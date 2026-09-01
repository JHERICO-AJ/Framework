"""Fleet Overview — Fleet Alarms Analytics' 2 ECharts CANVAS charts, RENDERED
content this time (not just their underlying API data, already covered by
test_fleet_overview_charts_data.py).

A canvas has no readable DOM for its drawing -- confirmed permanent, not
worth chasing further (see docs/CLAUDE_CODE_CONTEXT.md). But hovering a
data point opens ECharts' own tooltip, which IS plain HTML with real text
-- discovered 2026-09-01 by inspecting the live page. `FleetAlarmsAnalytics.
scan_hourly_chart()`/`scan_subsystem_pie()` sweep the chart area, read
whatever tooltip text appears at each point, and parse it. This lets us
assert the actual PIXELS someone hovers over say the same thing the API
says -- the closest thing to a pixel-level check these 2 charts allow.

scan_subsystem_pie() grid-sweeps the whole canvas box rather than assuming
a ring geometry -- confirmed via screenshot 2026-09-01 that the donut
isn't centered in its own canvas (a legend occupies part of the box), so
an angle/radius sweep around an assumed center missed the smaller slice.
"""
import pytest

from framework_api.services.events_service import EventsService
from shared.datasource.db_source import get_site_ids
from shared.datasource.db_source import count_alarms_by_subsystem

pytestmark = pytest.mark.ui

BOLIVIA_SITE_NAMES = ["BOLIVIA", "BOLIVIA 1", "BOLIVIA 2", "BOLIVIA 3", "BOLIVIA 4", "BOLIVIA 5"]


def test_hourly_chart_tooltips_match_api(require_omniops, fleet_overview_page, api_client):
    """Hovers across the bar chart; for every hour where a tooltip actually
    appeared, its Critical/Major/Minor values must match the API's own
    numbers for that hour. Doesn't require finding all 24 (bar rendering
    can leave gaps a sweep step misses) -- but whatever IS found must
    agree, and at least some bars must be found at all."""
    analytics = fleet_overview_page.alarms_analytics()
    tooltip_by_hour = analytics.scan_hourly_chart()
    assert tooltip_by_hour, "the tooltip scan found no bars at all -- chart not rendering as expected?"

    api_by_hour = {row["hour"]: row for row in EventsService(api_client).get_hourly_distribution(hours=24)}

    mismatches = []
    for hour, tooltip_values in tooltip_by_hour.items():
        expected = api_by_hour.get(hour)
        if expected is None:
            mismatches.append(f"{hour!r}: tooltip shows this hour, API has no matching bucket")
            continue
        for severity in ("critical", "major", "minor"):
            if tooltip_values.get(severity) != expected[severity]:
                mismatches.append(
                    f"{hour!r} {severity}: tooltip={tooltip_values.get(severity)} API={expected[severity]}")
    assert not mismatches, "\n".join(mismatches)


def test_subsystem_pie_tooltips_match_api(require_omniops, fleet_overview_page, api_client):
    """Hovers around the pie/donut; every subsystem the API reports must
    show up somewhere in the sweep, with the same count and the same
    displayed percentage (matched by count, not by name -- the pie's
    display names, e.g. "PCS / Inverter", are a frontend-side relabeling
    of the API's raw keys, e.g. "TRANSFORMER_PCS", with no confirmed
    mapping to assert against directly)."""
    analytics = fleet_overview_page.alarms_analytics()
    tooltip_by_name = analytics.scan_subsystem_pie()
    assert tooltip_by_name, "the tooltip scan found no pie slices at all -- chart not rendering as expected?"

    api_rows = EventsService(api_client).get_subsystem_distribution(hours=24)
    total = sum(row["value"] for row in api_rows)

    tooltip_counts_found = {count for count, _pct in tooltip_by_name.values()}
    mismatches = []
    for row in api_rows:
        if row["value"] not in tooltip_counts_found:
            mismatches.append(f"API subsystem {row['name']!r} (count={row['value']}) not found in any tooltip: {tooltip_by_name}")
            continue
        expected_pct = round(row["value"] / total * 100, 2)
        actual_pct = next(pct for count, pct in tooltip_by_name.values() if count == row["value"])
        if abs(actual_pct - expected_pct) > 0.01:
            mismatches.append(
                f"API subsystem {row['name']!r}: tooltip%={actual_pct} expected%={expected_pct}")
    assert not mismatches, "\n".join(mismatches)


def test_subsystem_pie_tooltip_counts_sum_matches_db(require_omniops, fleet_overview_page, db_conn):
    """A further cross-layer hop past the API: the tooltip counts read
    straight off the canvas must sum to the same total as a raw DB count
    of BOLIVIA alarms by subsystem for the same window -- proving the
    rendered pixels, not just the API response, agree with the DB."""
    analytics = fleet_overview_page.alarms_analytics()
    tooltip_by_name = analytics.scan_subsystem_pie()
    assert tooltip_by_name, "the tooltip scan found no pie slices at all"

    site_ids = list(get_site_ids(db_conn, BOLIVIA_SITE_NAMES).values())
    expected = count_alarms_by_subsystem(db_conn, site_ids)

    actual_total = sum(count for count, _pct in tooltip_by_name.values())
    expected_total = sum(expected.values())
    assert actual_total == expected_total, (
        f"sum of tooltip-read subsystem counts ({actual_total}) vs DB total ({expected_total})")
