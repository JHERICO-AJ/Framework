"""Fleet Overview — Group B: exact-value cases for Fleet Status Summary,
from docs/DATASET_FLEET_OVERVIEW.md and FLEET_OVERVIEW_FRACTAL_COMPATIBILITY.md.

Needs OmniOps reachable + login (require_omniops), a DB connection (db_conn
-- see .env.example), AND the 6 BOLIVIA sites in a known baseline: telemetry
reporting recently (<=120s) and events/alerts cleaned via
tools/db/cleanup_bolivia_data.sql before the session (see that script's
docstring for the manual reset steps -- this is a pre-condition, not
something these tests provision themselves).

IMPORTANT: the Fleet Status Summary cards aggregate the WHOLE fleet, not
just the 6 BOLIVIA sites -- confirmed this fleet is SHARED with other
teams/people who add sites without notice (went from 9 to 13 total sites
between two test sessions on 2026-08-28, when a colleague added her own;
and on 2026-09-02, a colleague's site (KIRUNA) came online with its own
real alerts, breaking an earlier version of this file that assumed only
BOLIVIA ever contributes alarms/online sites).

CROSS-LAYER vs FIXED: nearly everything here is CROSS-LAYER (read the real
value from the DB via db_conn + shared/datasource/db_source.py, then assert
the UI shows that same value) rather than a hardcoded guess, because
several things we don't control keep changing the "expected" number:
  1. The simulator sends randomized telemetry per tick (confirmed by the
     team, same as EPC), and known config gaps (DC Bus Overvoltage
     threshold left at the 900V factory default vs. the simulator's
     constant 1200V; the Comm Lost bitfield never reading "connected")
     mean BOLIVIA alarms fire almost immediately after a reset, not just
     from randomness -- confirmed 2026-08-28 (26 Critical alarms across
     all 6 sites within ~2 min of a fresh, cleaned start).
  2. The fleet is shared -- other people's sites come and go, so the total
     site count isn't ours to hardcode, and neither is the alarm/online
     activity coming from THEIR sites.

The alarm-count cards (Sites Requiring Attention, Critical Alarms, Sites
with Alarms) are read against ALL sites in the DB (get_all_site_ids), not
just BOLIVIA's -- see get_all_site_ids's docstring for why the
BOLIVIA-only version broke.

Connected Sites / Online Rate / Reporting Sites are trickier: "online"
requires a live telemetry-recency check we can't independently reconstruct
fleet-wide from the DB (Fractal telemetry specifically isn't persisted
anywhere queryable -- see fractal_modbus_source.py's docstring), so we
can't compute an exact expected online count for sites we don't control.
What we DO know for certain: all 6 BOLIVIA sites are online (proven
elsewhere, e.g. test_fleet_overview_sites_list_values.py's Power tests) --
so these assert our own known contribution is present (>= 6) and that the
three related UI numbers (Connected Sites, Online Rate, Reporting Sites)
are internally consistent with each other, rather than hardcoding what
other teams' sites are doing right now.
"""
import re

import pytest

from shared.datasource.db_source import (
    count_all_sites,
    get_all_site_ids,
    count_critical_alarms_windowed,
    count_sites_with_alarms_windowed,
    count_sites_requiring_attention,
)

pytestmark = pytest.mark.ui

MIN_ONLINE_BOLIVIA_SITES = 6  # our own known contribution -- proven elsewhere, not assumed


@pytest.fixture(scope="session")
def all_site_ids(db_conn):
    return get_all_site_ids(db_conn)


@pytest.fixture(scope="session")
def total_fleet_sites(db_conn):
    return count_all_sites(db_conn)


def _parse_connected_sites(card_text):
    """"7 / 9" -> (7, 9)."""
    match = re.match(r"(\d+)\s*/\s*(\d+)", card_text)
    assert match, f"couldn't parse Connected Sites card: {card_text!r}"
    return int(match.group(1)), int(match.group(2))


