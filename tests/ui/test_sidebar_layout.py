"""Global Navigation & Layout -- the app's sidebar (present on every page,
not owned by any single business module). Confirmed against the real
deployed app 2026-09-22: the real DOM structure differs from the older
client-approved demo (the internal QA note 'OmniOps_Phase1_Demo10_V09') -- the demo's
plain `.sidebar-footer` (holding only the "Logged in as" block) is now a
larger container that ALSO holds a "Sites Status" list above it; the
"Logged in as" block itself lives in the real app at `.sidebar-user-info`.
"""
import pytest

pytestmark = pytest.mark.ui

LAPTOP_VIEWPORT = {"width": 1366, "height": 768}


def test_sidebar_user_info_not_clipped_on_laptop_viewport(fleet_overview_page):
    """CONFIRMED FIXED 2026-09-30 (Qase Defect #66): re-verified at 1366x768
    -- the sidebar's user-info block no longer extends past the sidebar's
    own visible bottom edge, so the scope tag and Local Time lines are no
    longer clipped. xfail removed.

    Originally: confirmed 2026-09-22 this reproduces at the representative laptop
    resolution already established elsewhere in this suite for the same
    class of viewport-height/width clipping defect (Fleet Overview's
    'Power (kW)' header, Alarm History's Time/Device overlap). Uses
    `fleet_overview_page` (not the raw `logged_in_page`) so the app shell
    -- including the sidebar under test -- has genuinely finished loading
    before the viewport is resized; the sidebar is global chrome, so which
    module's page this fixture lands on doesn't matter. Restores the
    session-scoped page's viewport afterward so later tests still run at
    the 1920x1080 BrowserFactory default they assume."""
    page = fleet_overview_page.page
    original_viewport = page.viewport_size
    try:
        page.set_viewport_size(LAPTOP_VIEWPORT)
        page.wait_for_timeout(500)

        aside = page.locator("aside").first
        user_info = page.locator(".sidebar-user-info")
        assert user_info.count() > 0, "expected a '.sidebar-user-info' block in the sidebar"

        aside_box = aside.bounding_box()
        user_info_box = user_info.bounding_box()
        aside_visible_bottom = aside_box["y"] + aside_box["height"]
        user_info_bottom = user_info_box["y"] + user_info_box["height"]

        assert user_info_bottom <= aside_visible_bottom + 1, (
            f"the sidebar's 'Logged in as' user-info block (bottom edge at "
            f"{user_info_bottom:.0f}px) extends past the sidebar's own visible "
            f"bottom edge ({aside_visible_bottom:.0f}px) at {LAPTOP_VIEWPORT} -- "
            f"part of it (the scope tag / Local Time lines) is clipped off, not "
            f"scrollable, since the sidebar uses overflow-y: hidden")
    finally:
        page.set_viewport_size(original_viewport)
