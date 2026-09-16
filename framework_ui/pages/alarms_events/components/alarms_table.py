"""AlarmsTable — component: the alarms table. Handles virtualization
(scrolls and accumulates rows). Columns confirmed against the real HTML.
"""
from __future__ import annotations

from framework_ui.base.base_component import BaseComponent
from framework_ui.pages.alarms_events.components import alarms_table_locators as loc
from framework_ui.pages.alarms_events.components.alarm_row import AlarmRow


class AlarmsTable(BaseComponent):
    def _parse_row(self, tr):
        cells = tr.locator("td")

        def txt(locator):
            try:
                return locator.inner_text().strip()
            except Exception:
                return ""

        return AlarmRow(
            name=txt(cells.nth(0).locator(loc.CELL_NAME)),
            device=txt(cells.nth(0).locator(loc.CELL_SUBTEXT)),
            severity=txt(cells.nth(2)),
            status=txt(cells.nth(3)),
            first=txt(cells.nth(5)),
            last=txt(cells.nth(6)),
            subsystem=txt(cells.nth(8)),
            signal=txt(cells.nth(9).locator(loc.SIGNAL_LINE)),
        )

    def visible_rows(self):
        trs = self.page.locator(loc.ROWS)
        return [self._parse_row(trs.nth(i)) for i in range(trs.count())]

    def all_rows(self, max_scroll=60):
        """Scrolls the virtualized table and accumulates all rows (dedup)."""
        seen = {}
        container = self.page.locator(loc.SCROLL)
        prev = -1
        for _ in range(max_scroll):
            for row in self.visible_rows():
                if row.name:
                    seen[row.key] = row
            pos = container.evaluate("(el) => { el.scrollTop += 400; return el.scrollTop; }")
            self.page.wait_for_timeout(200)
            if pos == prev:
                break
            prev = pos
        return list(seen.values())
