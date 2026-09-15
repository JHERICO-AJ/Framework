"""Fleet Overview — Fleet Alarms Analytics, the 2 ECharts CANVAS charts
("Alarms in last 24h · by hour" and "Alarm distribution · by system").

These render on an HTML5 <canvas> -- there's no DOM/text content for
Playwright (or any DOM-based tool) to read; a canvas is pixels, not
markup. That's a real, permanent limitation, not something worth chasing
further (see docs/CLAUDE_CODE_CONTEXT.md §6). What we CAN and DO verify:
the DATA feeding the drawing is correct, via the same 2 endpoints the
frontend calls (confirmed via network capture 2026-08-31):
  GET /api/events/analytics/hourly-distribution?hours=N
  GET /api/events/analytics/subsystem-distribution?hours=N
This doesn't prove the pixels are drawn correctly, but it proves the chart
isn't lying about the underlying numbers -- which is the part an operator
actually relies on.
"""
import re
from datetime import datetime, timezone

import pytest

from framework_api.services.events_service import EventsService
from shared.datasource.db_source import (
    get_all_site_ids, count_alarms_by_subsystem_windowed, count_critical_alarms_windowed,
)

pytestmark = pytest.mark.ui


@pytest.fixture(scope="session")
def all_site_ids(db_conn):
    return get_all_site_ids(db_conn)


def test_subsystem_distribution_matches_db(require_omniops, api_client, db_conn, all_site_ids):
    """Fleet-wide (all_site_ids) -- confirmed 2026-09-02 these analytics
    endpoints aggregate the whole shared fleet, same incident that
    surfaced the same issue for the Fleet Status Summary alarm cards (see
    test_fleet_overview_values.py's module docstring). WINDOWED (hours=24)
    to match what GET /api/events/analytics/subsystem-distribution?hours=
    actually computes -- the flat, all-time count previously produced a
    false "API undercounts" failure whenever an alert's LastOccurred had
    aged out of the 24h window (see fleet_overview_new_bug_critical_causes
    memory: a window can only ever REDUCE a flat count, never explain the
    API showing less than a flat count for any other reason)."""
    expected = count_alarms_by_subsystem_windowed(db_conn, all_site_ids, hours=24)
    actual_rows = EventsService(api_client).get_subsystem_distribution(hours=24)
    actual = {row["name"]: row["value"] for row in actual_rows}
    assert actual == expected, f"API subsystem distribution {actual} vs DB {expected}"


def test_hourly_distribution_critical_sum_matches_db(require_omniops, api_client, db_conn, all_site_ids):
    """Doesn't replicate the exact hour-bucket boundaries (timezone/rollover
    edge cases aren't worth the complexity here) -- sums the 24 hourly
    "critical" values and compares against the DB's total Critical count
    for the same window. A coarser check than per-bucket, but still a real
    cross-layer: if the chart's data were wrong by even one alarm, or
    double-counting, this total wouldn't match. Fleet-wide, same reasoning
    as test_subsystem_distribution_matches_db above. WINDOWED (hours=24),
    same rationale as that test -- the flat count produced a false failure."""
    rows = EventsService(api_client).get_hourly_distribution(hours=24)
    actual_total_critical = sum(row["critical"] for row in rows)
    expected_total_critical = count_critical_alarms_windowed(db_conn, all_site_ids, hours=24)
    assert actual_total_critical == expected_total_critical, (
        f"sum of hourly 'critical' values ({actual_total_critical}) vs DB Critical count "
        f"({expected_total_critical}) for the last 24h")


def test_hourly_distribution_has_24_buckets(require_omniops, api_client):
    """Structural: one entry per hour, not a data-value check."""
    rows = EventsService(api_client).get_hourly_distribution(hours=24)
    assert len(rows) == 24, f"expected 24 hourly buckets, got {len(rows)}"


@pytest.mark.xfail(
    strict=True,
    reason="CONFIRMED DEFECT (2026-09-11). NOTE: already reported "
           "independently by a teammate with her own test -- filed in Qase "
           "(case + defect + Test Run result) and in Jira. Kept here as our "
           "own suite's regression coverage, but do NOT re-file this one in "
           "Qase/Jira -- it would be a duplicate. Every platform screen with a "
           "time component (Event Log, Alarm History, Site Power Telemetry, "
           "Telemetry Data Table) has already been confirmed to render in "
           "the browser's LOCAL time, not raw UTC. This chart doesn't: "
           "GET /api/events/analytics/hourly-distribution's own 'hour' "
           "label (e.g. '16 h') matches its 'timestamp' field's raw UTC "
           "hour-of-day verbatim (timestamp '2026-09-10T16:00:00Z' -> hour "
           "'16 h') -- for a browser in America/La_Paz (UTC-4, confirmed "
           "live via getTimezoneOffset()=240), the correct local label for "
           "that same instant would be '12 h', not '16 h'. The frontend "
           "displays this 'hour' field as-is, so every bar in 'Alarms in "
           "last 24h - by hour' is mislabeled by the site's UTC offset.")
def test_hourly_distribution_hour_label_is_local_not_utc(require_omniops, api_client, logged_in_page):
    rows = EventsService(api_client).get_hourly_distribution(hours=24)
    assert rows, "expected at least 1 hourly bucket"

    offset_min = logged_in_page.evaluate("() => new Date().getTimezoneOffset()")

    mismatches = []
    for row in rows:
        utc_dt = datetime.fromisoformat(row["timestamp"].replace("Z", "+00:00")).astimezone(timezone.utc)
        expected_local_hour = (utc_dt.hour - offset_min // 60) % 24
        match = re.match(r"(\d{1,2})\s*h", row["hour"])
        assert match, f"unrecognized hour-bucket label format: {row['hour']!r}"
        actual_hour = int(match.group(1))
        if actual_hour != expected_local_hour:
            mismatches.append((row["timestamp"], row["hour"], expected_local_hour))

    assert not mismatches, (
        f"expected each bucket's 'hour' label to reflect the LOCAL hour for "
        f"its UTC timestamp (offset {offset_min} min), found buckets still "
        f"labeled in raw UTC: {mismatches[:5]}")
