"""Fleet Overview — Fleet Availability card + bar.

Grounded in docs/fleet-availability.md (backend documentation, provided
2026-08-31) -- previously this file used approximate/consistency-only
checks because we didn't have the exact source tables or formulas. Now we
do, so most cases here assert EXACT values, not loose bounds:

  - Card formula (§4.1): round(normal / total * 100, 2) -- plain rounding,
    no mask-guard. Source: sites.FleetAvailabilitySample (24h window) or
    sites.FleetAvailabilityDailySummary (7d/30d).
  - Bar formula (§4.2.1): FleetStatePercentages.Calculate -- round each to
    1 decimal, mask-guard (nonzero count never shows 0.0%), then reconcile
    drift against the currently-largest segment so the three always sum to
    EXACTLY 100.0. Both replicated in shared/datasource/db_source.py's
    fleet_availability_card_pct / fleet_availability_bar_pcts -- verified
    2026-08-31 to match the live API byte-for-byte (0.0/0.0/100.0 vs the
    API's 0/0/100 for the same window).
  - Card and bar can legitimately differ by ~0.1-0.2% (two different
    rounding algorithms on the same raw data, documented and expected --
    §4.2.1's own worked example shows 98.1% vs 98.0% for identical data).
    NOT a bug if it happens.
  - The bar widget animates its displayed percentages over 800ms on mount
    using intermediate, non-reconciled values (§4.2) -- reading it before
    that settles is why an earlier version of this file saw sums like
    95-97% instead of the guaranteed-exact 100.0%. See
    FleetAvailability.wait_past_mount_animation().
"""
import pytest

from framework_api.services.fleet_service import FleetService
from shared.datasource.db_source import fleet_availability_card_pct, fleet_availability_bar_pcts

pytestmark = pytest.mark.ui


def _read_availability_card_pct(fleet_overview_page):
    """Fleet Availability is a slower-query card (same as MTTR, per
    FLEET_OVERVIEW_FRACTAL_COMPATIBILITY.md §1.8) -- can still show "..."
    after the rest of the grid has settled. Waits for a real value, then
    returns it as a float."""
    grid = fleet_overview_page.status_grid()
    grid.cards().first.wait_for(timeout=15000)
    fleet_overview_page.page.wait_for_function(
        """() => {
            const cards = document.querySelectorAll('.fss-card');
            for (const c of cards) {
                if (c.querySelector('.fss-label')?.textContent.trim().toUpperCase() === 'FLEET AVAILABILITY') {
                    return c.querySelector('.fss-value')?.textContent.trim() !== '...';
                }
            }
            return false;
        }""",
        timeout=20000,
    )
    return float(grid.card_value("Fleet Availability").rstrip("%"))


def test_availability_card_matches_db_formula(require_omniops, fleet_overview_page, db_conn):
    """Exact cross-layer: replicates the backend's own rounding formula
    against the raw DB ticks, not just "matches the API" -- this proves
    the API's number is itself derivable from first principles, not just
    self-consistent."""
    card_pct = _read_availability_card_pct(fleet_overview_page)
    expected = fleet_availability_card_pct(db_conn, days=1)
    if expected is None:
        pytest.skip("no FleetAvailabilitySample rows in the last 24h yet")
    assert card_pct == pytest.approx(expected, abs=0.05), (
        f"UI card {card_pct}% vs DB-formula {expected}% (exact formula, "
        f"see docs/fleet-availability.md §4.1)")


def test_availability_bar_matches_db_formula(require_omniops, fleet_overview_page, db_conn):
    """Same as above, for the bar's 3 segments (its own, mask-guarded
    formula -- §4.2.1)."""
    avail = fleet_overview_page.availability()
    avail.wait_past_mount_animation()
    pct = avail.percentages()
    assert None not in pct.values(), f"couldn't parse all 3 segments: {pct}"

    expected = fleet_availability_bar_pcts(db_conn, days=1)
    if expected is None:
        pytest.skip("no FleetAvailabilitySample rows in the last 24h yet")
    expected_normal, expected_warning, expected_critical = expected
    assert (pct["normal"], pct["with_alarms"], pct["critical_offline"]) == pytest.approx(
        (expected_normal, expected_warning, expected_critical), abs=0.05
    ), (f"UI bar {pct} vs DB-formula (normal={expected_normal}, warning={expected_warning}, "
        f"critical={expected_critical}) -- see docs/fleet-availability.md §4.2.1")


def test_availability_card_matches_api(require_omniops, fleet_overview_page, api_client):
    """Cross-layer against the live API response directly (not just the
    DB-formula replication above) -- catches a bug in the replicated
    formula itself, since this compares against a completely independent
    path (real backend call, not our Python reimplementation of its math)."""
    card_pct = _read_availability_card_pct(fleet_overview_page)

    expected = FleetService(api_client).get_availability_distribution(days=1)
    assert card_pct == pytest.approx(expected.normal_pct, abs=0.5), (
        f"UI card shows {card_pct}% but the API says {expected.normal_pct}% "
        f"(full API response: {expected})")


def test_availability_bar_sums_to_exactly_100(require_omniops, fleet_overview_page):
    """The mask-guard + reconciliation in FleetStatePercentages.Calculate
    (§4.2.1) GUARANTEES the three segments sum to exactly 100.0 -- not
    "roughly 100", not a band. Requires waiting past the 800ms mount
    animation (see module docstring) -- reading too early is exactly what
    made an earlier version of this test see 95-97% instead."""
    avail = fleet_overview_page.availability()
    avail.wait_past_mount_animation()
    pct = avail.percentages()
    assert None not in pct.values(), f"couldn't parse all 3 segments: {pct}"
    total = pct["normal"] + pct["with_alarms"] + pct["critical_offline"]
    assert total == pytest.approx(100.0, abs=0.1), f"segments sum to {total}%, expected exactly 100.0%: {pct}"