def test_connected_sites_matches_db(require_omniops, fleet_overview_page, total_fleet_sites):
    """The TOTAL is cross-layer (read live from the DB, since the fleet is
    shared and the total changes without notice). The ONLINE count can't be
    computed independently fleet-wide (see module docstring), so this only
    asserts our own known minimum (6) is included, not an exact value."""
    grid = fleet_overview_page.status_grid()
    online, total = _parse_connected_sites(grid.card_value("CONNECTED SITES"))
    assert total == total_fleet_sites, f"total sites: UI={total} DB={total_fleet_sites}"
    assert online >= MIN_ONLINE_BOLIVIA_SITES, (
        f"expected at least our {MIN_ONLINE_BOLIVIA_SITES} known-online BOLIVIA sites, UI shows {online}")


def test_online_rate_matches_db(require_omniops, fleet_overview_page):
    """Internal consistency: Online Rate must match Connected Sites' own
    ratio (X/Y) -- not an independent cross-layer value, since we can't
    reconstruct the true fleet-wide online count ourselves (see module
    docstring)."""
    grid = fleet_overview_page.status_grid()
    online, total = _parse_connected_sites(grid.card_value("CONNECTED SITES"))
    expected_pct = round(100 * online / total, 1)
    assert grid.card_value("ONLINE RATE") == f"{expected_pct}%"


def test_reporting_sites_chip_matches_connected(require_omniops, fleet_overview_page):
    """Reporting Sites chip uses the same <=120s criterion as Connected
    Sites (confirmed in FLEET_OVERVIEW_FRACTAL_COMPATIBILITY.md §1.9.2) --
    so it must equal Connected Sites' own online count, whatever that is."""
    grid = fleet_overview_page.status_grid()
    online, _total = _parse_connected_sites(grid.card_value("CONNECTED SITES"))
    assert grid.chip_value(1) == str(online)


def test_total_sites_chip_matches_db(require_omniops, fleet_overview_page, total_fleet_sites):
    grid = fleet_overview_page.status_grid()
    assert grid.chip_value(0) == str(total_fleet_sites)


@pytest.mark.xfail(
    strict=True,
    reason="CONFIRMED DEFECT (2026-09-16, Qase Defect TBD, same one as "
           "test_sites_requiring_attention_ignores_time_range below). "
           "REVISED per the developer (2026-09-16): this card's 'current' "
           "badge means it must show the flat/CURRENT count of sites with an "
           "open alert (count_sites_requiring_attention, not windowed by any "
           "range) -- alerts never auto-close, so 'flat' and 'current' are "
           "the same thing here. The previous version of this test compared "
           "against count_sites_requiring_attention_windowed(hours=24), which "
           "coincidentally passed because the UI's OWN bug (silently "
           "following the Topbar filter like Sites with Alarms does) made it "
           "match that wrong formula at the default 24h range -- confirmed "
           "live the flat/true value is 11, but the card showed 6 at 24h.")
def test_sites_requiring_attention_matches_db(require_omniops, fleet_overview_page, db_conn, all_site_ids):
    """Cross-layer, fleet-wide, FLAT/CURRENT (not windowed) -- see this
    test's xfail reason above for why the previous windowed(hours=24)
    comparison was itself hiding the bug."""
    grid = fleet_overview_page.status_grid()
    expected = count_sites_requiring_attention(db_conn, all_site_ids)
    assert grid.card_value("SITES REQUIRING ATTENTION") == str(expected)


def test_critical_alarms_matches_db(require_omniops, fleet_overview_page, db_conn, all_site_ids):
    """Windowed (hours=24) -- see test_sites_requiring_attention_matches_db."""
    grid = fleet_overview_page.status_grid()
    expected = count_critical_alarms_windowed(db_conn, all_site_ids, hours=24)
    assert grid.card_value("CRITICAL ALARMS") == str(expected)


def test_sites_with_alarms_matches_db(require_omniops, fleet_overview_page, db_conn, all_site_ids):
    """Windowed (hours=24) -- see test_sites_requiring_attention_matches_db."""
    grid = fleet_overview_page.status_grid()
    expected = count_sites_with_alarms_windowed(db_conn, all_site_ids, hours=24)
    assert grid.card_value("SITES WITH ALARMS") == str(expected)


