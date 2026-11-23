"""E2E-F10 · Trend alarms (Early Warning) — the internal QA note 'Plan_Integral_Fractal'
section 7. Site 5 = BOLIVIA 5. IDs: 74 (Meter vs PCS mismatch), 78 (PCS idle
power drift). Severity: Warning for both.

## Alarm 78 -- provable NOW
BOLIVIA 5's Data Intake already has `Idle drift duration=1s` (lowered from
the 3600s/1h default) and `Idle power limit=5kw` (already matched the
default) -- see the internal QA note 'FRACTAL_ALARM_INJECTION_SETUP'. Injection (from
shared/domain/fractal_alarm_catalog.py, alarm #78): `p_ac_kw=8` (>5kW) +
`status_word_1 bit5=1` (standby). NOTE: docs/Reporte_Alarmas_Fractal_Proto_
Detalle_3.txt mentions "PcsModule.alarm_word_1" bit5 instead of
status_word_1 -- likely a typo (the real register map,
modbus_common/fractal_addressing_map.py, assigns standby/hot-standby to
status_word_1, not alarm_word_1), not confirmed with the team -- keeping
status_word_1 (the version already confirmed working) until clarified.

## Alarm 74 -- NOT instantaneous, needs 1 real day running
Per that same report: the simulator ALREADY injects a 1.5% transformer/line
loss, above the 1% MeterMismatchTolPct, by design -- no register needs to
be forced for the CONDITION itself. The only thing missing is TIME: even
with MeterMismatchWindowDays lowered to 1 (already configured in BOLIVIA
5's Data Intake, previously 7 days), the site needs to run without
interrupting telemetry for a full day before the rolling window closes.
Its test is written (test_meter_mismatch_visible_via_api) but skipped by
default -- see its own docstring for how to actually run it.

Uses PCS-1 on BOLIVIA 5 (nothing has been tested on this site yet, so no
risk from the per-(site, PCS, rule) cache that does affect BOLIVIA 4/#70 --
see the internal QA note 'FRACTAL_ALARM_INJECTION_SETUP''s GOTCHA CRITICO).

Requires the real local stack for BOLIVIA 5 (simulator + proxy + edge) --
see the internal QA note 'FRACTAL_ALARM_INJECTION_SETUP'. Skips (doesn't fail) if that
site's proxy isn't reachable.
"""
from __future__ import annotations

import re
import time

import pytest

from framework_ui.pages.fleet_overview.fleet_overview_page import FleetOverviewPage
from framework_ui.pages.monitoring.monitoring_page import MonitoringPage
from framework_ui.pages.site_view.site_view_page import SiteViewPage
from shared.domain.fractal_register_injection import save_state, clear_state

pytestmark = [pytest.mark.ui, pytest.mark.local_fractal_sim]

SITE = "BOLIVIA 5"
SITE_ID = "45cb399d-a86b-4dc2-aed2-a9e6a5c18db3"
RULE_IDLE = 78
RULE_MISMATCH = 74
PCS_INDEX = 1


@pytest.fixture
def idle_drift_alarm_active(require_fractal_site):
    require_fractal_site(SITE)

    # Step 1: clean baseline, WITHOUT the alarm -- lets the backend observe
    # a real "0" before forcing the transition (same reason as F09: if the
    # edge starts with the condition already at 1 from its very first
    # reading, the backend never sees a 0->1 change and never opens the
    # alarm).
    save_state(SITE, [], baseline=True)
    time.sleep(15)

    # Step 2: the real transition -- p_ac_kw=8 (>5kW) + standby. 15s (not
    # 10s): confirmed 2026-09-19 that 10s sometimes isn't enough to show up
    # in an immediate Modbus read, even though the alarm still ends up
    # opening (the override itself is correct, it's just a tight time
    # margin).
    save_state(SITE, [RULE_IDLE], baseline=True, pcs_override={RULE_IDLE: PCS_INDEX})
    time.sleep(15)

    yield

    clear_state(SITE)


def test_simulator_register_is_actually_set(idle_drift_alarm_active):
    """Simulator layer (ground truth): p_ac_kw > 5kW and status_word_1
    bit5=1 on PCS-1, read through the proxy (canonical port)."""
    from shared.datasource.fractal_modbus_source import (
        read_fractal_pcs_active_power_kw, read_fractal_pcs_status_word_1,
    )

    p_kw = read_fractal_pcs_active_power_kw(SITE, PCS_INDEX - 1)
    assert abs(p_kw) > 5, f"expected |p_ac_kw| > 5kW on PCS-{PCS_INDEX}, got {p_kw}"

    status_word_1 = read_fractal_pcs_status_word_1(SITE, PCS_INDEX - 1)
    assert status_word_1 & (1 << 5), (
        f"expected status_word_1 bit5=1 (standby) on PCS-{PCS_INDEX}, "
        f"got {status_word_1:#010b}")


