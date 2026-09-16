"""Data & Monitoring - PCS Energy Statistics (docs/OF-150.txt): a 2-block
period-energy summary (PCS Charge Energy, PCS Discharge Energy) that
follows the page's GLOBAL 24h/7d/30d selector -- unlike Event Log/Alarm
History (whose badge is purely informational), this card's VALUES actually
change with the selected range (CA-05: "Al cambiar el rango -> recarga
valores").

BOLIVIA (Fractal). Confirmed via direct DB query (monitoring."MonitoringStat"):
EgPcsChg/EgPcsDchg are NULL for every row -- the documented Fractal gap
("Campos diarios/totales en proto EMU/PCS sin mapeo a EgPcsChg/EgPcsDchg").
So the displayed MWh values come from the power x time integration fallback
(docs/OF-150.txt: "Sin contadores: integración |potencia activa| x Δt,
carga si potencia > 0, descarga si < 0").

Root cause fully confirmed 2026-09-12 by reading the real backend source
(back_omniOps/src/Modules/Monitoring/Application/Services/Implementations/
MonitoringComputedService.cs + SiteState.cs):
  - For a site with no EgPcsChg/EgPcsDchg counters (BOLIVIA's case), even the
    "24h" range falls through to BuildPcsFromStats (the SAME historical-
    bucket-based calculation as 7d/30d) -- NOT a true continuously-live RAM
    counter as CA-10 implies for sites WITH counters.
  - TryPeriodEnergyFromDevices groups MonitoringStat rows by DeviceName and,
    per device, integrates power x Δt between consecutive persisted buckets
    (ActivePower > 0 -> charge, < 0 -> discharge), then SUMS every device
    group's total into the site total.
  - IsPcsEnergySource (the filter deciding which rows count) matches BOTH the
    per-unit devices (PCS-1/PCS-2/PCS-3) AND the site-level aggregate device
    ("00:00:00:00:00:00", same SubsystemName=TRANSFORMER_PCS) -- so the site
    total double-counts: once via the 3 individual PCS, once again via the
    aggregate device that already IS their sum. Confirmed by reproducing the
    exact algorithm against real MonitoringStat rows in Python: the
    aggregate device alone contributed ~15917.6 kWh charge over 24h, and the
    3 individual PCS summed to another ~15917.6 kWh -- and the manual
    replica's grand total (31835.15/1963.32 kWh) matched the LIVE API's own
    response to the exact decimal, confirming the algorithm (and the bug)
    with total certainty.
  - The sign convention itself (power>0=charge, power<0=discharge) was
    independently verified against real physics, not just the docs: joined
    MonitoringStat's Soc (Battery/BMS) against ActivePower (TRANSFORMER_PCS
    aggregate) at matching timestamps and confirmed SOC drops in lock-step
    with sustained negative power (49.90 -> 49.00 across 01:35-02:05 UTC on
    2026-09-13, power consistently -3200 to -7800 kW that whole stretch) --
    an unambiguous real discharge signature. The sign rule is correct; only
    the double-counting is a defect.
  - Separately (and NOT the same bug): the frontend does not appear to
    refetch this card's data on any interval -- watched the live UI for 6
    real minutes with zero interaction and it never changed, while an
    independent fresh API call made immediately after showed a HIGHER
    dischargeEnergyMWh than what was still frozen on screen. The backend
    value moves; the screen doesn't, without a reload.
"""
import re
import time
from datetime import datetime, timedelta, timezone

import pytest

from framework_api.services.monitoring_service import MonitoringService
from shared.datasource.db_source import get_site_ids

pytestmark = pytest.mark.ui

SITE_NAME = "BOLIVIA"
EXPECTED_BLOCK_TITLES = ["PCS Charge Energy", "PCS Discharge Energy"]

RANGE_LABEL_TO_BADGE = {"Last 24 hours": "24H", "Last 7 days": "7D", "Last 30 days": "30D"}
RANGE_LABEL_TO_PERIOD_TEXT = {
    "Last 24 hours": "Last 24 hours.", "Last 7 days": "Last 7 days.", "Last 30 days": "Last 30 days.",
}
RANGE_LABEL_TO_API_TIME_RANGE = {"Last 24 hours": "24h", "Last 7 days": "7d", "Last 30 days": "30d"}


@pytest.fixture
def bolivia_monitoring_page(require_omniops, monitoring_page):
    return monitoring_page.select_site(SITE_NAME)


