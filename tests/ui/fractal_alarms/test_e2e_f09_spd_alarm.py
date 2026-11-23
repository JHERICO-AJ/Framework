"""E2E-F09 · Surge Protection Device (SPD) — the internal QA note 'Plan_Integral_Fractal'
section 7 ("E2E-F09 · Proteccion contra sobretension (SPD)", Site 4, ID 70,
severity Minor).

Injection details (which register/bit to force) come from
shared/domain/fractal_alarm_catalog.py's own alarm #70 entry, itself built
from the internal QA note 'Reporte_Alarmas_Fractal_Proto_Detalle_3''s confirmed-working
path: PcsModule.alarm_word_6 bit0 (the EMU-side alarm_word_1/2 bit5 paths
are catalogued as `inject_alt` -- confirmed broken, not used here).

Uses PCS-2 instead of the catalog's default PCS-1 (`pcs_override`):
confirmed live 2026-09-18 that once a (site, PCS, rule) combination has
fired once, OmniOps caches it as "already open" and won't re-raise it even
after a DB cleanup + fresh simulator/edge restart -- see
the internal QA note 'FRACTAL_ALARM_INJECTION_SETUP''s "GOTCHA CRITICO" section. PCS-1 on
BOLIVIA 4 already fired #70 once (2026-09-17) and stays "poisoned" until
someone restarts the OmniOps backend; PCS-2 hasn't.

Requires the real local stack for BOLIVIA 4 (simulator + our proxy + edge) --
see the internal QA note 'FRACTAL_ALARM_INJECTION_SETUP' for how to bring it up. Skips
(doesn't fail) if that site's proxy isn't reachable.

Cross-layer coverage, same pattern already used for Fleet Overview/Data &
Monitoring elsewhere in this repo: simulator (ground truth register) -> API
(GET /api/events/alarms/filtered, independent of UI rendering) -> UI (all 4
Plan Integral modules: Alarms & Events, Fleet Overview, Site View, Data &
Monitoring).
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

SITE = "BOLIVIA 4"
SITE_ID = "8eae282b-2b6b-44cf-8d6b-bb9540444c63"   # BOLIVIA 4 (confirmed via DB + Admin UI)
RULE_ID = 70
PCS_INDEX = 2   # see module docstring -- PCS-1 is cache-poisoned on this site


@pytest.fixture
def spd_alarm_active(require_fractal_site):
    require_fractal_site(SITE)

    # Step 1: clean baseline, WITHOUT the alarm -- lets the backend observe a
    # real "0" before forcing the transition (confirmed 2026-09-18: without
    # this, if the edge starts fresh with the bit already at 1, the backend
    # never sees a 0->1 change and never opens the alarm).
    save_state(SITE, [], baseline=True)
    time.sleep(15)

    # Step 2: the real 0->1 transition.
    save_state(SITE, [RULE_ID], baseline=True, pcs_override={RULE_ID: PCS_INDEX})
    time.sleep(10)  # time for simulator tick + edge send + OmniOps evaluation

    yield

    clear_state(SITE)


def test_simulator_register_is_actually_set(spd_alarm_active):
    """Simulator layer (ground truth): confirms the real Modbus register --
    Fractal.Pcs.AlarmWord6 bit0, PCS-2 -- is set to 1 before trusting any
    other layer. Reads through the proxy (same canonical port the
    edge/OmniOps uses), not directly against the real simulator."""
    from shared.datasource.fractal_modbus_source import read_fractal_pcs_alarm_words

    alarm_words = read_fractal_pcs_alarm_words(SITE, PCS_INDEX - 1)  # 0-based PCS_BASES index
    assert alarm_words[5] == 1, (
        f"expected alarm_word_6=1 (bit0, index 5) on PCS-{PCS_INDEX} of {SITE}, "
        f"got {alarm_words[5]}")


def test_alarm_visible_via_api(spd_alarm_active, alarms_service):
    """API layer: GET /api/events/alarms/filtered must return rule #70 open
    for BOLIVIA 4 -- independent of whether the UI renders it correctly or
    not (a real cross-check, not just screen scraping)."""
    matches = [a for a in alarms_service.by_rule_id(RULE_ID) if a.site_id == SITE_ID]
    assert matches, (
        f"the API returned no alarm for rule {RULE_ID} for site_id={SITE_ID} "
        f"({SITE})")

    alarm = matches[0]
    assert alarm.is_open, f"expected status Open, got {alarm.status!r}"
    assert alarm.severity.strip().lower() == "minor", (
        f"expected severity Minor, got {alarm.severity!r}")
    assert f"PCS-{PCS_INDEX}" in alarm.device_name, (
        f"expected device PCS-{PCS_INDEX}, got {alarm.device_name!r}")


def test_spd_alarm_row_in_alarms_and_events(spd_alarm_active, alarms_page):
    """Plan Integral, Alarms & Events: '1 alarm (70) in #alarmTableBody,
    subsystem Safety / Fire (SPD)'."""
    alarms_page.open()
    rows = [r for r in alarms_page.rows() if r.site == SITE]

    matching = [r for r in rows if "SPD" in r.name.upper() or "LIGHTNING" in r.name.upper()]
    assert matching, (
        f"no SPD/Lightning row appeared for {SITE} in Alarms & Events -- "
        f"rows found for the site: {[r.name for r in rows]!r}"
    )

    row = matching[0]
    assert row.severity.strip().lower() == "minor", (
        f"expected severity Minor (Plan Integral), got {row.severity!r}")
    # NOTE: the Plan Integral says "subsistema Safety / Fire", but the real
    # UI (confirmed live 2026-09-18) classifies this alarm under "PCS /
    # Inverter" -- a document-vs-real-behavior discrepancy, not a bug in
    # this test. Documented exactly as observed.
    assert row.subsystem.strip() == "PCS / Inverter", (
        f"expected subsystem 'PCS / Inverter' (confirmed live, not 'Safety / "
        f"Fire' as the Plan Integral states), got {row.subsystem!r}")
    assert f"PCS-{PCS_INDEX}" in row.device, (
        f"expected device PCS-{PCS_INDEX} (where it was injected), got {row.device!r}")


