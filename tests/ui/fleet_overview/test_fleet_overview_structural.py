"""Fleet Overview — Group A: stable/structural cases (no exact DB values
needed), from docs/CLAUDE_CODE_CONTEXT.md section 7.

Needs OmniOps reachable + login; skipped offline via require_omniops.

Selectors below are CONFIRMED against the real deployed app (2026-08-26),
not guesses — see each component's *_locators.py for how they were verified.
Two of the original 6 Group A cases are marked skip rather than asserted:
what they'd need to check couldn't be found/confirmed on this screen yet
(see the skip reasons) — asserting against a guess would be worse than
flagging it as an open question.
"""
import re

import pytest

pytestmark = pytest.mark.ui

# Confirmed real header order (2026-08-26). Raw HTML text is Title Case
# ("Site", "Status", ...) but CSS applies text-transform:uppercase, and
# .inner_text() returns the rendered (post-CSS) text — hence uppercase here.
EXPECTED_SITES_LIST_HEADERS = ["SITE", "STATUS", "CRITICAL", "SOC", "POWER (KW)", "LAST SEEN"]

# Confirmed real site names currently in the Sites List (2026-08-26): Bolivia,
# BOLIVIA, BOLIVIA 1-4, Dallas BESS Alpha, and "hhhh" (looks like leftover
# test debris, not one of the 5 Fractal sites — confirm/delete with the user
# before relying on the dataset being exactly 5 sites).
ANCHOR_SITE_NAME = "Dallas BESS Alpha"  # only site with a name confirmed non-Fractal/known


def test_sites_list_column_headers_order(require_omniops, fleet_overview_page):
    """Qase #18 — column headers render in the exact expected order."""
    headers = fleet_overview_page.sites_list().header_labels()
    assert headers == EXPECTED_SITES_LIST_HEADERS


def test_status_grid_time_badges_current_vs_range(require_omniops, fleet_overview_page):
    """Qase #11 — 4 KPI cards show a "CURRENT" badge, 4 show the "24H" badge."""
    grid = fleet_overview_page.status_grid()
    kinds = [grid.badge_kind(i) for i in range(grid.cards().count())]
    assert kinds.count("current") == 4, f"badges: {kinds}"
    assert kinds.count("range") == 4, f"badges: {kinds}"


def _rgb_channels(color):
    match = re.match(r"rgba?\((\d+),\s*(\d+),\s*(\d+)", color)
    assert match, f"couldn't parse computed color: {color!r}"
    return tuple(int(x) for x in match.groups())


def test_map_marker_warning_status_is_blue(require_omniops, fleet_overview_page):
    """Qase #13 — Warning-status markers are BLUE, not the usual yellow."""
    fmap = fleet_overview_page.map()
    marker = fmap.marker_by_status("warning")
    if marker is None:
        pytest.skip("no warning-status site right now (all sites are offline/critical) — "
                    "put one site in a Warning state to exercise this case")
    red, green, blue = _rgb_channels(fmap.marker_computed_color(marker))
    assert blue > red and blue > green, (
        f"warning marker isn't blue: rgb({red}, {green}, {blue})")


def test_map_marker_critical_status_is_red(require_omniops, fleet_overview_page):
    """Companion to the Warning=blue case above: Critical-status markers
    are RED. Suggested 2026-08-28 as a substitute case since no site is
    currently in pure Warning (all 6 BOLIVIA sites are Critical -- see
    docs/DATASET_FLEET_OVERVIEW.md's known config gaps), so this is
    exercised every run instead of only when a Warning site exists."""
    fmap = fleet_overview_page.map()
    marker = fmap.marker_by_status("critical")
    if marker is None:
        pytest.skip("no critical-status site right now")
    red, green, blue = _rgb_channels(fmap.marker_computed_color(marker))
    assert red > green and red > blue, (
        f"critical marker isn't red: rgb({red}, {green}, {blue})")


# Qase #14 (site info popup, open + dismiss) — RESOLVED 2026-08-31, see
# test_fleet_overview_map_popup.py. Earlier attempts here found nothing
# because of a narrow default viewport + clicking the marker's translucent
# halo instead of its solid dot, not because the feature was missing.


@pytest.mark.skip(reason=(
    "Confirmed with the user 2026-08-28: this case came from a newer demo "
    "build that had a different \"Sites List · Priority\" layout — that "
    "layout isn't the one deployed today (we're on the older Sites List). "
    "Permanently out of scope until/unless that newer layout ships; not a "
    "gap in our coverage of the current screen."))
def test_healthy_site_shows_no_active_alarms_badge(require_omniops, fleet_overview_page):
    """Qase #26 — "No active alarms" + "0 Critical" badge when a site is online."""


def test_fractal_na_fields_show_hyphen_placeholder(require_omniops, fleet_overview_page):
    """Qase #2 — a not-applicable/not-wired field shows a hyphen placeholder
    instead of a fabricated value. Confirmed real example (2026-08-26): the
    "OPEN WO" KPI card shows "—" (not wired for any site yet)."""
    grid = fleet_overview_page.status_grid()
    value = grid.card_value("OPEN WO")
    assert value in ("-", "—"), f"expected a hyphen placeholder, got {value!r}"
