"""Fleet Overview — Sites List, per-row exact-value cases.

Same cross-layer principle as test_fleet_overview_values.py for MOST cases
here: read the real value from the DB at test time via db_conn +
shared/datasource/db_source.py, then assert the Sites List row shows that
same value -- not a hardcoded guess, since the simulator's telemetry is
randomized per tick.

POWER -- not DB-based (see below for why), covered end-to-end across 3
layers so a mismatch points at WHICH layer broke, not just "Power is
wrong":
  1. test_power_is_present_and_in_plausible_range: no ground truth needed,
     always runs.
  2. test_power_updates_over_time: liveness only, not an exact-value check.
  3. test_power_matches_recent_simulator_history: simulator -> UI, TRUE
     cross-layer, reading the live value directly off the Fractal
     simulator over Modbus TCP (see shared/datasource/fractal_modbus_source.py),
     bypassing OmniOps entirely.
  4. test_power_api_matches_recent_simulator_history: simulator -> API,
     same technique as #3 but against MonitoringService.get_summary()'s
     actualPcsPower instead of the UI -- confirmed 2026-09-01 to return
     real live BOLIVIA data (e.g. -1687.6 kW, fresh timestamp), not a
     placeholder like the ProcessedBessData table.
  5. test_power_ui_matches_api: UI -> API, direct comparison (no
     convergence window -- both are reads of the same already-ingested
     value). Together, #4 and #5 split "Power is correct end-to-end" into
     its two possible failure points: #4 catches a backend
     calculation/ingestion bug, #5 catches a UI-rendering-specific bug.
  Needed because Fractal telemetry isn't persisted to any table we could
  find (RawBaseData, TelemetryReading, dataprocessing.ProcessedBessData.Power_kW
  are all empty for BOLIVIA even with the simulator running) -- same
  "CACHE — NOT COVERED" gap noted in tools/db/cleanup_site_data.sql, so the
  DB can't be the source of truth here. Reading the simulator sidesteps
  that gap: whatever it emits IS the ground truth, regardless of what's
  cached/persisted (or not) downstream. Needs launch_sites.py running for
  BOLIVIA -- skips (not fails) if the simulator isn't reachable.

Most cases use ONE site (BOLIVIA) -- sufficient to prove the mechanism
works; the ranking-style cases (Fleet Alarms Analytics "Top sites") are
what actually benefit from having all 6 online. The 3 Power cross-layer
tests are the exception: parametrized across all 6 BOLIVIA sites (see
ALL_BOLIVIA_SITE_NAMES below), since Power is the one column whose "ground
truth" comes from a per-site Modbus connection (FRACTAL_SITE_MODBUS) --
each site is a genuinely separate wire, so one passing doesn't prove the
other 5 do.
"""
import time

import pytest

from framework_api.services.monitoring_service import MonitoringService
from shared.config.settings import POWER_MIN_KW, POWER_MAX_KW, TOL_ABS_KW, FRACTAL_SITE_MODBUS
from shared.datasource.db_source import (
    get_site_ids, count_critical_alarms, count_critical_alarms_windowed,
    site_names_with_real_telemetry_history,
)
from shared.datasource.fractal_modbus_source import read_fractal_site_total_kw
from framework_ui.pages.fleet_overview.fleet_overview_page import FleetOverviewPage

pytestmark = pytest.mark.ui

SITE_NAME = "BOLIVIA"
ALL_BOLIVIA_SITE_NAMES = list(FRACTAL_SITE_MODBUS.keys())


@pytest.fixture(scope="session")
def site_id(db_conn):
    return get_site_ids(db_conn, [SITE_NAME])[SITE_NAME]


@pytest.fixture(scope="session")
def bolivia_site_ids(db_conn):
    """{site_name: site_id} for all 6 BOLIVIA sites -- used by the
    parametrized Power cross-layer tests below."""
    return get_site_ids(db_conn, ALL_BOLIVIA_SITE_NAMES)


@pytest.fixture
def site_row(fleet_overview_page):
    sites = fleet_overview_page.sites_list()
    row = sites.row_index_by_site_name(SITE_NAME)
    assert row is not None, f"{SITE_NAME!r} not found in the Sites List"
    return sites, row