@pytest.fixture(scope="session")
def bolivia_site_id(db_conn):
    return get_site_ids(db_conn, [SITE_NAME])[SITE_NAME]


def test_card_badge_and_subtitle(bolivia_monitoring_page):
    """CA-04/CA-07: badge shows the current global range; subtitle explains
    PCS-side throughput for utilization/efficiency analysis."""
    pcs = bolivia_monitoring_page.pcs_energy_statistics()
    assert pcs.time_range_badge() == "24H"
    assert pcs.time_range_period() == "Last 24 hours."
    subtitle = pcs.subtitle().lower()
    assert "pcs" in subtitle and ("throughput" in subtitle or "efficiency" in subtitle), (
        f"expected the subtitle to mention PCS throughput/efficiency, got: {pcs.subtitle()!r}")


def test_exactly_2_blocks_in_documented_order(bolivia_monitoring_page):
    """CA-08/CA-12: exactly these 2 blocks, in this order."""
    pcs = bolivia_monitoring_page.pcs_energy_statistics()
    assert pcs.block_titles() == EXPECTED_BLOCK_TITLES


@pytest.mark.parametrize("range_label", ["Last 24 hours", "Last 7 days", "Last 30 days"])
def test_help_text_mentions_the_selected_period_label(bolivia_monitoring_page, range_label):
    """CA-09/CA-13: each block's help text names the currently selected
    period (\"Last 24 hours\" / \"Last 7 days\" / \"Last 30 days\")."""
    bolivia_monitoring_page.select_time_range(range_label)
    bolivia_monitoring_page.page.wait_for_timeout(500)
    pcs = bolivia_monitoring_page.pcs_energy_statistics()

    charge_help = pcs.help_text("PCS Charge Energy")
    discharge_help = pcs.help_text("PCS Discharge Energy")
    assert range_label.lower() in charge_help.lower(), (
        f"expected {range_label!r} in Charge Energy's help text, got: {charge_help!r}")
    assert range_label.lower() in discharge_help.lower(), (
        f"expected {range_label!r} in Discharge Energy's help text, got: {discharge_help!r}")


@pytest.mark.parametrize("range_label", ["Last 24 hours", "Last 7 days", "Last 30 days"])
def test_value_format_is_3_decimals_with_mwh_unit(bolivia_monitoring_page, range_label):
    """CA-26/CA-27: X.XXX MWh (3 decimals) whenever there's a number."""
    bolivia_monitoring_page.select_time_range(range_label)
    bolivia_monitoring_page.page.wait_for_timeout(500)
    pcs = bolivia_monitoring_page.pcs_energy_statistics()

    for title in EXPECTED_BLOCK_TITLES:
        text = pcs.value_text(title)
        if text.strip() == "—":
            continue
        assert re.fullmatch(r"\d+\.\d{3} MWh", text), (
            f"[{range_label}] expected 'X.XXX MWh' format for {title!r}, got: {text!r}")


@pytest.mark.parametrize("range_label", ["Last 24 hours", "Last 7 days", "Last 30 days"])
def test_ui_values_match_api_pcs_energy(bolivia_monitoring_page, api_client, bolivia_site_id, range_label):
    """True cross-layer ground truth (UI vs the REAL API endpoint the UI
    itself calls -- docs/OF-150.txt: GET /monitoring/pcs-energy/{siteId}
    ?timeRange=). The UI's chargeEnergyMWh/dischargeEnergyMWh are already
    rounded server-side to 3 decimals -- exactly what's rendered -- so this
    is an exact-match check, not a tolerance-based one."""
    bolivia_monitoring_page.select_time_range(range_label)
    bolivia_monitoring_page.page.wait_for_timeout(500)
    pcs = bolivia_monitoring_page.pcs_energy_statistics()

    api_time_range = RANGE_LABEL_TO_API_TIME_RANGE[range_label]
    api_data = MonitoringService(api_client).get_pcs_energy(site_id=bolivia_site_id, time_range=api_time_range)

    ui_charge = pcs.charge_energy_mwh()
    ui_discharge = pcs.discharge_energy_mwh()
    api_charge = api_data["chargeEnergyMWh"]
    api_discharge = api_data["dischargeEnergyMWh"]

    if ui_charge is None or api_charge is None:
        assert ui_charge is None and api_charge is None, (
            f"[{range_label}] UI Charge Energy {ui_charge!r} disagrees with API chargeEnergyMWh {api_charge!r}")
    else:
        assert ui_charge == pytest.approx(api_charge, abs=0.001), (
            f"[{range_label}] UI Charge Energy {ui_charge} disagrees with API chargeEnergyMWh {api_charge}")

    if ui_discharge is None or api_discharge is None:
        assert ui_discharge is None and api_discharge is None, (
            f"[{range_label}] UI Discharge Energy {ui_discharge!r} disagrees with API dischargeEnergyMWh {api_discharge!r}")
    else:
        assert ui_discharge == pytest.approx(api_discharge, abs=0.001), (
            f"[{range_label}] UI Discharge Energy {ui_discharge} disagrees with API dischargeEnergyMWh {api_discharge}")


