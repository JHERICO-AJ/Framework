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

from shared.datasource.db_source import get_site_ids, top_sites_by_alarms, top_critical_causes

pytestmark = pytest.mark.ui

BOLIVIA_SITE_NAMES = ["BOLIVIA", "BOLIVIA 1", "BOLIVIA 2", "BOLIVIA 3", "BOLIVIA 4", "BOLIVIA 5"]


@pytest.fixture(scope="session")
def bolivia_site_ids(db_conn):
    return list(get_site_ids(db_conn, BOLIVIA_SITE_NAMES).values())


def test_top_sites_by_alarms_matches_db(require_omniops, fleet_overview_page, db_conn, bolivia_site_ids):
    expected = top_sites_by_alarms(db_conn, bolivia_site_ids)
    actual = fleet_overview_page.alarms_analytics().top_sites_by_alarms()
    # Only compare the BOLIVIA sites we track -- the table may include rows
    # for other sites in the shared fleet that we don't feed telemetry to.
    actual_bolivia = {name: value for name, value in actual.items() if name in BOLIVIA_SITE_NAMES}
    assert actual_bolivia == expected


def test_top_critical_causes_matches_db(require_omniops, fleet_overview_page, db_conn, bolivia_site_ids):
    expected = top_critical_causes(db_conn, bolivia_site_ids)
    actual = fleet_overview_page.alarms_analytics().top_critical_causes()
    assert actual == expected