def _row_for(fleet_overview_page, site_name):
    """Same lookup as the site_row fixture, but for an arbitrary site name
    -- used by the parametrized Power tests instead of the fixture, since a
    fixture can't take a per-test parameter as an argument."""
    sites = fleet_overview_page.sites_list()
    row = sites.row_index_by_site_name(site_name)
    assert row is not None, f"{site_name!r} not found in the Sites List"
    return sites, row


def test_power_is_present_and_in_plausible_range(require_omniops, site_row):
    """Not cross-layer (see module docstring) -- just confirms the cell
    isn't empty/a placeholder, and the number is physically plausible."""
    sites, row = site_row
    actual = sites.power_kw(row)
    assert actual is not None, "expected a real Power value, cell was empty/unparseable"
    assert POWER_MIN_KW <= actual <= POWER_MAX_KW, (
        f"Power {actual} kW is outside the plausible range "
        f"[{POWER_MIN_KW}, {POWER_MAX_KW}]")


POWER_FRESHNESS_WAIT_S = 45  # comfortably longer than simulator_tick_seconds (5s)


def test_power_updates_over_time(require_omniops, site_row):
    """Liveness check, not an exact-value check: with a randomized simulator
    re-ticking every ~5s, the Power cell should show a DIFFERENT value after
    a long-enough wait -- if it doesn't, the UI is frozen/stuck on a stale
    cached value, regardless of what that value's exact latency turns out to
    be (see test_power_matches_simulator's open item on that)."""
    sites, row = site_row
    before = sites.power_kw(row)
    assert before is not None, "expected a real Power value, cell was empty/unparseable"

    sites.page.wait_for_timeout(POWER_FRESHNESS_WAIT_S * 1000)

    after = sites.power_kw(row)
    assert after is not None, "Power cell went empty after the wait"
    assert after != before, (
        f"Power didn't change after waiting {POWER_FRESHNESS_WAIT_S}s "
        f"(stuck at {before} kW) -- looks frozen/stale, not live")


POWER_HISTORY_DURATION_S = 120   # how far back we're willing to look for a match
POWER_HISTORY_INTERVAL_S = 3     # < simulator_tick_seconds (5s), so we don't miss ticks
POWER_HISTORY_MAX_LATENCY_S = 300  # generous sanity ceiling -- not the real expected value


@pytest.mark.parametrize("site_name", ALL_BOLIVIA_SITE_NAMES)
def test_power_matches_recent_simulator_history(require_omniops, fleet_overview_page, site_name):
    """True cross-layer: the simulator's own p_ac_kw sum is the ground
    truth (see module docstring). Skips if the simulator isn't reachable.
    Runs once per BOLIVIA site (see module docstring for why Power
    specifically needs all 6, not just one).

    BUILDS A GROWING HISTORY of simulator samples AND re-reads the UI value
    on every loop iteration (not just once) -- test_power_updates_over_time
    already proved the UI genuinely updates over ~45-70s, so as time passes
    the UI's CURRENT value should eventually match a simulator sample
    that's now sitting in our history. A single live read or a short
    forward-only window (15s, tried first) both missed: the UI's value at
    test start was already older than the whole 15s window, which a
    fixed-in-time "actual" can never catch up to -- re-reading the UI each
    iteration is what makes this converge as both sides move forward.

    When it matches, the match's age (now minus that sample's timestamp) is
    the MEASURED real-world latency -- reported (not asserted tight) so it
    becomes actual evidence for the platform team instead of a guess. The
    assertion itself stays deliberately loose (latency < 5 min, just a
    sanity ceiling): the point isn't to gate on a latency number nobody's
    confirmed yet, it's to prove the UI's value is a REAL one the simulator
    actually sent recently (not garbage/a stuck value from a previous run),
    while measuring and reporting how stale it typically is."""
    sites, row = _row_for(fleet_overview_page, site_name)

    history = []  # [(wall_clock_time, value), ...]
    elapsed = 0
    while elapsed <= POWER_HISTORY_DURATION_S:
        try:
            sim_value = read_fractal_site_total_kw(site_name)
        except ConnectionError as e:
            pytest.skip(f"Fractal simulator for {site_name!r} not reachable: {e}")
        except KeyError as e:
            pytest.skip(str(e))
        history.append((time.monotonic(), sim_value))

        ui_value = sites.power_kw(row)
        assert ui_value is not None, "UI shows no power value at all"
        match = next((t for t, v in history if abs(v - ui_value) <= TOL_ABS_KW), None)
        if match is not None:
            latency_s = time.monotonic() - match
            print(f"\n[{site_name}] Measured UI->simulator latency for Power: ~{latency_s:.1f}s "
                  f"(UI={ui_value} kW matched a simulator sample from {latency_s:.1f}s ago)")
            assert latency_s <= POWER_HISTORY_MAX_LATENCY_S, (
                f"matched, but {latency_s:.1f}s is beyond the sanity ceiling "
                f"of {POWER_HISTORY_MAX_LATENCY_S}s -- likely a stale/stuck value")
            return

        sites.page.wait_for_timeout(POWER_HISTORY_INTERVAL_S * 1000)
        elapsed += POWER_HISTORY_INTERVAL_S

    pytest.fail(
        f"[{site_name}] UI power never matched any of the simulator's last "
        f"{POWER_HISTORY_DURATION_S}s of ticks ({len(history)} samples, "
        f"within {TOL_ABS_KW} kW) -- either latency exceeds that window, or "
        f"the UI value isn't real simulator data. Simulator samples: "
        f"{[v for _, v in history]}")