def test_switching_time_range_actually_changes_the_values(bolivia_monitoring_page):
    """CA-05/CA-18/CA-20: unlike Event Log/Alarm History's purely
    informational badge, THIS card's values must actually change when the
    range changes -- confirms the panel doesn't silently keep showing a
    stale 24h number under a 7D/30D badge."""
    pcs = bolivia_monitoring_page.pcs_energy_statistics()

    bolivia_monitoring_page.select_time_range("Last 24 hours")
    bolivia_monitoring_page.page.wait_for_timeout(500)
    charge_24h = pcs.charge_energy_mwh()
    discharge_24h = pcs.discharge_energy_mwh()

    bolivia_monitoring_page.select_time_range("Last 7 days")
    bolivia_monitoring_page.page.wait_for_timeout(500)
    assert pcs.time_range_badge() == "7D"
    charge_7d = pcs.charge_energy_mwh()
    discharge_7d = pcs.discharge_energy_mwh()

    assert (charge_24h, discharge_24h) != (charge_7d, discharge_7d), (
        f"expected different totals for 24h {(charge_24h, discharge_24h)} vs 7d "
        f"{(charge_7d, discharge_7d)} -- got identical values")


def test_longer_windows_accumulate_at_least_as_much_as_shorter_ones(bolivia_monitoring_page):
    """CA-21/CA-22: energy is a PERIOD total, not a lifetime counter -- but
    since the 7d and 30d windows both fully CONTAIN the last 24h, their
    totals can only be >= the 24h total (accumulation never goes
    backwards). Also confirms 30d >= 7d for the same reason. A real,
    robust sanity check that doesn't depend on knowing the exact
    integration formula."""
    pcs = bolivia_monitoring_page.pcs_energy_statistics()
    totals = {}
    for label in ("Last 24 hours", "Last 7 days", "Last 30 days"):
        bolivia_monitoring_page.select_time_range(label)
        bolivia_monitoring_page.page.wait_for_timeout(500)
        totals[label] = (pcs.charge_energy_mwh() or 0, pcs.discharge_energy_mwh() or 0)

    charge_24h, discharge_24h = totals["Last 24 hours"]
    charge_7d, discharge_7d = totals["Last 7 days"]
    charge_30d, discharge_30d = totals["Last 30 days"]

    assert charge_7d >= charge_24h, f"expected 7d charge ({charge_7d}) >= 24h charge ({charge_24h})"
    assert discharge_7d >= discharge_24h, f"expected 7d discharge ({discharge_7d}) >= 24h discharge ({discharge_24h})"
    assert charge_30d >= charge_7d, f"expected 30d charge ({charge_30d}) >= 7d charge ({charge_7d})"
    assert discharge_30d >= discharge_7d, f"expected 30d discharge ({discharge_30d}) >= 7d discharge ({discharge_7d})"


