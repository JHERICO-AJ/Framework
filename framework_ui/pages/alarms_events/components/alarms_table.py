"""AlarmsTable — componente: la tabla de alarmas. Maneja la virtualización
(scrollea y acumula filas). Columnas confirmadas contra el HTML real.
"""
from __future__ import annotations

import datetime

from dataclasses import dataclass

from framework_ui.base.base_component import BaseComponent
from framework_ui.pages.alarms_events.components import alarms_table_locators as loc


def parse_ui_datetime(text):
    """'18/08/2026, 09:46:03' (local time) -> naive local datetime, or None."""
    if not text:
        return None
    t = text.strip()
    for fmt in ("%d/%m/%Y, %H:%M:%S", "%d/%m/%Y %H:%M:%S"):
        try:
            return datetime.datetime.strptime(t, fmt)
        except ValueError:
            continue
    return None


@dataclass(frozen=True)
class AlarmRow:
    name: str
    device: str
    severity: str
    status: str
    first: str
    last: str
    subsystem: str
    signal: str

    @property
    def key(self):
        return (self.name, self.device)


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
        """Scrollea la tabla virtualizada y acumula todas las filas (dedup)."""
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
