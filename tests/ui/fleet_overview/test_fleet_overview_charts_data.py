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
from datetime import datetime, timedelta, timezone

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


@pytest.mark.parametrize("range_label, hours", [("Last 7 days", 168), ("Last 30 days", 720)])
def test_subsystem_distribution_matches_db_for_range(
        require_omniops, api_client, db_conn, all_site_ids, range_label, hours):
    """Same check as test_subsystem_distribution_matches_db above, extended
    to 7d/30d -- closes a gap flagged 2026-09-16: Qase cases #287/#288
    ("Distribution by system shows exact 7D/30D percentages") had been Not
    Automated/muted. Fleet-wide and hours-parametrized directly against
    GET /api/events/analytics/subsystem-distribution?hours=, same as the
    24h version above -- there's still no reliable DOM data to scrape for
    this canvas-rendered chart regardless of range (see this module's own
    docstring), so proving the underlying data is correct for 7d/30d is
    the same kind of check the 24h case already makes, not a lesser one."""
    expected = count_alarms_by_subsystem_windowed(db_conn, all_site_ids, hours=hours)
    actual_rows = EventsService(api_client).get_subsystem_distribution(hours=hours)
    actual = {row["name"]: row["value"] for row in actual_rows}
    assert actual == expected, f"[{range_label}] API subsystem distribution {actual} vs DB {expected}"


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


@pytest.mark.parametrize("range_label, hours", [("Last 7 days", 168), ("Last 30 days", 720)])
def test_hourly_distribution_critical_sum_matches_db_for_range(
        require_omniops, api_client, db_conn, all_site_ids, range_label, hours):
    """Same check as test_hourly_distribution_critical_sum_matches_db above,
    extended to 7d/30d (daily buckets past 24h, see
    test_hourly_distribution_day_label_is_local_not_utc) -- closes a gap
    flagged 2026-09-16: Qase cases #285/#286 ("Histogram renders 7D/30D
    with filter Time range") had been Not Automated/muted since 2026-09-03.
    Same coarse-sum, fleet-wide, windowed reasoning as the 24h version."""
    rows = EventsService(api_client).get_hourly_distribution(hours=hours)
    actual_total_critical = sum(row["critical"] for row in rows)
    expected_total_critical = count_critical_alarms_windowed(db_conn, all_site_ids, hours=hours)
    assert actual_total_critical == expected_total_critical, (
        f"[{range_label}] sum of bucket 'critical' values ({actual_total_critical}) vs "
        f"DB Critical count ({expected_total_critical})")


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


@pytest.mark.parametrize("hours, range_label", [(168, "7d"), (720, "30d")])
@pytest.mark.xfail(
    strict=True,
    reason="CONFIRMED DEFECT (2026-09-15, Qase Defects #37/#38 -- same root "
           "cause as #36/test_hourly_distribution_hour_label_is_local_not_utc "
           "above, a 7d/30d occurrence of it): for the wide-window ranges, "
           "GET /api/events/analytics/hourly-distribution's 'hour' field is a "
           "DAY label (e.g. '09 Sep') instead of an hour label, one bucket "
           "per UTC calendar day at timestamp T00:00:00Z. The frontend "
           "displays this label as-is, verbatim in UTC, instead of "
           "converting to the browser's local day -- confirmed live "
           "(offset=240 min, America/La_Paz): every single bucket's label is "
           "exactly 1 day AHEAD of the correct local calendar day (e.g. "
           "timestamp 2026-09-09T00:00:00Z, labeled '09 Sep', but that "
           "instant is still '08 Sep' 20:00 in the browser's local time).")
def test_hourly_distribution_day_label_is_local_not_utc(require_omniops, api_client, logged_in_page, hours, range_label):
    """[Fleet Overview scalability] Same check as the 24h hour-label test
    above, extended to the 7d/30d "day label" format -- one parametrized
    test instead of duplicating the whole body per range, per
    docs/PR_CORRECTIONS.md's spirit of small, reusable, DRY test code."""
    rows = EventsService(api_client).get_hourly_distribution(hours=hours)
    assert rows, f"[{range_label}] expected at least 1 daily bucket"

    offset_min = logged_in_page.evaluate("() => new Date().getTimezoneOffset()")

    mismatches = []
    for row in rows:
        utc_dt = datetime.fromisoformat(row["timestamp"].replace("Z", "+00:00")).astimezone(timezone.utc)
        local_dt = utc_dt - timedelta(minutes=offset_min)
        expected_label = f"{local_dt.day:02d} {local_dt.strftime('%b')}"
        if row["hour"] != expected_label:
            mismatches.append((row["timestamp"], row["hour"], expected_label))

    assert not mismatches, (
        f"[{range_label}] expected each bucket's day label to reflect the LOCAL "
        f"calendar day for its UTC timestamp (offset {offset_min} min), found "
        f"buckets still labeled in raw UTC: {mismatches[:5]}")