@pytest.mark.parametrize("site_name", ALL_BOLIVIA_SITE_NAMES)
def test_power_api_matches_recent_simulator_history(require_omniops, api_client, bolivia_site_ids, site_name):
    """Same convergence-window technique as
    test_power_matches_recent_simulator_history, but against the BACKEND's
    own calculated value (MonitoringService.get_summary().actual_pcs_power_kw,
    confirmed 2026-09-01 to return real live data for BOLIVIA -- e.g.
    -1687.6 kW with a fresh timestamp, not a placeholder) instead of what
    the UI displays. Together with test_power_ui_matches_api below, this
    splits "is Power correct end-to-end" into its two possible failure
    points: a mismatch HERE (API vs simulator) would mean the backend's own
    calculation/ingestion is wrong; a mismatch in test_power_ui_matches_api
    (UI vs API) would mean the backend is right but the UI renders it
    wrong. No browser needed -- pure API + Modbus. Runs once per BOLIVIA
    site."""
    site_id = bolivia_site_ids[site_name]
    history = []
    elapsed = 0
    while elapsed <= POWER_HISTORY_DURATION_S:
        try:
            sim_value = read_fractal_site_total_kw(site_name)
        except ConnectionError as e:
            pytest.skip(f"Fractal simulator for {site_name!r} not reachable: {e}")
        except KeyError as e:
            pytest.skip(str(e))
        history.append((time.monotonic(), sim_value))

        summary = MonitoringService(api_client).get_summary(site_id=site_id)
        api_value = summary.actual_pcs_power_kw
        if api_value is None:
            pytest.skip(f"API returned no actualPcsPower for {site_name!r}")
        match = next((t for t, v in history if abs(v - api_value) <= TOL_ABS_KW), None)
        if match is not None:
            latency_s = time.monotonic() - match
            print(f"\n[{site_name}] Measured API->simulator latency for Power: ~{latency_s:.1f}s "
                  f"(API={api_value} kW matched a simulator sample from {latency_s:.1f}s ago)")
            assert latency_s <= POWER_HISTORY_MAX_LATENCY_S, (
                f"matched, but {latency_s:.1f}s is beyond the sanity ceiling "
                f"of {POWER_HISTORY_MAX_LATENCY_S}s -- likely a stale/stuck value")
            return

        time.sleep(POWER_HISTORY_INTERVAL_S)
        elapsed += POWER_HISTORY_INTERVAL_S

    pytest.fail(
        f"[{site_name}] API actualPcsPower never matched any of the simulator's last "
        f"{POWER_HISTORY_DURATION_S}s of ticks ({len(history)} samples, "
        f"within {TOL_ABS_KW} kW) -- either backend latency exceeds that "
        f"window, or the backend's calculated value isn't real simulator "
        f"data. Simulator samples: {[v for _, v in history]}")


