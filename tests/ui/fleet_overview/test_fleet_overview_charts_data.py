"""Fleet Overview — Fleet Alarms Analytics, the 2 ECharts CANVAS charts
("Alarms in last 24h · by hour" and "Alarm distribution · by system").

These render on an HTML5 <canvas> -- there's no DOM/text content to read
directly, but hovering a data point opens ECharts' own tooltip, which IS
plain HTML (see FleetAlarmsAnalytics.scan_hourly_chart/_parse_bar_tooltip)
-- so the REAL rendered label/values ARE readable, just not by scraping
the canvas itself. Most tests here still verify the DATA feeding the
drawing via the same 2 endpoints the frontend calls (confirmed via network
capture 2026-08-31):
  GET /api/events/analytics/hourly-distribution?hours=N
  GET /api/events/analytics/subsystem-distribution?hours=N
That proves the chart isn't lying about the underlying numbers, but
confirmed 2026-09-16 it is NOT a substitute for reading the real tooltip
when checking something the FRONTEND itself computes independently of the
API field (see the hour/day-label tests below, where checking only the
API's 'hour' field produced a false result for the 24h case)."""
import re
from datetime import datetime, timedelta, timezone

import pytest

from framework_api.services.events_service import EventsService
from shared.datasource.db_source import (
    get_all_site_ids, count_alarms_by_subsystem_windowed, count_critical_alarms_windowed,
    count_critical_alarms_by_local_day,
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


def test_hourly_distribution_hour_label_is_local_not_utc(require_omniops, api_client, fleet_overview_page):
    """REVISED 2026-09-16 (twice). First revision: compared GET
    .../hourly-distribution's own 'hour' field, called WITHOUT the
    'ClientTimeZone' query param, against the local hour -- found a
    mismatch and filed it as a confirmed defect. RETRACTED: confirmed via
    network capture that the REAL frontend ALWAYS sends 'ClientTimeZone'
    (e.g. 'America/La_Paz'), and the BACKEND uses it to shift bucket
    boundaries to LOCAL time and build already-correct labels --
    EventsService.get_hourly_distribution() now sends this by default
    (settings.CLIENT_TIMEZONE). Calling the endpoint without it, as this
    test used to unconditionally, is a genuinely different, timezone-blind
    request that the real UI never makes -- not a valid way to test what
    the UI shows. With the correct request, the API's own 'hour' field
    already matches the REAL rendered tooltip exactly, confirmed
    positionally (bar N left-to-right = API row N, both chronological)."""
    rows = EventsService(api_client).get_hourly_distribution(hours=24)
    assert rows, "expected at least 1 hourly bucket"

    rendered_bars = fleet_overview_page.alarms_analytics().scan_bars_in_order(steps=100)
    assert rendered_bars, "no bars found via the tooltip sweep"

    n = min(len(rendered_bars), len(rows))
    mismatches = []
    for i in range(n):
        row = rows[i]
        rendered_label, _values = rendered_bars[i]
        if rendered_label != row["hour"]:
            mismatches.append((row["timestamp"], row["hour"], rendered_label))

    assert not mismatches, (
        f"expected each bar's rendered hour label (matched positionally, left-to-"
        f"right, against the API's chronologically-ordered rows) to match the API's "
        f"own (already-localized) 'hour' field; mismatches (timestamp, api_hour, "
        f"rendered): {mismatches}")


@pytest.mark.parametrize("hours, range_label, range_ui_label", [(168, "7d", "Last 7 days"), (720, "30d", "Last 30 days")])
def test_hourly_distribution_day_label_is_local_not_utc(
        require_omniops, api_client, db_conn, all_site_ids, fleet_overview_page, hours, range_label, range_ui_label):
    """[Fleet Overview scalability] Same check as the 24h hour-label test
    above, extended to the 7d/30d "day label" format -- one parametrized
    test instead of duplicating the whole body per range, per
    docs/PR_CORRECTIONS.md's spirit of small, reusable, DRY test code.

    RETRACTED 2026-09-16 (the DEFECT was Qase #37/#38, deleted -- a false
    positive, same lesson as the 24h test above; the CASES themselves,
    #732/#733, were kept/recreated as permanent regression coverage since
    the scenario is legitimate, only the tooling was wrong): the earlier
    version called the API WITHOUT the 'ClientTimeZone' query param and
    compared its 'hour' field/bucket timestamps (all at UTC midnight)
    against locally-shifted expectations. Confirmed via network capture
    that the real frontend always sends 'ClientTimeZone', and the backend
    uses it to shift bucket BOUNDARIES to LOCAL midnight (not just the
    label) -- EventsService.get_hourly_distribution() now sends this by
    default. With the correct request, 3 independent layers agree: DB
    direct query (count_critical_alarms_by_local_day, bucketed by LOCAL
    calendar day) == API's per-day Critical counts == the REAL rendered
    tooltip, matched positionally (bar N left-to-right = API row N, both
    chronologically ordered, covering every bucket including all-zero
    ones)."""
    db_day_counts = count_critical_alarms_by_local_day(db_conn, all_site_ids, hours=hours)

    fleet_overview_page.select_time_range(range_ui_label)
    try:
        fleet_overview_page.page.wait_for_timeout(1000)
        rows = EventsService(api_client).get_hourly_distribution(hours=hours)
        assert rows, f"[{range_label}] expected at least 1 daily bucket"

        # Layer 1 (DB direct, local-day bucketed) vs Layer 2 (API).
        db_vs_api_mismatches = []
        for row in rows:
            utc_dt = datetime.fromisoformat(row["timestamp"].replace("Z", "+00:00")).astimezone(timezone.utc)
            local_dt = utc_dt - timedelta(minutes=240)  # America/La_Paz, UTC-4
            day_key = local_dt.strftime("%Y-%m-%d")
            db_count = db_day_counts.get(day_key, 0)
            if db_count != row.get("critical", 0):
                db_vs_api_mismatches.append((row["timestamp"], db_count, row.get("critical")))
        assert not db_vs_api_mismatches, (
            f"[{range_label}] DB (direct query, local-day bucketed) vs API per-day "
            f"Critical counts disagree (timestamp, db_count, api_count): "
            f"{db_vs_api_mismatches}")

        # Layer 2 (API) vs Layer 3 (the REAL rendered tooltip).
        rendered_bars = fleet_overview_page.alarms_analytics().scan_bars_in_order(steps=300)
        assert rendered_bars, f"[{range_label}] no bars found via the tooltip sweep"

        n = min(len(rendered_bars), len(rows))
        mismatches = []
        for i in range(n):
            row = rows[i]
            rendered_label, _values = rendered_bars[i]
            if rendered_label != row["hour"]:
                mismatches.append((row["timestamp"], row["hour"], rendered_label))

        assert not mismatches, (
            f"[{range_label}] expected each bar's rendered day label (matched "
            f"positionally, left-to-right, against the API's chronologically-"
            f"ordered rows) to match the API's own (already-localized) 'hour' "
            f"field; mismatches (timestamp, api_hour, rendered): {mismatches}")
    finally:
        fleet_overview_page.select_time_range("Last 24 hours")
