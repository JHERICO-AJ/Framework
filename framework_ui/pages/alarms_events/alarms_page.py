"""AlarmsPage — Alarms & Events screen. Delegates the table to the component."""
from __future__ import annotations

from framework_ui.base.base_page import BasePage
from framework_ui.pages.alarms_events.components.alarms_table import AlarmsTable
from framework_ui.pages.alarms_events.components import alarms_table_locators as loc


class AlarmsPage(BasePage):
    PATH = "/alarms"

    # Confirmed live 2026-09-20: with a heavily-used shared QA environment
    # (many BOLIVIA sites carrying dozens of open alarms after a full day of
    # E2E-F09/F10/F11 testing), the first real batch of rows can take
    # noticeably longer than 15s to render -- reproduced 3x in a row at
    # exactly the old 15000ms timeout. Same "first batch is slower under
    # load" pattern already documented and fixed this same way in
    # TelemetryDataTable.ROWS_APPEAR_TIMEOUT_MS.
    ROWS_APPEAR_TIMEOUT_MS = 30000

    def open(self):
        self.goto()
        self.page.locator(loc.ROWS).first.wait_for(timeout=self.ROWS_APPEAR_TIMEOUT_MS)
        return self

    def table(self) -> AlarmsTable:
        return AlarmsTable(self.page)

    def rows(self):
        return self.table().all_rows()
