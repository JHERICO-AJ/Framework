"""SiteViewPage -- Site View - Single Site screen. Delegates sections to
their own components (only Recent Alarms is modeled so far -- add more as
needed, same pattern as MonitoringPage/FleetOverviewPage)."""
from __future__ import annotations

from framework_ui.base.base_page import BasePage
from framework_ui.pages.site_view import site_view_locators as loc
from framework_ui.pages.site_view.components.recent_alarms import RecentAlarms


class SiteViewPage(BasePage):
    PATH = "/site?timeRange=24h"

    def open(self):
        """Deliberately NOT calling self.goto(): same SPA deep-link
        limitation already documented for FleetOverviewPage/MonitoringPage
        -- navigate via the sidebar link from wherever the page currently
        is instead."""
        self.page.get_by_role("link", name=loc.SIDEBAR_LINK_TEXT).click()
        self.page.locator(loc.LOADED_MARKER).first.wait_for(timeout=20000)
        return self

    def select_site(self, name):
        self.page.locator(loc.SITE_SELECT).first.select_option(label=name)
        self.page.locator(loc.LOADED_MARKER).first.wait_for(timeout=20000)
        return self

    def recent_alarms(self) -> RecentAlarms:
        return RecentAlarms(self.page)
