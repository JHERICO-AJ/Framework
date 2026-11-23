"""AlarmHistoryModal -- the modal opened from its card."""

from __future__ import annotations

from framework_ui.base.base_component import BaseComponent
from framework_ui.pages.monitoring.components import alarm_history_locators as loc


class AlarmHistoryModal(BaseComponent):
    """The "Browse history" modal opened from AlarmHistory.open_browse_history()
    -- CA-18 through CA-28 (Jira story OF-148). Same shared modal component as
    Event Log's own modal (event_log.py's EventLogHistoryModal) and
    Telemetry Data Table's "Browse snapshots", just with the 5-column
    Time/Device/Alarm/Severity/Status table."""

    def title(self):
        return self.page.locator(loc.MODAL_TITLE).inner_text().strip()

    def subtitle(self):
        return self.page.locator(loc.MODAL_SUBTITLE).inner_text().strip()

    def select_window(self, label):
        self.page.locator(loc.WINDOW_BUTTON, has_text=label).click()
        return self

    def active_window(self):
        return self.page.locator(loc.WINDOW_BUTTON_ACTIVE).inner_text().strip()

    def header_cells(self):
        cells = self.page.locator(loc.MODAL_HEADER_CELL)
        return [cells.nth(i).evaluate("el => el.textContent").strip() for i in range(cells.count())]

    def rows(self):
        return self.page.locator(loc.MODAL_ROW)

    def row_count(self):
        return self.rows().count()

    def row_time_day(self, index):
        day = self.rows().nth(index).locator(loc.MODAL_ROW_TIME_DAY)
        return day.inner_text().strip() if day.count() else None

    def row_time_clock(self, index):
        clock = self.rows().nth(index).locator(loc.MODAL_ROW_TIME_CLOCK)
        return clock.inner_text().strip() if clock.count() else None

    def row_time_datetime(self, index):
        cell = self.rows().nth(index).locator(loc.MODAL_ROW_TIME_DATETIME)
        return cell.inner_text().strip() if cell.count() else None

    def row_values(self, index):
        cells = self.rows().nth(index).locator("td")
        return [cells.nth(i).inner_text().strip() for i in range(cells.count())]

    def row_severity_class(self, index):
        return self.rows().nth(index).locator(loc.MODAL_ROW_SEVERITY_PILL).get_attribute("class")

    def close(self):
        self.page.locator(loc.MODAL_CLOSE_BUTTON).click()
        self.page.locator(loc.OVERLAY).wait_for(state="hidden")
        return self

    def has_day_range_filter(self):
        return self.page.locator(loc.DAY_RANGE).count() > 0

    def select_day_range(self, from_date, to_date):
        self.page.locator(loc.DAY_RANGE_FROM_SELECT).select_option(value=from_date)
        self.page.locator(loc.DAY_RANGE_TO_SELECT).select_option(value=to_date)
        return self

    def day_range_option_texts(self):
        """The FROM select's own visible <option> text for every day --
        the locale-sensitive rendering (e.g. "sab, 5 sept 2026" vs "Sat,
        Sep 5, 2026")."""
        options = self.page.locator(loc.DAY_RANGE_FROM_SELECT).locator("option")
        return [options.nth(i).inner_text().strip() for i in range(options.count())]

    def day_range_summary(self):
        return self.page.locator(loc.DAY_RANGE_SUMMARY).inner_text().strip()

    def day_range_warning(self):
        warning = self.page.locator(loc.DAY_RANGE_WARNING)
        return warning.inner_text().strip() if warning.count() else None

    def pagination_info(self):
        return self.page.locator(loc.PAGINATION_INFO).inner_text().strip()

    def current_page_number(self):
        return int(self.page.locator(loc.PAGE_INPUT).input_value())

    def select_page_size(self, size):
        self.page.locator(loc.PAGE_SIZE_SELECT).select_option(value=str(size))
        return self

    def go_to_next_page(self):
        self.page.locator(loc.NEXT_PAGE_BUTTON).click()
        return self

    def go_to_prev_page(self):
        self.page.locator(loc.PREV_PAGE_BUTTON).click()
        return self

    def jump_to_oldest(self):
        self.page.locator(loc.JUMP_TO_OLDEST_BUTTON).click()
        return self

    def jump_to_latest(self):
        self.page.locator(loc.JUMP_TO_LATEST_BUTTON).click()
        return self

    def next_page_button_enabled(self):
        return self.page.locator(loc.NEXT_PAGE_BUTTON).is_enabled()

    def prev_page_button_enabled(self):
        return self.page.locator(loc.PREV_PAGE_BUTTON).is_enabled()

    def snapshot_note(self):
        return self.page.locator(loc.SNAPSHOT_NOTE).inner_text().strip()
