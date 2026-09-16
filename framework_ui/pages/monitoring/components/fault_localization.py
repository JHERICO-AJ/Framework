"""FaultLocalization -- reusable component: the 8-row rack/pack/cell
extreme-location card on Data & Monitoring (docs/OF-153.txt)."""
from __future__ import annotations

import re

from framework_ui.base.base_component import BaseComponent
from framework_ui.pages.monitoring.components import fault_localization_locators as loc


class FaultLocalization(BaseComponent):
    def card(self):
        return self.page.locator(".card").filter(
            has=self.page.locator(loc.CARD_TITLE, has_text=loc.TITLE_TEXT))

    def subtitle(self):
        return self.card().locator(loc.SUBTITLE).inner_text().strip()

    def device_cards(self):
        return self.card().locator(loc.GRID).locator(loc.DEVICE_CARD)

    def _row(self, label):
        """Exact label match, not substring -- same collision risk already
        confirmed for Raw Event Bit Viewer's evt1/pcsevt1 (e.g. "Highest V
        rack" must not also match "Highest V rack" inside a longer label)."""
        return self.card().locator(loc.BIT_ROW).filter(
            has=self.page.locator(loc.BIT_LABEL, has_text=re.compile(f"^{re.escape(label)}$")))

    def row_value(self, label):
        return self._row(label).locator(loc.BIT_VALUE).inner_text().strip()

    def all_row_labels(self):
        labels = self.card().locator(loc.BIT_ROW).locator(loc.BIT_LABEL)
        return [labels.nth(i).inner_text().strip() for i in range(labels.count())]

    def all_values(self):
        return {label: self.row_value(label) for label in loc.ALL_ROWS}
