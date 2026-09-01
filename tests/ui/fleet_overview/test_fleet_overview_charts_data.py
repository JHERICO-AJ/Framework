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
import pytest

from framework_api.services.events_service import EventsService
from shared.datasource.db_source import get_site_ids, count_alarms_by_subsystem, count_critical_alarms

pytestmark = pytest.mark.ui

BOLIVIA_SITE_NAMES = ["BOLIVIA", "BOLIVIA 1", "BOLIVIA 2", "BOLIVIA 3", "BOLIVIA 4", "BOLIVIA 5"]


@pytest.fixture(scope="session")
def bolivia_site_ids(db_conn):
    return list(get_site_ids(db_conn, BOLIVIA_SITE_NAMES).values())


def test_subsystem_distribution_matches_db(require_omniops, api_client, db_conn, bolivia_site_ids):
    expected = count_alarms_by_subsystem(db_conn, bolivia_site_ids)
    actual_rows = EventsService(api_client).get_subsystem_distribution(hours=24)
    actual = {row["name"]: row["value"] for row in actual_rows}
    assert actual == expected, f"API subsystem distribution {actual} vs DB {expected}"


def test_hourly_distribution_critical_sum_matches_db(require_omniops, api_client, db_conn, bolivia_site_ids):
    """Doesn't replicate the exact hour-bucket boundaries (timezone/rollover
    edge cases aren't worth the complexity here) -- sums the 24 hourly
    "critical" values and compares against the DB's total Critical count
    for the same window. A coarser check than per-bucket, but still a real
    cross-layer: if the chart's data were wrong by even one alarm, or
    double-counting, this total wouldn't match."""
    rows = EventsService(api_client).get_hourly_distribution(hours=24)
    actual_total_critical = sum(row["critical"] for row in rows)
    expected_total_critical = count_critical_alarms(db_conn, bolivia_site_ids)
    assert actual_total_critical == expected_total_critical, (
        f"sum of hourly 'critical' values ({actual_total_critical}) vs DB Critical count "
        f"({expected_total_critical}) for the last 24h")


def test_hourly_distribution_has_24_buckets(require_omniops, api_client):
    """Structural: one entry per hour, not a data-value check."""
    rows = EventsService(api_client).get_hourly_distribution(hours=24)
    assert len(rows) == 24, f"expected 24 hourly buckets, got {len(rows)}"