def test_alarm_visible_via_api(idle_drift_alarm_active, alarms_service):
    """API layer: GET /api/events/alarms/filtered must return rule #78 open
    for BOLIVIA 5 -- independent of whether the UI renders it correctly."""
    matches = [a for a in alarms_service.by_rule_id(RULE_IDLE) if a.site_id == SITE_ID]
    assert matches, (
        f"the API returned no alarm for rule {RULE_IDLE} for site_id={SITE_ID} "
        f"({SITE})")

    alarm = matches[0]
    assert alarm.is_open, f"expected status Open, got {alarm.status!r}"
    assert alarm.severity.strip().lower() == "warning", (
        f"expected severity Warning, got {alarm.severity!r}")
    assert f"PCS-{PCS_INDEX}" in alarm.device_name, (
        f"expected device PCS-{PCS_INDEX}, got {alarm.device_name!r}")
    # NOTE: the Plan Integral says "subsistema Early Warning" -- confirmed
    # live 2026-09-19 that the real API returns "TRANSFORMER_PCS", same as
    # #70 (which the Plan Integral also documents differently from reality --
    # see test_e2e_f09_spd_alarm.py). Documented exactly as observed, not a
    # bug in this test.
    assert alarm.subsystem.strip() == "TRANSFORMER_PCS", (
        f"expected subsystem 'TRANSFORMER_PCS' (confirmed live, not 'Early "
        f"Warning' as the Plan Integral states), got {alarm.subsystem!r}")


def test_idle_drift_row_in_alarms_and_events(idle_drift_alarm_active, alarms_page):
    """Plan Integral, Alarms & Events: '2 alarms (74, 78) in
    #alarmTableBody, subsystem Early Warning' -- this test covers 78 (74
    needs the 1-day window, see test_meter_mismatch_visible_via_api)."""
    alarms_page.open()
    rows = [r for r in alarms_page.rows() if r.site == SITE]

    matching = [r for r in rows if "IDLE" in r.name.upper() or "DRIFT" in r.name.upper()]
    assert matching, (
        f"no Idle Power Drift row appeared for {SITE} in Alarms & Events -- "
        f"rows found for the site: {[r.name for r in rows]!r}"
    )

    row = matching[0]
    assert row.severity.strip().lower() == "warning", (
        f"expected severity Warning (Plan Integral), got {row.severity!r}")
    assert f"PCS-{PCS_INDEX}" in row.device, (
        f"expected device PCS-{PCS_INDEX} (where it was injected), got {row.device!r}")
    # see the note in test_alarm_visible_via_api: the UI shows "PCS /
    # Inverter" (translated from TRANSFORMER_PCS), not "Early Warning" as
    # the Plan Integral states.
    assert row.subsystem.strip() == "PCS / Inverter", (
        f"expected subsystem 'PCS / Inverter' (confirmed live, not 'Early "
        f"Warning' as the Plan Integral states), got {row.subsystem!r}")


def test_fleet_overview_reflects_it(idle_drift_alarm_active, logged_in_page):
    """Plan Integral, Fleet Overview: '#kpiGrid increments Active; S10's pin
    turns amber; everything else unchanged'."""
    logged_in_page.get_by_role("link", name=re.compile("Fleet Overview", re.I)).click()
    fleet_overview_page = FleetOverviewPage(logged_in_page).open()
    sites = fleet_overview_page.sites_list()
    row = sites.row_index_by_site_name(SITE)
    assert row is not None, f"{SITE} doesn't appear in Fleet Overview's Sites List"
    assert sites.critical_count(row) == 0, (
        f"{SITE} shows Critical > 0 -- a Warning alarm (#78) shouldn't count there")
    assert sites.status_text(row) == "Warning", (
        f"expected the 'Warning' pill (amber) on {SITE} with alarm 78 active, "
        f"got {sites.status_text(row)!r}")


def test_site_view_recent_alarms_lists_it(idle_drift_alarm_active, logged_in_page):
    """Plan Integral, Site View: 'Recent Alarms lists the alarms once the
    window closes'."""
    logged_in_page.get_by_role("link", name=re.compile("Site View", re.I)).click()
    sv = SiteViewPage(logged_in_page).open()
    sv.select_site(SITE)

    rows = sv.recent_alarms().rows()
    matching = [r for r in rows if "IDLE" in r.description.upper() or "DRIFT" in r.description.upper()]
    assert matching, (
        f"no Idle Power Drift row appeared in Recent Alarms for {SITE} -- "
        f"descriptions found: {[r.description for r in rows]!r}"
    )
    row = matching[0]
    assert row.severity.strip().lower() == "warning", (
        f"expected severity Warning (Plan Integral), got {row.severity!r}")
    assert f"PCS-{PCS_INDEX}" in row.device, (
        f"expected device PCS-{PCS_INDEX} (where it was injected), got {row.device!r}")


