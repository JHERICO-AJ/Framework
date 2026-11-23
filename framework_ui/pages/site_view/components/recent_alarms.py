"""RecentAlarms -- reusable component: the "Recent Alarms (Last 24h)" card
on Site View. Confirmed live 2026-09-18 (BOLIVIA 4): a small, non-virtualized
table (unlike the full Alarms & Events table) -- no scrolling/pagination
needed, just read every <tr>.

rows() reads every cell in ONE evaluate() call, not one Playwright
round-trip per cell per row: confirmed live 2026-09-20 that reading cell by
cell (nth(i).locator("td").nth(j).inner_text()) can race a live-updating
site (the card re-renders as new telemetry/alerts arrive) and time out
mid-row -- same failure mode already documented and fixed this same way in
TelemetryDataTable.all_row_values()."""
from __future__ import annotations

from framework_ui.base.base_component import BaseComponent
from framework_ui.pages.site_view.components import recent_alarms_locators as loc
from framework_ui.pages.site_view.components.recent_alarm_row import RecentAlarmRow


class RecentAlarms(BaseComponent):
    def card(self):
        return self.page.locator(loc.CARD).filter(has_text=loc.TITLE_TEXT)

    def rows(self):
        card = self.card()
        if card.locator(loc.ROWS).count() == 0:
            return []
        raw_rows = card.evaluate(
            """card => Array.from(card.querySelectorAll('tbody tr')).map(tr => {
                const cells = Array.from(tr.querySelectorAll('td'));
                const sevPill = cells[2] ? cells[2].querySelector('.sev-pill') : null;
                return {
                    time: cells[0] ? cells[0].textContent.trim() : '',
                    device: cells[1] ? cells[1].textContent.trim() : '',
                    severity: sevPill ? sevPill.textContent.trim() : (cells[2] ? cells[2].textContent.trim() : ''),
                    description: cells[3] ? cells[3].textContent.trim() : '',
                };
            })"""
        )
        return [RecentAlarmRow(**raw) for raw in raw_rows]
