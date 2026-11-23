"""Fleet Overview — scaffolding smoke test: log in, open the page, confirm it
rendered. Needs the live stack (OmniOps + login); skipped offline via
require_omniops, same convention as the other UI/cross_layer tests."""
import pytest

pytestmark = pytest.mark.ui


def test_fleet_overview_loads(require_omniops, fleet_overview_page):
    assert not fleet_overview_page.is_on_login()
    grid = fleet_overview_page.status_grid()
    # the KPI cards render async (~10s after the shell), so wait for the
    # first one instead of asserting the count immediately
    grid.cards().first.wait_for(timeout=15000)
    assert grid.cards().count() > 0