def _replicate_backend_period_energy(db_conn, site_id, window_start, device_filter=None, hourly_only=False, exclude_today=False):
    """Exact Python re-implementation of the real backend pipeline
    (MonitoringStatRepository.GetStatsForPowerTrendAsync +
    MonitoringComputedService.TryPeriodEnergyFromDevices), confirmed
    2026-09-13 to match the live API to the exact decimal for 24h, 7d, and
    30d: group MonitoringStat rows by DeviceName, order by BucketTimestamp,
    integrate ActivePower x Δt between consecutive buckets per device
    (power>0 -> charge, power<0 -> discharge), sum every device group.

    `hourly_only`/`exclude_today` replicate the 7d/30d-only "wide window"
    subsampling (MonitoringStatRepository.cs: for 7d/30d, only rows where
    BucketTimestamp.Minute == 0 are kept, and today's rows are dropped
    entirely) -- 24h uses neither (full 5-minute resolution, today
    included). `device_filter` restricts to specific DeviceName values
    (e.g. only the 3 individual PCS, excluding the site aggregate) --
    letting this same helper compute either the buggy (all devices, matches
    the live API) or the correct (individual PCS only) total."""
    query = (
        'SELECT "DeviceName", "BucketTimestamp", "ActivePower" FROM monitoring."MonitoringStat" '
        'WHERE "SiteId" = %s AND "BucketTimestamp" >= %s '
        'AND ("DeviceName" ILIKE %s OR "SubsystemName" = %s)'
    )
    params = [site_id, window_start, "%PCS%", "TRANSFORMER_PCS"]
    if hourly_only:
        query += ' AND EXTRACT(MINUTE FROM "BucketTimestamp") = 0'
    if exclude_today:
        query += ' AND "BucketTimestamp" < %s'
        params.append(datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0))
    query += ' ORDER BY "DeviceName", "BucketTimestamp"'

    with db_conn.cursor() as cur:
        cur.execute(query, params)
        rows = cur.fetchall()

    from collections import defaultdict
    by_device = defaultdict(list)
    for device, ts, power in rows:
        if device_filter is not None and device not in device_filter:
            continue
        by_device[device].append((ts, power))

    total_charge_kwh = 0.0
    total_discharge_kwh = 0.0
    for device, seq in by_device.items():
        for (t0, _), (t1, p1) in zip(seq, seq[1:]):
            if p1 is None:
                continue
            dt_h = (t1 - t0).total_seconds() / 3600.0
            if dt_h <= 0:
                continue
            p = float(p1)
            if p > 0:
                total_charge_kwh += p * dt_h
            elif p < 0:
                total_discharge_kwh += abs(p * dt_h)

    return total_charge_kwh / 1000, total_discharge_kwh / 1000  # -> MWh


@pytest.mark.parametrize("range_label,api_time_range,days,hourly_only,exclude_today", [
    ("Last 24 hours", "24h", 1, False, False),
    ("Last 7 days", "7d", 7, True, True),
    ("Last 30 days", "30d", 30, True, True),
])
@pytest.mark.xfail(
    strict=True,
    reason="CONFIRMED DEFECT (2026-09-12/13), root cause pinned down in the "
           "real backend source (MonitoringComputedService.IsPcsEnergySource): "
           "the site total sums BOTH the 3 individual PCS device groups AND "
           "the separate site-level aggregate device ('00:00:00:00:00:00', "
           "which already IS their sum, same SubsystemName=TRANSFORMER_PCS) "
           "-- double-counting every unit of real energy, in ALL 3 time "
           "ranges (same shared backend function). Confirmed by re-running "
           "the exact algorithm in Python against real MonitoringStat rows, "
           "matching each range's own real query shape (24h: full 5-min "
           "resolution; 7d/30d: hourly-only subsample excluding today's "
           "incomplete data, confirmed 2026-09-13 to reproduce the live "
           "API's number to the exact decimal): the individual-PCS-only "
           "total (the physically correct site total) comes out to "
           "roughly HALF of what the live API actually returns, in every "
           "single range.")
def test_site_total_does_not_double_count_the_aggregate_device(
        bolivia_monitoring_page, api_client, bolivia_site_id, db_conn,
        range_label, api_time_range, days, hourly_only, exclude_today):
    bolivia_monitoring_page.select_time_range(range_label)
    bolivia_monitoring_page.page.wait_for_timeout(500)

    if hourly_only:
        window_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=days)
    else:
        window_start = datetime.now(timezone.utc) - timedelta(days=days)

    correct_charge, correct_discharge = _replicate_backend_period_energy(
        db_conn, bolivia_site_id, window_start, device_filter={"PCS-1", "PCS-2", "PCS-3"},
        hourly_only=hourly_only, exclude_today=exclude_today)

    api_data = MonitoringService(api_client).get_pcs_energy(site_id=bolivia_site_id, time_range=api_time_range)
    api_charge = api_data["chargeEnergyMWh"]
    api_discharge = api_data["dischargeEnergyMWh"]

    assert api_charge == pytest.approx(correct_charge, abs=0.05), (
        f"[{range_label}] expected the API's Charge Energy ({api_charge} MWh) to match the sum of "
        f"the 3 individual PCS only ({correct_charge:.3f} MWh) -- instead it's inflated by also "
        f"counting the site-aggregate device on top")
    assert api_discharge == pytest.approx(correct_discharge, abs=0.05), (
        f"[{range_label}] expected the API's Discharge Energy ({api_discharge} MWh) to match the "
        f"sum of the 3 individual PCS only ({correct_discharge:.3f} MWh) -- instead it's inflated by "
        f"also counting the site-aggregate device on top")


