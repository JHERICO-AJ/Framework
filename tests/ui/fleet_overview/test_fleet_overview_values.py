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
between two test sessions on 2026-08-28, when a colleague added her own).
We never send telemetry to any non-BOLIVIA site, so they always stay
Offline -- but the exact TOTAL keeps changing, so it's read live from the
DB (count_all_sites) instead of hardcoded.

One test per KPI card/chip -- each fails independently, same pattern as
test_fleet_overview_structural.py.

CROSS-LAYER vs FIXED: nearly everything here is CROSS-LAYER (read the real
value from the DB via db_conn + shared/datasource/db_source.py, then assert
the UI shows that same value) rather than a hardcoded guess, because two
things we don't control keep changing the "expected" number:
  1. The simulator sends randomized telemetry per tick (confirmed by the
     team, same as EPC), and known config gaps (DC Bus Overvoltage
     threshold left at the 900V factory default vs. the simulator's
     constant 1200V; the Comm Lost bitfield never reading "connected")
     mean BOLIVIA alarms fire almost immediately after a reset, not just
     from randomness -- confirmed 2026-08-28 (26 Critical alarms across
     all 6 sites within ~2 min of a fresh, cleaned start).
  2. The fleet is shared -- other people's sites come and go, so the total
     site count isn't ours to hardcode either.
Only ONLINE_BOLIVIA_SITES stays fixed: that's a fact about OUR test
environment (we know exactly which 6 sites we feed telemetry to).
"""
import pytest

from shared.datasource.db_source import (
    count_all_sites,
    get_site_ids,
    count_critical_alarms,
    count_sites_with_alarms,
    count_sites_requiring_attention,
)

pytestmark = pytest.mark.ui

ONLINE_BOLIVIA_SITES = 6     # all 6 BOLIVIA sites healthy after a fresh sim start + reset
BOLIVIA_SITE_NAMES = ["BOLIVIA", "BOLIVIA 1", "BOLIVIA 2", "BOLIVIA 3", "BOLIVIA 4", "BOLIVIA 5"]


@pytest.fixture(scope="session")
def bolivia_site_ids(db_conn):
    return list(get_site_ids(db_conn, BOLIVIA_SITE_NAMES).values())


@pytest.fixture(scope="session")
def total_fleet_sites(db_conn):
    return count_all_sites(db_conn)


def test_connected_sites_matches_db(require_omniops, fleet_overview_page, total_fleet_sites):
    """Only the 6 BOLIVIA sites ever receive telemetry, so online count is
    fixed at 6 -- but the TOTAL is read live since the fleet is shared and
    other people's site count changes without notice."""
    grid = fleet_overview_page.status_grid()
    assert grid.card_value("CONNECTED SITES") == f"{ONLINE_BOLIVIA_SITES} / {total_fleet_sites}"


def test_online_rate_matches_db(require_omniops, fleet_overview_page, total_fleet_sites):
    grid = fleet_overview_page.status_grid()
    expected_pct = round(100 * ONLINE_BOLIVIA_SITES / total_fleet_sites, 1)
    assert grid.card_value("ONLINE RATE") == f"{expected_pct}%"


def test_reporting_sites_chip_matches_connected(require_omniops, fleet_overview_page):
    """Reporting Sites chip uses the same <=120s criterion as Connected
    Sites (confirmed in FLEET_OVERVIEW_FRACTAL_COMPATIBILITY.md §1.9.2)."""
    grid = fleet_overview_page.status_grid()
    assert grid.chip_value(1) == str(ONLINE_BOLIVIA_SITES)


def test_total_sites_chip_matches_db(require_omniops, fleet_overview_page, total_fleet_sites):
    grid = fleet_overview_page.status_grid()
    assert grid.chip_value(0) == str(total_fleet_sites)


def test_sites_requiring_attention_matches_db(require_omniops, fleet_overview_page, db_conn, bolivia_site_ids):
    """Cross-layer: whatever the UI shows must match the real count in
    events.Alert -- NOT hardcoded to 0, since known config gaps (DC Bus
    Overvoltage threshold, stuck Comm Lost bit) mean BOLIVIA rarely stays
    alarm-free for long (see module docstring)."""
    grid = fleet_overview_page.status_grid()
    expected = count_sites_requiring_attention(db_conn, bolivia_site_ids)
    assert grid.card_value("SITES REQUIRING ATTENTION") == str(expected)


def test_critical_alarms_matches_db(require_omniops, fleet_overview_page, db_conn, bolivia_site_ids):
    grid = fleet_overview_page.status_grid()
    expected = count_critical_alarms(db_conn, bolivia_site_ids)
    assert grid.card_value("CRITICAL ALARMS") == str(expected)


def test_sites_with_alarms_matches_db(require_omniops, fleet_overview_page, db_conn, bolivia_site_ids):
    grid = fleet_overview_page.status_grid()
    expected = count_sites_with_alarms(db_conn, bolivia_site_ids)
    assert grid.card_value("SITES WITH ALARMS") == str(expected)


def test_update_time_chip_is_populated(require_omniops, fleet_overview_page):
    """Not an exact value (it's a live timestamp) -- just confirms it's not
    the placeholder ("—") once telemetry is flowing."""
    grid = fleet_overview_page.status_grid()
    assert grid.chip_value(2) not in ("", "—", "-")
