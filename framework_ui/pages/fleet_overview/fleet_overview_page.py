"""FleetOverviewPage — Fleet Overview screen (fleet-wide KPIs for Fractal
sites). Delegates each of the 5 sections to its own component."""
from __future__ import annotations

from framework_ui.base.base_page import BasePage
from framework_ui.pages.fleet_overview import fleet_overview_locators as loc
from framework_ui.pages.fleet_overview.components.fleet_alarms_analytics import FleetAlarmsAnalytics
from framework_ui.pages.fleet_overview.components.fleet_availability import FleetAvailability
from framework_ui.pages.fleet_overview.components.fleet_map import FleetMap
from framework_ui.pages.fleet_overview.components.fleet_status_grid import FleetStatusGrid
from framework_ui.pages.fleet_overview.components.sites_list import SitesList


class FleetOverviewPage(BasePage):
    # Confirmed: login lands here directly, there's no separate "/fleet-overview" route.
    PATH = "/?timeRange=24h"

    def open(self):
        # Deliberately NOT calling self.goto() here: login already lands on
        # this exact page, and a full reload of "/" was observed to bounce
        # back to /login on the real deployed app (2026-08-26) — so we just
        # wait for it to be there instead of re-navigating. If a future test
        # needs to reach Fleet Overview from somewhere else, add an explicit
        # goto() call at that call site rather than reinstating it here.
        self.page.locator(loc.LOADED_MARKER).first.wait_for(timeout=20000)
        return self

    def status_grid(self) -> FleetStatusGrid:
        return FleetStatusGrid(self.page)

    def map(self) -> FleetMap:
        return FleetMap(self.page)

    def sites_list(self) -> SitesList:
        return SitesList(self.page)

    def availability(self) -> FleetAvailability:
        return FleetAvailability(self.page)

    def alarms_analytics(self) -> FleetAlarmsAnalytics:
        return FleetAlarmsAnalytics(self.page)

    def select_time_range(self, label):
        """Switches the global 24h/7d/30d selector (confirmed live
        2026-09-15: a real <select> in the topbar, same mechanism Data &
        Monitoring's own global range selector uses) -- `label` is the
        visible option text (e.g. "Last 7 days"), not the underlying
        value ("7d")."""
        self.page.locator(loc.TIME_RANGE_SELECT).select_option(label=label)
        return self
