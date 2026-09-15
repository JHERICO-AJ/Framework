"""Fleet Overview — Fleet Alarms Analytics, cross-layer cases.

Originally marked out of scope on the assumption that a "healthy Fractal
sim" would leave these tables empty (nothing to assert). That assumption
doesn't hold for BOLIVIA (known config gaps mean alarms are basically always
present -- see docs/DATASET_FLEET_OVERVIEW.md), so these ARE testable now,
same cross-layer pattern as test_fleet_overview_values.py: read the real
value from the DB, assert the UI table shows the same thing.

The section's 2 ECharts canvases (hourly time series, distribution pie) are
NOT covered here -- no reliable DOM data to scrape for a canvas-rendered
chart, unlike the 2 real HTML tables this file does cover.
"""
import pytest

from shared.datasource.db_source import (
    get_site_ids,
    get_all_site_ids,
    top_sites_by_alarms_windowed,
    top_critical_causes_windowed,
)

pytestmark = pytest.mark.ui

BOLIVIA_SITE_NAMES = ["BOLIVIA", "BOLIVIA 1", "BOLIVIA 2", "BOLIVIA 3", "BOLIVIA 4", "BOLIVIA 5"]


@pytest.fixture(scope="session")
def bolivia_site_ids(db_conn):
    return list(get_site_ids(db_conn, BOLIVIA_SITE_NAMES).values())


@pytest.fixture(scope="session")
def all_site_ids(db_conn):
    return get_all_site_ids(db_conn)


def test_top_sites_by_alarms_matches_db(require_omniops, fleet_overview_page, db_conn, bolivia_site_ids):
    """Windowed (hours=24): this panel reads
    GET /api/events/analytics/top-sites?hours= (docs/OF-344.txt), same
    Topbar-driven window as the KPI cards, and the page loads with
    ?timeRange=24h (fleet_overview_page.py PATH) -- so the flat, all-time
    top_sites_by_alarms would undercount whenever an alert's LastOccurred
    has aged out of the 24h window (see
    test_top_critical_causes_matches_db's docstring for the full mechanism)."""
    expected = top_sites_by_alarms_windowed(db_conn, bolivia_site_ids, hours=24)
    actual = fleet_overview_page.alarms_analytics().top_sites_by_alarms()
    # Only compare the BOLIVIA sites we track -- the table may include rows
    # for other sites in the shared fleet that we don't feed telemetry to.
    # (Safe to scope this one to BOLIVIA only: each row IS a site name, so
    # filtering actual down to ours before comparing is exact -- unlike
    # top_critical_causes below, where a row is a CAUSE that other sites
    # could also be contributing to.)
    actual_bolivia = {name: value for name, value in actual.items() if name in BOLIVIA_SITE_NAMES}
    assert actual_bolivia == expected


def test_top_critical_causes_matches_db(require_omniops, fleet_overview_page, db_conn, all_site_ids):
    """Fleet-wide (all_site_ids), NOT scoped to BOLIVIA -- confirmed
    2026-09-02 this table aggregates the whole shared fleet, same as the
    Fleet Status Summary alarm cards (see test_fleet_overview_values.py's
    module docstring for the incident that surfaced this: a colleague's
    site, KIRUNA, started contributing real critical causes). Unlike
    top_sites_by_alarms above, a row here is a CAUSE, not a site name, so
    there's no clean way to filter the UI's rows down to "BOLIVIA's
    contribution only" -- comparing fleet-wide on both sides is the only
    correct comparison.

    WINDOWED (hours=24): this panel reads
    GET /api/events/analytics/critical-causes?hours= (docs/OF-344.txt),
    and the page loads with ?timeRange=24h (fleet_overview_page.py PATH).
    A flat, all-time count previously produced a false "UI undercounts by
    N" failure: OmniOps alerts never auto-close (docs/HOW_IT_WORKS.md §4),
    so an old alert (e.g. from a morning telemetry outage that stopped a
    site's PCS communication and never resumed) stays open in the DB
    forever, but its LastOccurred timestamp freezes at whenever the
    condition was last observed -- once that falls outside the last 24h,
    the real windowed endpoint correctly excludes it while a flat count
    still includes it. A time window can only ever REDUCE a count relative
    to the flat one (the windowed set is a subset), so this only explains
    the UI showing FEWER than the flat DB count, never MORE -- see
    fleet_overview_new_bug_critical_causes memory, where the UI shows 2
    MORE than the windowed DB truth for "PCS DC Bus Overvoltage" specifically,
    a mismatch this windowing fix cannot produce or hide.

    Tolerant of ties at the #5 boundary: confirmed 2026-09-02 that when two
    causes tie on count, our plain `ORDER BY count(*) DESC` (no secondary
    sort key) doesn't necessarily pick the same one the UI does -- neither
    side is "wrong" in that case, Postgres just doesn't guarantee an order
    among ties and we don't know the frontend's own tie-breaker. So instead
    of requiring the exact same 5 causes, this fetches a wider top-20 and
    checks: (1) every cause the UI shows has the right (count, sites) --
    catches real wrong-number bugs; (2) nothing with a STRICTLY higher
    count was left off the UI's list -- catches a real "wrong top 5" bug;
    ties at the boundary are allowed to differ."""
    wide_expected = top_critical_causes_windowed(db_conn, all_site_ids, hours=24, limit=20)
    actual = fleet_overview_page.alarms_analytics().top_critical_causes()

    wrong_values = {
        cause: (value, wide_expected.get(cause))
        for cause, value in actual.items()
        if wide_expected.get(cause) != value
    }
    assert not wrong_values, f"UI shows wrong (count, sites) for: {wrong_values}"

    if actual:
        min_shown_count = min(count for count, _sites in actual.values())
        missed = {
            cause: value for cause, value in wide_expected.items()
            if value[0] > min_shown_count and cause not in actual
        }
        assert not missed, f"causes with a strictly higher count than the UI's Top 5 are missing: {missed}"
