"""AlarmsPage — Alarms & Events screen. Delegates the table to the component."""
from __future__ import annotations

from framework_ui.base.base_page import BasePage
from framework_ui.pages.alarms_events.components.alarms_table import AlarmsTable
from framework_ui.pages.alarms_events.components import alarms_table_locators as loc


class AlarmsPage(BasePage):
    PATH = "/alarms"

    def open(self):
        self.goto()
        self.page.locator(loc.ROWS).first.wait_for(timeout=15000)
        return self

    def table(self) -> AlarmsTable:
        return AlarmsTable(self.page)

    def rows(self):
        return self.table().all_rows()