def test_update_time_chip_is_populated(require_omniops, fleet_overview_page):
    """Not an exact value (it's a live timestamp) -- just confirms it's not
    the placeholder ("—") once telemetry is flowing."""
    grid = fleet_overview_page.status_grid()
    assert grid.chip_value(2) not in ("", "—", "-")


@pytest.mark.parametrize("range_label, hours", [("Last 7 days", 168), ("Last 30 days", 720)])
def test_history_kpi_cards_match_db_for_range(
        require_omniops, fleet_overview_page, db_conn, all_site_ids, range_label, hours):
    """Extends test_critical_alarms_matches_db / test_sites_with_alarms_matches_db
    above to 7d/30d, driven through the REAL UI time-range selector -- Qase
    case #260 ("Range switch recomputes the history KPIs to exact values").
    Fleet Availability already has its own dedicated 7d/30d coverage in
    test_fleet_overview_availability.py (Qase case #283) -- not repeated
    here. Sites Requiring Attention is DELIBERATELY NOT checked here --
    per the developer (2026-09-16), it's a CURRENT-state card (badge=
    "current", see test_status_grid_time_badges_current_vs_range) and must
    NOT change with the Topbar range at all; see
    test_sites_requiring_attention_ignores_time_range below for that
    (currently-failing) case instead."""
    fleet_overview_page.select_time_range(range_label)
    try:
        fleet_overview_page.page.wait_for_timeout(1000)
        grid = fleet_overview_page.status_grid()

        expected_critical = count_critical_alarms_windowed(db_conn, all_site_ids, hours=hours)
        assert grid.card_value("CRITICAL ALARMS") == str(expected_critical), (
            f"[{range_label}] Critical Alarms")

        expected_with_alarms = count_sites_with_alarms_windowed(db_conn, all_site_ids, hours=hours)
        assert grid.card_value("SITES WITH ALARMS") == str(expected_with_alarms), (
            f"[{range_label}] Sites with Alarms")
    finally:
        fleet_overview_page.select_time_range("Last 24 hours")


@pytest.mark.parametrize("range_label", ["Last 7 days", "Last 30 days"])
@pytest.mark.xfail(
    strict=True,
    reason="CONFIRMED DEFECT (2026-09-16, Qase Defect TBD). Sites Requiring "
           "Attention carries a 'current' badge (not a '24H/7D/30D' range "
           "badge, confirmed by test_status_grid_time_badges_current_vs_range) "
           "and per the developer (2026-09-16) is meant to show the CURRENT "
           "fleet state -- unaffected by the Topbar's time-range filter, the "
           "same as Connected Sites/Online Rate/MTTR. Instead it silently "
           "follows the filter exactly like Sites with Alarms does: confirmed "
           "live the DB's flat/current count (11 sites with an open alert --"
           "alerts never auto-close, so flat IS current) stays 11 regardless "
           "of range, but the card itself showed 6 at 24h, 9 at 7d, 11 at "
           "30d -- tracking the SAME windowed query as Sites with Alarms "
           "instead of staying fixed at the current value.")
def test_sites_requiring_attention_ignores_time_range(
        require_omniops, fleet_overview_page, db_conn, all_site_ids, range_label):
    """Per the developer's clarification (2026-09-16): the 'current' badge
    on this card means its value should be the CURRENT fleet state, not
    reactive to the Topbar's 24h/7d/30d filter -- so it must show the SAME
    value at 24h and at this range."""
    grid = fleet_overview_page.status_grid()
    fleet_overview_page.select_time_range("Last 24 hours")
    fleet_overview_page.page.wait_for_timeout(1000)
    current_value = grid.card_value("SITES REQUIRING ATTENTION")

    fleet_overview_page.select_time_range(range_label)
    try:
        fleet_overview_page.page.wait_for_timeout(1000)
        assert grid.card_value("SITES REQUIRING ATTENTION") == current_value, (
            f"Sites Requiring Attention changed from {current_value!r} at 24h to "
            f"{grid.card_value('SITES REQUIRING ATTENTION')!r} at {range_label!r} -- "
            f"it should stay at the CURRENT value regardless of the selected range")
    finally:
        fleet_overview_page.select_time_range("Last 24 hours")