@pytest.mark.xfail(
    strict=True,
    reason="CONFIRMED DEFECT (2026-09-12): CA-10 requires 24h mode to "
           "update live ('sube en vivo ~5 s'). Confirmed live: watched the "
           "actual rendered UI (not the raw API) for 6 real minutes with "
           "zero interaction/reload -- the displayed Charge/Discharge "
           "values never changed even once. Immediately after, an "
           "independent fresh API call for the same site/range returned a "
           "HIGHER Discharge Energy than what was still frozen on screen -- "
           "proving the backend value genuinely moved during those 6 "
           "minutes while the page simply never re-fetched it. The card "
           "needs a manual reload to show current data.")
def test_ui_refreshes_without_a_manual_reload(bolivia_monitoring_page, api_client, bolivia_site_id):
    bolivia_monitoring_page.select_time_range("Last 24 hours")
    bolivia_monitoring_page.page.wait_for_timeout(500)
    pcs = bolivia_monitoring_page.pcs_energy_statistics()

    ui_before = (pcs.charge_energy_mwh(), pcs.discharge_energy_mwh())
    bolivia_monitoring_page.page.wait_for_timeout(6 * 60 * 1000)  # 6 real minutes, no interaction
    ui_after = (pcs.charge_energy_mwh(), pcs.discharge_energy_mwh())

    fresh_api = MonitoringService(api_client).get_pcs_energy(site_id=bolivia_site_id, time_range="24h")
    api_now = (fresh_api["chargeEnergyMWh"], fresh_api["dischargeEnergyMWh"])

    assert api_now != ui_before, (
        "sanity check failed: the backend value itself didn't change in 6 minutes either -- "
        "can't validate the UI's live-refresh behavior without a real underlying change")
    assert ui_after == api_now, (
        f"expected the UI to have refreshed on its own to match the current backend value "
        f"{api_now}, but it stayed frozen at {ui_after} (was {ui_before} 6 minutes earlier)")


def test_charge_discharge_sign_convention_matches_real_battery_soc(bolivia_monitoring_page, db_conn, bolivia_site_id):
    """Independent physics-based verification of docs/OF-150.txt's sign
    rule ("carga si potencia > 0, descarga si < 0") -- not just trusting
    the document, but confirming it against the one ground truth that
    can't be ambiguous: a real battery's SOC falls while it discharges and
    rises while it charges. Finds a real stretch of several consecutive
    same-sign ActivePower buckets (aggregate device) and checks the SOC
    trend across that same stretch moves in the documented direction."""
    window_start = datetime.now(timezone.utc) - timedelta(hours=12)
    with db_conn.cursor() as cur:
        cur.execute(
            'SELECT s."BucketTimestamp", s."Soc", p."ActivePower" '
            'FROM monitoring."MonitoringStat" s '
            'JOIN monitoring."MonitoringStat" p '
            '  ON p."SiteId" = s."SiteId" AND p."BucketTimestamp" = s."BucketTimestamp" '
            '  AND p."SubsystemName" = %s AND p."DeviceName" = %s '
            'WHERE s."SiteId" = %s AND s."SubsystemName" = %s AND s."BucketTimestamp" >= %s '
            'ORDER BY s."BucketTimestamp"',
            ("TRANSFORMER_PCS", "00:00:00:00:00:00", bolivia_site_id, "BATTERY_BMS", window_start),
        )
        rows = cur.fetchall()

    if len(rows) < 4:
        pytest.skip("not enough joined SOC/ActivePower rows in the last 12h to check the sign convention")

    # longest run of consecutive same-sign power buckets
    best_run, current_run = [], [rows[0]]
    for prev, curr in zip(rows, rows[1:]):
        same_sign = (prev[2] > 0) == (curr[2] > 0) and curr[2] != 0
        if same_sign:
            current_run.append(curr)
        else:
            if len(current_run) > len(best_run):
                best_run = current_run
            current_run = [curr]
    if len(current_run) > len(best_run):
        best_run = current_run

    if len(best_run) < 4:
        pytest.skip(f"no run of >=4 consecutive same-sign power buckets in the last 12h "
                    f"(longest was {len(best_run)}) -- can't confirm the sign convention right now")

    soc_start, soc_end = best_run[0][1], best_run[-1][1]
    power_sign_positive = best_run[0][2] > 0
    soc_delta = float(soc_end) - float(soc_start)

    if power_sign_positive:
        assert soc_delta >= -0.1, (
            f"positive power (documented as 'charge') over {len(best_run)} buckets "
            f"({best_run[0][0]} to {best_run[-1][0]}) but SOC fell {soc_delta:.2f} pts "
            f"({soc_start} -> {soc_end}) -- looks like discharging, not charging")
    else:
        assert soc_delta <= 0.1, (
            f"negative power (documented as 'discharge') over {len(best_run)} buckets "
            f"({best_run[0][0]} to {best_run[-1][0]}) but SOC rose {soc_delta:.2f} pts "
            f"({soc_start} -> {soc_end}) -- looks like charging, not discharging")


