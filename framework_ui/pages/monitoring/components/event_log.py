"""EventLog — reusable component: the live event table + "Browse history"
modal on Data & Monitoring (docs/OF-293.txt)."""
from __future__ import annotations

from framework_ui.base.base_component import BaseComponent
from framework_ui.pages.monitoring.components import event_log_locators as loc


class EventLog(BaseComponent):
    def card(self):
        return self.page.locator(".card").filter(
            has=self.page.locator(loc.CARD_TITLE, has_text=loc.TITLE_TEXT))

    def time_range_badge(self):
        return self.card().locator(loc.TIME_RANGE_BADGE).inner_text().strip()

    def time_range_period(self):
        return self.card().locator(loc.TIME_RANGE_PERIOD).inner_text().strip()

    def subtitle(self):
        return self.card().locator(loc.SUBTITLE).first.inner_text().strip()

    def header_cells(self):
        """Reads via textContent (evaluate), not inner_text(): this table's
        headers render uppercase via CSS text-transform, same pattern
        already confirmed unreliable with inner_text() elsewhere in this
        module."""
        cells = self.card().locator(loc.TABLE_HEADER_CELL)
        return [cells.nth(i).evaluate("el => el.textContent").strip() for i in range(cells.count())]

    def rows(self):
        return self.card().locator(loc.TABLE_ROW)

    def row_count(self):
        return self.rows().count()

    def row_values(self, index):
        """[Time, Type, Source, Description] for row `index` (0 = most
        recent, per CA-07). Reads all 4 cells in a single evaluate() call
        (one atomic snapshot of the row), not 4 separate round-trips:
        CA-14's live push can re-render rows between individual reads,
        which could otherwise mix cells from two different moments into
        one inconsistent "row"."""
        return self.rows().nth(index).evaluate(
            "row => Array.from(row.querySelectorAll('td')).map(td => td.textContent.trim())")

    def all_row_values(self):
        """Every row's [Time, Type, Source, Description], read in a SINGLE
        evaluate() call over the whole table -- one atomic DOM snapshot.
        Reading row-by-row via separate Locator calls (rows().nth(i)...) is
        unsafe here: CA-14's live push can re-render/reorder rows between
        individual reads, and under a fast event burst (e.g. the known
        PCS_COMM_LOST rate issue) this can shrink the row count mid-loop,
        making a later index simply vanish and the read hang until
        timeout. Retries past the initial "Loading events..." placeholder
        row (CA-30) rather than treating it as real data."""
        for _ in range(10):
            values = self.card().locator("table").first.evaluate(
                "table => Array.from(table.querySelectorAll('tbody tr')).map("
                "row => Array.from(row.querySelectorAll('td')).map(td => td.textContent.trim()))")
            if values != [["Loading events..."]]:
                return values
            self.page.wait_for_timeout(300)
        return values

    def open_browse_history(self):
        self.card().locator(loc.BROWSE_HISTORY_BUTTON).click()
        self.page.locator(loc.OVERLAY).wait_for(state="visible")
        self.page.locator(loc.MODAL_HEADER_CELL).first.wait_for(state="visible")
        return EventLogHistoryModal(self.page)

    def browse_history_button_enabled(self):
        return self.card().locator(loc.BROWSE_HISTORY_BUTTON).is_enabled()


class EventLogHistoryModal(BaseComponent):
    """The "Browse history" modal opened from EventLog.open_browse_history()
    -- CA-17 through CA-24 (docs/OF-293.txt). Same shared modal component
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
