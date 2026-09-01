"""FleetStatusGrid — reusable component: the fleet-wide KPI cards row."""
from __future__ import annotations

from framework_ui.base.base_component import BaseComponent
from framework_ui.pages.fleet_overview.components import fleet_status_grid_locators as loc


class FleetStatusGrid(BaseComponent):
    def cards(self):
        return self.page.locator(loc.CARD)

    def card_titles(self):
        cards = self.cards()
        return [cards.nth(i).locator(loc.CARD_LABEL).inner_text().strip()
                for i in range(cards.count())]

    def card_by_title(self, title):
        return self.cards().filter(has=self.page.locator(loc.CARD_LABEL, has_text=title))

    def card_value(self, title):
        return self.card_by_title(title).locator(loc.CARD_VALUE).inner_text().strip()

    def badge_kind(self, index):
        """'current' if the card's badge is the "CURRENT" style, else 'range'
        (the "24H" style — a fixed lookback window, not a literal date range,
        but structurally the same "not current" bucket)."""
        classes = self.cards().nth(index).locator(loc.CARD_BADGE).get_attribute("class") or ""
        return "current" if "current" in classes.split() else "range"

    def chips(self):
        return self.page.locator(loc.CHIP)

    def chip_value(self, index):
        """Chips have no per-chip label class (see fleet_status_grid_locators.py)
        -- confirmed fixed order: 0=Total Sites, 1=Reporting Sites, 2=Update Time."""
        return self.chips().nth(index).locator(loc.CHIP_VALUE).inner_text().strip()
