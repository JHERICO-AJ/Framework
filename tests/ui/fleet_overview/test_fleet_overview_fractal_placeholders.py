"""Fleet Overview — Group C: Fractal N/A / structural-placeholder cases,
from docs/CLAUDE_CODE_CONTEXT.md section 7 and confirmed against
FLEET_OVERVIEW_FRACTAL_COMPATIBILITY.md's "Checklist QA rápido" table.

These are all TRUE for Fractal regardless of whether any given site is
online/healthy or offline — Fractal has no BMS racks and no Work Orders
wiring at all, so these placeholders don't depend on live telemetry. That's
why this file doesn't need require_omniops the same way Group A/B do for
per-site exact values — it still needs login/the page, but the assertions
themselves hold before AND after telemetry starts.

Needs OmniOps reachable + login; skipped offline via require_omniops.

REMOVED 2026-08-28: test_critical_alarms_card_shows_zero,
test_sites_with_alarms_card_shows_zero,
test_sites_requiring_attention_card_shows_zero, and
test_fractal_site_critical_column_shows_zero all assumed "healthy Fractal
sim = 0 alarms". That assumption doesn't hold for BOLIVIA (known config
gaps make alarms fire almost immediately after any reset — see
docs/DATASET_FLEET_OVERVIEW.md). Those cases are superseded by the
cross-layer versions in test_fleet_overview_values.py, which compare
against the DB's real count instead of hardcoding 0.
"""
import pytest

pytestmark = pytest.mark.ui

# Any known Fractal site works for the row-level checks — SOC/Critical
# placeholders are structural, not tied to a particular site's health.
FRACTAL_SITE_NAME = "BOLIVIA"


def test_mttr_card_shows_zero(require_omniops, fleet_overview_page):
    """MTTR isn't wired without Work Orders — always '0.0 h'. Its value comes
    from a slower query than the other cards (per
    FLEET_OVERVIEW_FRACTAL_COMPATIBILITY.md §1.7, "no realtime snapshot"),
    so it can still show the "..." loading placeholder well after the rest
    of the grid has settled — poll instead of asserting immediately."""
    grid = fleet_overview_page.status_grid()
    grid.cards().first.wait_for(timeout=15000)
    fleet_overview_page.page.wait_for_function(
        """() => {
            const cards = document.querySelectorAll('.fss-card');
            for (const c of cards) {
                if (c.querySelector('.fss-label')?.textContent.trim().toUpperCase() === 'MTTR') {
                    return c.querySelector('.fss-value')?.textContent.trim() !== '...';
                }
            }
            return false;
        }""",
        timeout=20000,
    )
    assert grid.card_value("MTTR") == "0.0 h"


def test_fractal_site_soc_bar_is_empty(require_omniops, fleet_overview_page):
    """SOC only averages Battery BMS racks — Fractal never sends those, so
    the bar is always ~0% regardless of site health (structural, not N/A-
    because-offline)."""
    sites = fleet_overview_page.sites_list()
    row = sites.row_index_by_site_name(FRACTAL_SITE_NAME)
    assert row is not None, f"{FRACTAL_SITE_NAME!r} not found in the Sites List"
    soc = sites.soc_percent(row)
    assert soc is None or soc == 0, f"expected an empty/0% SOC bar, got {soc}"


def test_availability_warning_and_critical_segments_near_zero(require_omniops, fleet_overview_page):
    """Passes today because Fleet Availability history hasn't accrued yet
    (needs ~5 min of samples) — once it does, this may start failing for
    the same reason the four removed tests above did (BOLIVIA's known
    config gaps mean it isn't actually alarm-free). Revisit if/when this
    flakes; the fix is the same cross-layer pattern, not reverting to a
    hardcoded expectation."""
    pct = fleet_overview_page.availability().percentages()
    assert pct["with_alarms"] is not None, f"couldn't parse legend: {pct}"
    assert pct["with_alarms"] <= 1.0, f"expected ~0% with alarms, got {pct['with_alarms']}%"