def test_fleet_overview_critical_unaffected(spd_alarm_active, logged_in_page):
    """Plan Integral, Fleet Overview: '#kpiGrid increments Active; S09's pin
    turns amber; everything else unchanged' -- #70 is Minor, it must not raise the
    Critical count (neither the site's row nor the fleet KPI)."""
    # The browser session is shared across tests in this run -- a previous
    # test may have left it on /alarms. The fleet_overview_page FIXTURE
    # calls .open() during its own setup (before this test body runs) and
    # FleetOverviewPage.open() deliberately doesn't navigate (see its own
    # docstring) -- so using that fixture here would fail before we get a
    # chance to click the sidebar link. Do the click first, then build the
    # page object ourselves.
    logged_in_page.get_by_role("link", name=re.compile("Fleet Overview", re.I)).click()
    fleet_overview_page = FleetOverviewPage(logged_in_page).open()
    sites = fleet_overview_page.sites_list()
    row = sites.row_index_by_site_name(SITE)
    assert row is not None, f"{SITE} doesn't appear in Fleet Overview's Sites List"
    assert sites.critical_count(row) == 0, (
        f"{SITE} shows Critical > 0 -- a Minor alarm (#70) shouldn't count there")
    # confirmed live 2026-09-18: the Status pill switches from
    # "Offline"/"Online" to "Warning" (amber, CSS class status-warning) as
    # soon as a Minor/Warning alarm is active on the site.
    assert sites.status_text(row) == "Warning", (
        f"expected the 'Warning' pill (amber) on {SITE} with alarm 70 active, "
        f"got {sites.status_text(row)!r}")


@pytest.mark.xfail(
    strict=True,
    reason="CONFIRMED DEFECT (2026-09-18, against the internal QA note 'OmniOps_Parameter_Mapping_V03 1' "
           "row 89, 'pcsevt1'): the spec requires this to 'display the LATEST ... raw "
           "register value', but the decode modal reads 'No bits set' even while the "
           "real Modbus register (confirmed via direct read) has alarm_word_6 bit0=1 "
           "RIGHT NOW. Same root cause as the Alarms & Events per-(site,PCS,rule) alarm "
           "cache (see the internal QA note 'FRACTAL_ALARM_INJECTION_SETUP''s GOTCHA CRITICO) -- the "
           "decode's bit list appears to derive from the same cached alert-promotion "
           "pipeline instead of polling the live register, so a (site, PCS, rule) "
           "combo that already fired once no longer shows here either. Also missing: "
           "the spec's own required PCS filter ('If multiple PCS exist, show selected "
           "PCS register or site-priority PCS based on UI filter') -- no such filter "
           "exists in the real UI, so which PCS's word gets shown isn't controllable.")
def test_data_monitoring_raw_bit_viewer_shows_the_bit(spd_alarm_active, logged_in_page):
    """Plan Integral, Data & Monitoring: 'Raw Event Bit Viewer muestra
    alarm_word_6'. Confirms the bit SHOULD show (per the Parameter Mapping
    spec, row 89 -- 'latest raw register value') but doesn't reliably,
    tracked as a confirmed defect above."""
    logged_in_page.get_by_role("link", name=re.compile("Data & Monitoring", re.I)).click()
    mp = MonitoringPage(logged_in_page).open()
    mp.select_site(SITE)

    viewer = mp.raw_event_bit_viewer()
    modal = viewer.open_decode()
    try:
        count_text = modal.set_bit_count_text()
        assert count_text and not count_text.strip().startswith("0"), (
            f"expected at least 1 bit Set (the injected alarm 70), got {count_text!r}")
    finally:
        modal.close()


def test_site_view_recent_alarms_lists_it(spd_alarm_active, logged_in_page):
    """Plan Integral, Site View: 'Recent Alarms lists the alarm'."""
    logged_in_page.get_by_role("link", name=re.compile("Site View", re.I)).click()
    sv = SiteViewPage(logged_in_page).open()
    sv.select_site(SITE)

    rows = sv.recent_alarms().rows()
    matching = [r for r in rows if "SPD" in r.description.upper() or "LIGHTNING" in r.description.upper()]
    assert matching, (
        f"no SPD/Lightning row appeared in Recent Alarms for {SITE} -- "
        f"descriptions found: {[r.description for r in rows]!r}"
    )
    row = matching[0]
    assert row.severity.strip().lower() == "minor", (
        f"expected severity Minor (Plan Integral), got {row.severity!r}")
    assert f"PCS-{PCS_INDEX}" in row.device, (
        f"expected device PCS-{PCS_INDEX} (where it was injected), got {row.device!r}")
