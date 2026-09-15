"""EnvironmentalMonitoring -- reusable component: the Ambient Temp/Humidity
card on Data & Monitoring (docs/OF-151.txt)."""
from __future__ import annotations

from framework_ui.base.base_component import BaseComponent
from framework_ui.pages.monitoring.components import environmental_monitoring_locators as loc
from shared.utils.parsing import parse_value_and_source


class EnvironmentalMonitoring(BaseComponent):
    def card(self):
        return self.page.locator(".card").filter(
            has=self.page.locator(loc.CARD_TITLE, has_text=loc.TITLE_TEXT))

    def subtitle(self):
        return self.card().locator(loc.SUBTITLE).inner_text().strip()

    def _block(self, title):
        return self.card().locator(loc.BLOCK).filter(
            has=self.page.locator(loc.BLOCK_TITLE, has_text=title))

    def block_titles(self):
        titles = self.card().locator(loc.BLOCK_TITLE)
        return [titles.nth(i).inner_text().strip() for i in range(titles.count())]

    def raw_value_text(self, title):
        """Full rendered text for a block's value, including any trailing
        source flag (e.g. "25.0°C (API)", "50% (On-site)", or "—")."""
        return self._block(title).locator(loc.BLOCK_VALUE).inner_text().strip()

    def help_text(self, title):
        return self._block(title).locator(loc.BLOCK_HELP_TEXT).inner_text().strip()

    def value_and_source(self, title):
        """(numeric_value, source) -- source is "On-site"/"API"/None (no
        source flag at all, i.e. the value itself is absent)."""
        return parse_value_and_source(self.raw_value_text(title))

    def ambient_temp_value_and_source(self):
        return self.value_and_source(loc.AMBIENT_TEMP_TITLE)

    def humidity_value_and_source(self):
        return self.value_and_source(loc.HUMIDITY_TITLE)