POWER_UI_API_RETRY_ATTEMPTS = 6
POWER_UI_API_RETRY_INTERVAL_S = 5


@pytest.mark.parametrize("site_name", ALL_BOLIVIA_SITE_NAMES)
def test_power_ui_matches_api(require_omniops, fleet_overview_page, api_client, bolivia_site_ids, site_name):
    """Direct UI-vs-backend comparison, no convergence window needed: unlike
    the simulator comparisons above (which have to hunt through a window of
    past ticks because of real ingestion latency), the UI and
    MonitoringService.get_summary() are two different READS of the same
    already-ingested backend value -- they should agree quickly if the UI
    is rendering correctly. A short retry loop absorbs the two sides
    polling on slightly different cadences; it does NOT excuse a genuine
    rendering bug, since that would keep failing across every attempt.
    Runs once per BOLIVIA site."""
    sites, row = _row_for(fleet_overview_page, site_name)
    site_id = bolivia_site_ids[site_name]
    ui_value = api_value = None
    for _attempt in range(POWER_UI_API_RETRY_ATTEMPTS):
        ui_value = sites.power_kw(row)
        api_value = MonitoringService(api_client).get_summary(site_id=site_id).actual_pcs_power_kw
        if ui_value is not None and api_value is not None and abs(ui_value - api_value) <= TOL_ABS_KW:
            return
        sites.page.wait_for_timeout(POWER_UI_API_RETRY_INTERVAL_S * 1000)

    pytest.fail(
        f"[{site_name}] UI Power ({ui_value} kW) never matched the backend's own "
        f"actualPcsPower ({api_value} kW) within {TOL_ABS_KW} kW across "
        f"{POWER_UI_API_RETRY_ATTEMPTS} tries -- backend has a value, UI "
        f"shows a different one: looks like a UI rendering bug specifically, "
        f"not a data-pipeline latency issue.")


def test_critical_column_matches_db(require_omniops, site_row, db_conn, site_id):
    """WINDOWED (hours=24), not the flat all-time count -- confirmed
    2026-09-15 this exact test was still comparing against the flat
    count_critical_alarms (its own docstring explicitly warns against
    that: "does NOT match what the UI shows, which is windowed by the
    Topbar's timeRange filter") despite the sibling windowing bug already
    being fixed elsewhere in this file. Live evidence: BOLIVIA had 9
    Critical alerts total, but 3 of them dated back to 2026-09-12 (outside
    the last 24h) -- the UI correctly showed 6, the flat count wrongly
    expected 9."""
    sites, row = site_row
    expected = count_critical_alarms_windowed(db_conn, [site_id], hours=24)
    assert sites.critical_count(row) == expected


def test_last_seen_is_populated_when_online(require_omniops, site_row):
    """Not an exact cross-layer value (it's a relative/live timestamp) --
    confirms it's not the "Never"/placeholder state once telemetry flows."""
    sites, row = site_row
    text = sites.last_seen_text(row)
    assert text not in ("", "—", "-", "Never"), f"expected a real Last Seen value, got {text!r}"


def test_last_seen_shows_real_time_not_never_when_offline(require_omniops, fleet_overview_page, db_conn):
    """Closes a gap flagged 2026-09-03: "Never" is only the CORRECT Last
    Seen value for a site that has NEVER received telemetry -- a site
    that WAS online before and is currently Offline (e.g. the simulator
    briefly disconnecting, a real and frequent occurrence in this
    environment) should still show the real elapsed time since its last
    telemetry, not reset to "Never".

    FLEET-WIDE, not scoped to ALL_BOLIVIA_SITE_NAMES -- confirmed
    2026-09-15 this is what makes the case reliably exercisable: we can't
    always guarantee one of OUR 6 sites happens to be Offline the moment
    this runs (e.g. all 6 online via the simulator), but a colleague's
    site elsewhere in the shared fleet often already is (KIRUNA, PALAWAN
    confirmed live 2026-09-15 to both be Offline for days while still
    carrying a real, non-null LastTelemetryAtUtc). Asserting against
    site_names_with_real_telemetry_history(db_conn) instead of a hardcoded
    site list is what lets this test scale to whichever site the fleet
    happens to have in that state, without needing to manually take one of
    ours offline for it. The legacy sites that predate the
    LastTelemetryAtUtc column entirely (Dallas BESS Alpha, lowercase
    Bolivia, Fractal Knapp QA-01/02/03, Frac SiteView, Fract2) are
    correctly excluded by that same DB check -- "Never" IS the correct
    value for them, so picking one of those here would be asserting the
    wrong thing."""
    sites = fleet_overview_page.sites_list()
    candidates = site_names_with_real_telemetry_history(db_conn)

    offline_row = None
    for name in candidates:
        row = sites.row_index_by_site_name(name)
        if row is not None and sites.status_text(row).strip().upper() == "OFFLINE":
            offline_row = (name, row)
            break

    if offline_row is None:
        pytest.skip("no site with real telemetry history is Offline right now -- "
                     "can't exercise the offline-with-history case")

    name, row = offline_row
    text = sites.last_seen_text(row)
    assert text.strip() != "Never", (
        f"{name!r} is Offline but has definitely received telemetry before "
        f"(LastTelemetryAtUtc IS NOT NULL) -- Last Seen should show the real "
        f"elapsed time, not 'Never'")