def test_data_monitoring_telemetry_shows_the_drift(idle_drift_alarm_active, logged_in_page):
    """Plan Integral, Data & Monitoring: 'Telemetry Data Table (Quality
    column) and Site Power Telemetry show evidence of the window'. Unlike
    F09 (pure bit, Raw Event Bit Viewer), #78 is a BY-VALUE rule -- the
    expected evidence here is the live telemetry table itself showing
    Active Power for the injected PCS, with good data quality (proving the
    data that feeds the trend rule IS arriving correctly, not that a
    specific bit exists)."""
    logged_in_page.get_by_role("link", name=re.compile("Data & Monitoring", re.I)).click()
    mp = MonitoringPage(logged_in_page).open()
    mp.select_site(SITE)

    table = mp.telemetry_data_table()
    table.wait_for_rows()
    row = table.search_recent_row_for_metric("Active Power", device=f"PCS-{PCS_INDEX}")
    assert row is not None, (
        f"no recent 'Active Power' row found for PCS-{PCS_INDEX} "
        f"in the Telemetry Data Table")
    quality = row.get("Quality", "").strip().lower()
    assert quality in ("good", "ok"), f"unexpected data quality: {row.get('Quality')!r}"


# ---------------------------------------------------------------------------
# Alarm 74 (Meter vs PCS mismatch) -- everything below is built and ready,
# but most of it stays `skip` because the alarm itself can't open without
# ~1 real day passing (MeterMismatchWindowDays=1). The EXCEPTION is
# test_simulator_meter_mismatch_condition_present: the CONDITION (transformer
# loss > 1% tolerance) is already true right now by simulator design,
# without injecting anything -- that much can be confirmed today, without
# waiting for the window.
# ---------------------------------------------------------------------------
def test_simulator_meter_mismatch_condition_present(require_fractal_site):
    """Simulator layer (ground truth) -- NOT skipped: confirms the
    condition that feeds rule #74 (deviation > 1% between the meter and the
    sum of PCS) is already true right now, without injecting anything. This
    does NOT prove alarm #74 is already open (that requires the full 1-day
    window) -- it only proves that, once the day passes, the underlying
    condition is still there. Manually confirmed 2026-09-19: ~1.51%
    relative error, above the 1% MeterMismatchTolPct."""
    require_fractal_site(SITE)
    from shared.datasource.fractal_modbus_source import (
        read_fractal_site_total_kw, read_fractal_meter_total_active_power_kw,
    )

    pcs_total_kw = read_fractal_site_total_kw(SITE)
    meter_kw = read_fractal_meter_total_active_power_kw(SITE)
    assert pcs_total_kw != 0, "sum of PCS = 0 -- can't compute the relative error"

    err = abs(meter_kw - pcs_total_kw) / abs(pcs_total_kw)
    assert err > 0.01, (
        f"meter vs PCS relative error = {err*100:.2f}% -- expected > 1% "
        f"(MeterMismatchTolPct) for rule #74 to eventually fire")


@pytest.mark.skip(
    reason="Requires BOLIVIA 5 to run without interrupting telemetry for ~1 full day "
           "(MeterMismatchWindowDays=1, configured in Data Intake) before the rolling "
           "window closes -- see this module's docstring. To actually run it: remove "
           "this skip, leave BOLIVIA 5's stack (simulator+proxy+edge) running 24h+ "
           "without interruption, then execute this file.")
def test_meter_mismatch_visible_via_api(require_fractal_site, alarms_service):
    """API layer. Plan Integral, trend criterion: '#74 must NOT fire before "
    the window completes... and MUST once it closes, with the window's "
    timestamp'. No register needs to be injected -- the simulator's own "
    factory mismatch (1.5% transformer/line loss > 1% tolerance, see "
    test_simulator_meter_mismatch_condition_present) is already enough; "
    only real elapsed time is missing."""
    require_fractal_site(SITE)
    matches = [a for a in alarms_service.by_rule_id(RULE_MISMATCH) if a.site_id == SITE_ID]
    assert matches, (
        f"the API returned no alarm {RULE_MISMATCH} for {SITE} -- "
        f"did you run the stack uninterrupted for 24h+?")
    alarm = matches[0]
    assert alarm.is_open, f"expected status Open, got {alarm.status!r}"
    assert alarm.severity.strip().lower() == "warning", (
        f"expected severity Warning, got {alarm.severity!r}")


