"""MonitoringPage — Data & Monitoring screen. Delegates the card to the component."""
from __future__ import annotations

from framework_ui.base.base_page import BasePage
from framework_ui.pages.monitoring.components.power_card import PowerCard


class MonitoringPage(BasePage):
    PATH = "/monitoring?timeRange=24h"

    def open(self):
        return self.goto()

    def power_card(self) -> PowerCard:
        return PowerCard(self.page)

    def read_pcs_power_kw(self):
        return self.power_card().value_kw()