def test_status_column_matches_db_when_critical(require_omniops, site_row, db_conn, site_id):
    """Confirmed gap closed 2026-08-31: the Status pill TEXT was never
    cross-layer verified before (only Critical, Power, Last Seen were).
    Per the status-derivation order (FLEET_OVERVIEW_FRACTAL_COMPATIBILITY.md
    §2.1/§3.2: offline > Critical alert active > Warning > online), if the
    DB has a Critical alert open for this site, the pill MUST read
    "Critical" -- can't test the reverse (0 alerts -> "Online") as cleanly
    here since that also requires confirming recent telemetry, which
    test_last_seen_is_populated_when_online already covers separately."""
    sites, row = site_row
    critical_count = count_critical_alarms(db_conn, [site_id])
    if critical_count == 0:
        pytest.skip(f"{SITE_NAME!r} has 0 Critical alerts right now -- "
                     "can't assert the Critical-status case")
    assert sites.status_text(row).strip().upper() == "CRITICAL", (
        f"DB shows {critical_count} Critical alert(s) for {SITE_NAME!r}, "
        f"but the Status pill doesn't say Critical")


LAPTOP_VIEWPORT = {"width": 1366, "height": 768}


@pytest.mark.xfail(
    strict=True,
    reason="CONFIRMED DEFECT (2026-09-16, Qase Defect TBD). The 'Power "
           "(kW)' column header uses white-space: nowrap + text-overflow: "
           "clip (not ellipsis, no wrap) with a fixed-width cell that "
           "doesn't grow with its content -- fine at the 1920x1080 "
           "automation-default viewport (a typical external monitor), but "
           "at common laptop resolutions the cell narrows along with "
           "everything else and the header text no longer fits, silently "
           "clipping the '(KW)' suffix (confirmed live: cell needs 86px, "
           "gets only 57px at 1366x768). Reported by the user after "
           "noticing '(kW)' was cut off on a laptop screen but fine on an "
           "external monitor -- not an OS display-scaling artifact, "
           "reproduced here at the DOM/CSS level in a clean headless "
           "browser.")
def test_power_column_header_not_clipped_on_laptop_viewport(require_omniops, logged_in_page):
    """Confirmed 2026-09-16 this reproduces at every common laptop
    resolution tried (1366x768, 1536x864, 1280x800) -- 1366x768 is used
    here as the representative case. Restores the session-scoped page's
    viewport afterward so later tests still run at the 1920x1080
    BrowserFactory default they assume (see its own docstring on why that
    size matters for the Fleet Map)."""
    original_viewport = logged_in_page.viewport_size
    try:
        logged_in_page.set_viewport_size(LAPTOP_VIEWPORT)
        fleet = FleetOverviewPage(logged_in_page).open()
        sites = fleet.sites_list()
        assert not sites.header_is_clipped("POWER (KW)"), (
            f"'Power (kW)' column header is clipped at {LAPTOP_VIEWPORT} "
            f"-- part of the label (the '(KW)' unit) is invisible")
    finally:
        logged_in_page.set_viewport_size(original_viewport)
