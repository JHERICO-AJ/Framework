"""PcsEnergyStatistics -- reusable component: the 2-block period-energy
summary on Data & Monitoring (docs/OF-150.txt)."""
from __future__ import annotations

from framework_ui.base.base_component import BaseComponent
from framework_ui.pages.monitoring.components import pcs_energy_statistics_locators as loc


class PcsEnergyStatistics(BaseComponent):
    def card(self):
        return self.page.locator(".card").filter(
            has=self.page.locator(loc.CARD_TITLE, has_text=loc.TITLE_TEXT))

    def time_range_badge(self):
        return self.card().locator(loc.TIME_RANGE_BADGE).inner_text().strip()

    def time_range_period(self):
        return self.card().locator(loc.TIME_RANGE_PERIOD).inner_text().strip()

    def subtitle(self):
        return self.card().locator(loc.SUBTITLE).first.inner_text().strip()

    def blocks(self):
        return self.card().locator(loc.BLOCK)

    def block_titles(self):
        titles = self.blocks().locator(loc.BLOCK_TITLE)
        return [titles.nth(i).inner_text().strip() for i in range(titles.count())]

    def _block(self, title):
        return self.blocks().filter(has=self.page.locator(loc.BLOCK_TITLE, has_text=title))

    def value_text(self, title):
        """Raw value text for a block (e.g. "133.749 MWh" or "—")."""
        return self._block(title).locator(loc.BLOCK_VALUE).inner_text().strip()

    def help_text(self, title):
        return self._block(title).locator(loc.BLOCK_HELP_TEXT).inner_text().strip()

    def charge_energy_mwh(self):
        """Parses "133.749 MWh" -> 133.749, or None if the value is
        "—"."""
        return self._parse_mwh(self.value_text("PCS Charge Energy"))

    def discharge_energy_mwh(self):
        return self._parse_mwh(self.value_text("PCS Discharge Energy"))

    @staticmethod
    def _parse_mwh(text):
        if text.strip() == "—":
            return None
        return float(text.replace("MWh", "").strip())