def test_switching_site_updates_the_values(bolivia_monitoring_page):
    """[PCSENG-04] Changing the selected site must refetch and show that
    site's own Charge/Discharge Energy, not keep showing BOLIVIA's stale
    numbers under the new site's name."""
    pcs = bolivia_monitoring_page.pcs_energy_statistics()
    bolivia_values = (pcs.charge_energy_mwh(), pcs.discharge_energy_mwh())

    bolivia_monitoring_page.select_site("BOLIVIA 2")
    bolivia_monitoring_page.page.wait_for_timeout(1000)
    other_site_values = (pcs.charge_energy_mwh(), pcs.discharge_energy_mwh())
    bolivia_monitoring_page.select_site("BOLIVIA")

    assert bolivia_values != other_site_values, (
        f"expected BOLIVIA 2's Charge/Discharge Energy to differ from BOLIVIA's own "
        f"({bolivia_values}), got the same values for both sites: {other_site_values}")


def test_7d_and_30d_are_identical_because_site_history_is_only_7_days_old(bolivia_monitoring_page, db_conn):
    """NOT a defect: confirmed directly against monitoring.MonitoringStat
    that BOLIVIA's entire recorded history starts 2026-09-04 (~7 days of
    data total as of this writing) -- so a 30-day window can't contain any
    more data than a 7-day one already does. This test pins down WHY 7d
    and 30d show identical totals, so a future regression (the two windows
    suddenly differing incorrectly, or suddenly NOT differing once the
    site has >30 days of real history) gets caught either way."""
    from shared.datasource.db_source import get_site_ids
    site_id = get_site_ids(db_conn, [SITE_NAME])[SITE_NAME]
    with db_conn.cursor() as cur:
        cur.execute('SELECT min("BucketTimestamp") FROM monitoring."MonitoringStat" WHERE "SiteId" = %s', (site_id,))
        oldest = cur.fetchone()[0]

    from datetime import datetime, timezone
    site_age_days = (datetime.now(timezone.utc) - oldest).days

    pcs = bolivia_monitoring_page.pcs_energy_statistics()
    bolivia_monitoring_page.select_time_range("Last 7 days")
    bolivia_monitoring_page.page.wait_for_timeout(500)
    charge_7d, discharge_7d = pcs.charge_energy_mwh(), pcs.discharge_energy_mwh()

    bolivia_monitoring_page.select_time_range("Last 30 days")
    bolivia_monitoring_page.page.wait_for_timeout(500)
    charge_30d, discharge_30d = pcs.charge_energy_mwh(), pcs.discharge_energy_mwh()

    if site_age_days < 30:
        assert (charge_7d, discharge_7d) == (charge_30d, discharge_30d), (
            f"site history is only {site_age_days} days old (< 30d) -- expected 7d and 30d totals "
            f"to be identical, got 7d={(charge_7d, discharge_7d)} vs 30d={(charge_30d, discharge_30d)}")
    else:
        pytest.skip(f"site history is now {site_age_days} days old (>= 30d) -- 7d/30d are no longer "
                    f"expected to match; see test_longer_windows_accumulate_at_least_as_much_as_shorter_ones instead")
