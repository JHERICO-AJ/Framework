"""Data & Monitoring: navigation OUT to any other module freezes whenever
a 7D/30D range filter is active, regardless of where that filter was set.

Discovered from a user-recorded screen capture (2026-09-16), then
precisely isolated live. The user's own clarification, confirmed exactly:
switching to a 7D/30D range and moving between the OTHER 3 modules
(Fleet Overview, Alarms & Events, Site View) works fine -- it's
specifically LEAVING Data & Monitoring that freezes, whenever it's
carrying a non-24h range (however it got there).

Confirmed live 2026-09-16 with this exact sequence:
  1. Fleet Overview -> switch range to "Last 7 days" (a 401 fires on
     GET /api/ExternalUserAuth/me right after, the session/token check
     endpoint -- but this is NOT required again later).
  2. Navigate to Alarms & Events (filter carries via ?timeRange=7d in the
     URL) -- loads fine.
  3. Navigate to Data & Monitoring (filter still carries) -- loads fine.
  4. Click ANY other sidebar module (tested with Fleet Overview) -- the
     URL updates (e.g. to /fleet?timeRange=7d), but the page's RENDERED
     CONTENT never updates -- it stays frozen showing Data & Monitoring's
     own content ("Device Status Panel" etc.) indefinitely. No new 401
     needs to fire at this exact moment -- whatever broke when the range
     was first switched stays broken specifically for leaving Data &
     Monitoring.

Confirmed in the original recording this lasted 38+ seconds until a
manual page reload (F5), which then loads the destination module
correctly.
"""
import re

import pytest

pytestmark = pytest.mark.ui


@pytest.mark.parametrize("range_label", ["Last 7 days", "Last 30 days"])
def test_leaving_monitoring_freezes_with_day_range_active(require_omniops, fleet_overview_page, range_label):
    """CONFIRMED DEFECT 2026-09-16 (Qase Defect #65, critical): once a
    7D/30D range was active (set anywhere), moving between Fleet Overview
    / Alarms & Events / Site View worked fine, but navigating OUT of Data
    & Monitoring to any other module froze: the URL updated but the
    page's rendered content stayed stuck on Data & Monitoring's own
    content ('Device Status Panel'), the destination module's own content
    never appeared. Confirmed via a user screen recording (38+ seconds
    stuck, fixed only by a manual reload). FIXED as of 2026-09-21
    (re-verified after the JF/FixMonitoring deploy, matching
    the internal QA note 'MnitoringFix' section 10's live-update fix) -- for both 7d and
    30d."""
    fleet_overview_page.select_time_range(range_label)
    fleet_overview_page.page.wait_for_timeout(2000)

    fleet_overview_page.page.get_by_role("link", name=re.compile("Alarms & Events", re.I)).click()
    fleet_overview_page.page.wait_for_timeout(2000)

    fleet_overview_page.page.get_by_role("link", name=re.compile("Data & Monitoring", re.I)).click()
    fleet_overview_page.page.wait_for_timeout(2000)
    assert fleet_overview_page.page.locator("text=Device Status Panel").count() > 0, (
        f"[{range_label}] Data & Monitoring itself didn't load correctly -- can't "
        f"test leaving it")

    fleet_overview_page.page.get_by_role("link", name=re.compile("Fleet Overview", re.I)).click()
    fleet_overview_page.page.wait_for_timeout(3000)

    url_says_fleet = "/fleet" in fleet_overview_page.page.url
    stuck_on_monitoring = fleet_overview_page.page.locator("text=Device Status Panel").count() > 0
    real_fleet_loaded = fleet_overview_page.page.locator("text=Fleet Status Summary").count() > 0

    try:
        assert not (url_says_fleet and stuck_on_monitoring and not real_fleet_loaded), (
            f"[{range_label}] navigation froze leaving Data & Monitoring: the URL "
            f"changed to Fleet Overview ({fleet_overview_page.page.url!r}) but the "
            f"page is still showing Data & Monitoring's own content, and Fleet "
            f"Overview's 'Fleet Status Summary' heading never appeared")
    finally:
        if not real_fleet_loaded:
            fleet_overview_page.page.reload()
            fleet_overview_page.page.wait_for_timeout(2000)
