"""EventLog — reusable component: the live event table + "Browse history"
modal on Data & Monitoring (Jira story OF-293)."""
from __future__ import annotations

from framework_ui.base.base_component import BaseComponent
from framework_ui.pages.monitoring.components import event_log_locators as loc
from framework_ui.pages.monitoring.components.event_log_history_modal import EventLogHistoryModal


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


