"""TelemetrySnapshotsModal — reusable component: the "Browse snapshots"
modal opened from the Telemetry Data Table (docs/OF-141.txt CA-21..28)."""
from __future__ import annotations

from framework_ui.base.base_component import BaseComponent
from framework_ui.pages.monitoring.components import telemetry_snapshots_modal_locators as loc


class TelemetrySnapshotsModal(BaseComponent):
    def is_open(self):
        return self.page.locator(loc.OVERLAY).count() > 0

    def title(self):
        return self.page.locator(loc.TITLE).inner_text().strip()

    def subtitle(self):
        return self.page.locator(loc.SUBTITLE).inner_text().strip()

    def snapshot_note(self):
        return self.page.locator(loc.SNAPSHOT_NOTE).inner_text().strip()

    def close(self):
        self.page.locator(loc.CLOSE_BUTTON).click()
        return self

    def column_headers(self):
        """Real underlying text via textContent -- same CSS
        text-transform:uppercase caveat as TelemetryDataTable's own
        column_headers()."""
        headers = self.page.locator(loc.HEADER_CELL)
        return [headers.nth(i).evaluate("el => el.textContent").strip() for i in range(headers.count())]

    def subsystem_options(self):
        options = self.page.locator(loc.SUBSYSTEM_SELECT).locator("option")
        return [options.nth(i).inner_text().strip() for i in range(options.count())]

    def window_labels(self):
        buttons = self.page.locator(loc.WINDOW_BUTTON)
        return [buttons.nth(i).inner_text().strip() for i in range(buttons.count())]

    def active_window_label(self):
        return self.page.locator(loc.WINDOW_BUTTON_ACTIVE).inner_text().strip()

    def select_window(self, label):
        self.page.locator(loc.WINDOW_BUTTON, has_text=label).click()
        return self

    def wait_for_rows(self, timeout=15000, poll_interval_ms=300):
        """Confirmed 2026-09-09 the modal takes a few seconds to load its
        first snapshot batch after opening. Unlike the Live table, this
        view is anchored/frozen (docs/OF-141.txt CA-23) -- once rows
        appear they don't change on their own, so a simple poll-until-
        present is enough, no convergence window needed. Returns self."""
        deadline = self.page.evaluate("Date.now()") + timeout
        while self.rows().count() == 0 and self.page.evaluate("Date.now()") < deadline:
            self.page.wait_for_timeout(poll_interval_ms)
        return self

    def rows(self):
        return self.page.locator(loc.ROW)

    def row_count(self):
        return self.rows().count()

    def row_values(self, index):
        headers = self.column_headers()
        cells = self.rows().nth(index).locator("td")
        return {header: cells.nth(i).inner_text().strip() for i, header in enumerate(headers)}

    def all_row_values(self):
        headers = self.column_headers()
        rows = self.page.locator(loc.TABLE).evaluate(
            """table => Array.from(table.querySelectorAll('tbody tr')).map(tr =>
                Array.from(tr.querySelectorAll('td')).map(td => td.textContent.trim()))"""
        )
        return [dict(zip(headers, cells)) for cells in rows]

    def pagination_info(self):
        """e.g. "Rows 1-9 of 9" -- read via textContent, the <strong> tags
        inside don't affect it."""
        return self.page.locator(loc.PAGINATION_INFO).inner_text().strip()

    def chronology_label(self):
        """CA-25 (docs/OF-141.txt): should say "Newest records first" --
        the opposite order convention from the Live table. Read via
        textContent, not inner_text(): this label is styled with CSS
        text-transform:uppercase, same caveat as column_headers()."""
        return self.page.locator(loc.PAGINATION_CHRONOLOGY).evaluate("el => el.textContent").strip()

    def page_size_options(self):
        options = self.page.locator(loc.PAGE_SIZE_SELECT).locator("option")
        return [options.nth(i).inner_text().strip() for i in range(options.count())]

    def select_page_size(self, label):
        self.page.locator(loc.PAGE_SIZE_SELECT).select_option(label=label)
        return self
