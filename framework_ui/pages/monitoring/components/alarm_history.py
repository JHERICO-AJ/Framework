"""AlarmHistory -- reusable component: the live alarm table + "Browse
history" modal on Data & Monitoring (Jira story OF-148). Event Log's direct
sibling in the same "Logs" section -- same shared modal architecture."""
from __future__ import annotations

from framework_ui.base.base_component import BaseComponent
from framework_ui.pages.monitoring.components import alarm_history_locators as loc
from framework_ui.pages.monitoring.components.alarm_history_modal import AlarmHistoryModal


class AlarmHistory(BaseComponent):
    def card(self):
        return self.page.locator(".card").filter(
            has=self.page.locator(loc.CARD_TITLE, has_text=loc.TITLE_TEXT))

    def time_range_badge(self):
        return self.card().locator(loc.TIME_RANGE_BADGE).inner_text().strip()

    def time_range_period(self):
        return self.card().locator(loc.TIME_RANGE_PERIOD).inner_text().strip()

    def subtitle(self):
        return self.card().locator(loc.SUBTITLE).first.inner_text().strip()

    def has_table(self):
        """False when the card shows only the "No alarms to display" /
        "Select a site..." empty state instead of a real table (unlike
        Event Log, which always renders a table shell even when empty)."""
        return self.card().locator("table").count() > 0

    def empty_state_text(self):
        empty = self.card().locator(".card-soft > div").first
        return empty.inner_text().strip()

    def header_cells(self):
        cells = self.card().locator(loc.TABLE_HEADER_CELL)
        return [cells.nth(i).evaluate("el => el.textContent").strip() for i in range(cells.count())]

    def rows(self):
        return self.card().locator(loc.TABLE_ROW)

    def row_count(self):
        return self.rows().count()

    def row_values(self, index):
        """[Time, Device, Alarm, Severity, Status] for row `index` (0 = most
        recent, per CA-08). Reads all 5 cells in a single evaluate() call --
        same atomic-snapshot pattern as Event Log, since this table is fed
        by the same fast-moving live PCS_COMM_LOST-driven alarm stream."""
        return self.rows().nth(index).evaluate(
            "row => Array.from(row.querySelectorAll('td')).map(td => td.textContent.trim())")

    def all_row_values(self):
        """Every row's [Time, Device, Alarm, Severity, Status], read in a
        SINGLE evaluate() call over the whole table -- one atomic DOM
        snapshot, avoiding the same live-churn Locator.nth() timeout risk
        already confirmed for Event Log's table."""
        for _ in range(10):
            values = self.card().locator("table").first.evaluate(
                "table => Array.from(table.querySelectorAll('tbody tr')).map("
                "row => Array.from(row.querySelectorAll('td')).map(td => td.textContent.trim()))")
            if values != [["Loading alarms..."]]:
                return values
            self.page.wait_for_timeout(300)
        return values

    def row_severity_class(self, index):
        """Full className of the row's severity pill, e.g. "sev-pill
        sev-critical" -- or "sev-pill " (trailing space, no modifier) for a
        severity the app doesn't have a color mapping for (confirmed live:
        MAJOR)."""
        return self.rows().nth(index).locator(loc.SEVERITY_PILL).get_attribute("class")

    def row_status_text(self, index):
        return self.rows().nth(index).locator(loc.STATUS_BADGE).inner_text().strip()

    def click_row(self, index):
        """CA-17: clicking a row filters Telemetry Data Table by that row's
        device and smooth-scrolls to it. Confirmed live: this does NOT
        change the Subsystem <select> -- it scrolls the telemetry table's
        own virtualized container to the matching device's rows."""
        self.rows().nth(index).click()
        return self

    def open_browse_history(self):
        self.card().locator(loc.BROWSE_HISTORY_BUTTON).click()
        self.page.locator(loc.OVERLAY).wait_for(state="visible")
        self.page.locator(loc.MODAL_HEADER_CELL).first.wait_for(state="visible")
        return AlarmHistoryModal(self.page)

    def browse_history_button_enabled(self):
        return self.card().locator(loc.BROWSE_HISTORY_BUTTON).is_enabled()


