"""EventLogHistoryModal -- the modal opened from its card."""

from __future__ import annotations

from framework_ui.base.base_component import BaseComponent
from framework_ui.pages.monitoring.components import event_log_locators as loc


class EventLogHistoryModal(BaseComponent):
    """The "Browse history" modal opened from EventLog.open_browse_history()
    -- CA-17 through CA-24 (Jira story OF-293). Same shared modal component
    as Telemetry Data Table's "Browse snapshots" (see
    telemetry_snapshots_modal.py), but this module keeps its own thin
    wrapper since Event Log's modal has no subsystem filter (only the 3
    time-window buttons) and adds the "Today"/clock split time cell."""

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

    def wait_for_rows(self, timeout=5000):
        """select_window() reloads the modal's query -- confirmed live
        2026-09-21 that reading row_count() immediately after switching
        windows can race the reload and see a transient 0 rows (25 real
        rows show up within ~1s). Waits for the first row rather than a
        fixed sleep."""
        self.rows().first.wait_for(timeout=timeout)
        return self

    def row_time_day(self, index):
        """The "Today"/date label in a row's Time cell (CA-31) -- None if
        the row doesn't split day/clock (e.g. a full-datetime format for
        7d/30d with a day filter)."""
        day = self.rows().nth(index).locator(loc.MODAL_ROW_TIME_DAY)
        return day.inner_text().strip() if day.count() else None

    def row_time_clock(self, index):
        clock = self.rows().nth(index).locator(loc.MODAL_ROW_TIME_CLOCK)
        return clock.inner_text().strip() if clock.count() else None

    def row_time_datetime(self, index):
        """The single full-datetime span used for 7d/30d rows (CA-31) --
        None if the row instead splits day/clock (24h's own format)."""
        cell = self.rows().nth(index).locator(loc.MODAL_ROW_TIME_DATETIME)
        return cell.inner_text().strip() if cell.count() else None

    def row_values(self, index):
        cells = self.rows().nth(index).locator("td")
        return [cells.nth(i).inner_text().strip() for i in range(cells.count())]

    def close(self):
        self.page.locator(loc.MODAL_CLOSE_BUTTON).click()
        self.page.locator(loc.OVERLAY).wait_for(state="hidden")
        return self

    def has_day_range_filter(self):
        """CA-21: the "Browse by day" From/To selector, only present for
        7d/30d windows."""
        return self.page.locator(loc.DAY_RANGE).count() > 0

    def select_day_range(self, from_date, to_date):
        """`from_date`/`to_date` are "YYYY-MM-DD" strings matching one of
        the day-range <option>'s own value attribute (confirmed live
        2026-09-10 -- the visible option text is a localized "weekday, D
        month YYYY" string, so matching by value is the stable, locale-
        independent way to pick a specific day)."""
        self.page.locator(loc.DAY_RANGE_FROM_SELECT).select_option(value=from_date)
        self.page.locator(loc.DAY_RANGE_TO_SELECT).select_option(value=to_date)
        return self

    def day_range_option_texts(self):
        """The FROM select's own visible <option> text for every day --
        this is the locale-sensitive rendering (e.g. "sab, 5 sept 2026" vs
        "Sat, Sep 5, 2026"), as opposed to select_day_range's locale-
        independent value attribute."""
        options = self.page.locator(loc.DAY_RANGE_FROM_SELECT).locator("option")
        return [options.nth(i).inner_text().strip() for i in range(options.count())]

    def day_range_summary(self):
        return self.page.locator(loc.DAY_RANGE_SUMMARY).inner_text().strip()

    def day_range_warning(self):
        """CA-32's truncation notice ("Showing the N most recent records in
        this window...") -- None if the current window is under the query
        limit and no warning is shown."""
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
        """CA-19/CA-23's own reinforcing footer text ("Snapshot loaded at
        open -- no live updates in this view.")."""
        return self.page.locator(loc.SNAPSHOT_NOTE).inner_text().strip()