_SKIP_74_REASON = (
    "Requires BOLIVIA 5 to run without interrupting telemetry for ~1 full day "
    "(MeterMismatchWindowDays=1) before alarm #74 can open -- see the module "
    "docstring and test_meter_mismatch_visible_via_api. Remove this skip once "
    "the 1-day window has already run.")


@pytest.mark.skip(reason=_SKIP_74_REASON)
def test_meter_mismatch_row_in_alarms_and_events(require_fractal_site, alarms_page):
    """Plan Integral, Alarms & Events: '2 alarms (74, 78) in
    #alarmTableBody, subsystem Early Warning' -- this one specifically
    covers 74."""
    require_fractal_site(SITE)
    alarms_page.open()
    rows = [r for r in alarms_page.rows() if r.site == SITE]

    matching = [r for r in rows if "MISMATCH" in r.name.upper() or "METER" in r.name.upper()]
    assert matching, (
        f"no Meter vs PCS mismatch row appeared for {SITE} in Alarms & "
        f"Events -- rows found for the site: {[r.name for r in rows]!r}"
    )
    row = matching[0]
    assert row.severity.strip().lower() == "warning", (
        f"expected severity Warning (Plan Integral), got {row.severity!r}")


@pytest.mark.skip(reason=_SKIP_74_REASON)
def test_meter_mismatch_fleet_overview_reflects_it(require_fractal_site, logged_in_page):
    """Plan Integral, Fleet Overview: '#kpiGrid increments Active; S10's pin
    turns amber; everything else unchanged'."""
    require_fractal_site(SITE)
    logged_in_page.get_by_role("link", name=re.compile("Fleet Overview", re.I)).click()
    fleet_overview_page = FleetOverviewPage(logged_in_page).open()
    sites = fleet_overview_page.sites_list()
    row = sites.row_index_by_site_name(SITE)
    assert row is not None, f"{SITE} doesn't appear in Fleet Overview's Sites List"
    assert sites.critical_count(row) == 0, (
        f"{SITE} shows Critical > 0 -- a Warning alarm (#74) shouldn't count there")
    assert sites.status_text(row) == "Warning", (
        f"expected the 'Warning' pill (amber) on {SITE} with alarm 74 active, "
        f"got {sites.status_text(row)!r}")


@pytest.mark.skip(reason=_SKIP_74_REASON)
def test_meter_mismatch_site_view_lists_it(require_fractal_site, logged_in_page):
    """Plan Integral, Site View: 'Recent Alarms lists the alarms once the
    window closes; Key Trends - Power may show the drift'."""
    require_fractal_site(SITE)
    logged_in_page.get_by_role("link", name=re.compile("Site View", re.I)).click()
    sv = SiteViewPage(logged_in_page).open()
    sv.select_site(SITE)

    rows = sv.recent_alarms().rows()
    matching = [r for r in rows if "MISMATCH" in r.description.upper() or "METER" in r.description.upper()]
    assert matching, (
        f"no Meter vs PCS mismatch row appeared in Recent Alarms for {SITE} -- "
        f"descriptions found: {[r.description for r in rows]!r}"
    )
    row = matching[0]
    assert row.severity.strip().lower() == "warning", (
        f"expected severity Warning (Plan Integral), got {row.severity!r}")


@pytest.mark.skip(reason=_SKIP_74_REASON)
def test_meter_mismatch_data_monitoring_shows_the_window(require_fractal_site, logged_in_page):
    """Plan Integral, Data & Monitoring: 'Telemetry Data Table (Quality
    column) and Site Power Telemetry show evidence of the window'. Unlike
    #78 (per-PCS), #74 is at the METER/site level -- the evidence is the
    meter's telemetry row with good data quality (proving the data feeding
    the Meter-vs-PCS comparison IS arriving). NOTE: the exact metric/device
    name for the meter's row in this table hasn't been confirmed live yet
    (requires actually running this test first) -- adjust the metric/device
    filter below if it doesn't match once the skip is removed."""
    require_fractal_site(SITE)
    logged_in_page.get_by_role("link", name=re.compile("Data & Monitoring", re.I)).click()
    mp = MonitoringPage(logged_in_page).open()
    mp.select_site(SITE)

    table = mp.telemetry_data_table()
    table.wait_for_rows()
    row = table.search_recent_row_for_metric("Active Power")
    assert row is not None, "no recent 'Active Power' row found (meter)"
    quality = row.get("Quality", "").strip().lower()
    assert quality in ("good", "ok"), f"unexpected data quality: {row.get('Quality')!r}"
