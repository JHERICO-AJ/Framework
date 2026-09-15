"""ThermalDiagnostics -- reusable component: the 3-block site-level
thermal summary on Data & Monitoring (docs/OF-149.txt)."""
from __future__ import annotations

from framework_ui.base.base_component import BaseComponent
from framework_ui.pages.monitoring.components import thermal_diagnostics_locators as loc


class ThermalDiagnostics(BaseComponent):
    def card(self):
        return self.page.locator(".card").filter(
            has=self.page.locator(loc.CARD_TITLE, has_text=loc.TITLE_TEXT))

    def subtitle(self):
        return self.card().locator(loc.SUBTITLE).inner_text().strip()

    def blocks(self):
        return self.card().locator(loc.BLOCK)

    def block_count(self):
        return self.blocks().count()

    def block_titles(self):
        titles = self.blocks().locator(loc.BLOCK_TITLE)
        return [titles.nth(i).inner_text().strip() for i in range(titles.count())]

    def _block(self, title):
        return self.blocks().filter(has=self.page.locator(loc.BLOCK_TITLE, has_text=title))

    def help_text(self, title):
        return self._block(title).locator(loc.BLOCK_HELP_TEXT).inner_text().strip()

    def value_class(self, title):
        """Raw `class` attribute of the block's value span (e.g.
        "metric-value yellow") -- used for CA-07's "Cell Temperature Delta
        is always highlighted yellow" without depending on a computed
        color."""
        return self._block(title).locator(loc.BLOCK_VALUE).get_attribute("class") or ""

    def single_value(self, title):
        """(number, unit) for a single-thermal-pair block (Cell
        Temperature Delta, Average Cell Temp) -- e.g. ("5.2", "°C") or
        ("—", "°C") when there's no fresh data."""
        pair = self._block(title).locator(loc.THERMAL_PAIR).first
        number = pair.locator(loc.THERMAL_NUMBER).inner_text().strip()
        unit = pair.locator(loc.THERMAL_UNIT).inner_text().strip()
        return number, unit

    def highest_lowest_values(self):
        """(highest_number, highest_unit, lowest_number, lowest_unit) for
        the "Highest / Lowest Temp" block's two thermal-pairs, in that
        order (CA-11: "First = highest ... second = lowest")."""
        block = self._block("Highest / Lowest Temp")
        pairs = block.locator(loc.THERMAL_PAIR)
        highest_number = pairs.nth(0).locator(loc.THERMAL_NUMBER).inner_text().strip()
        highest_unit = pairs.nth(0).locator(loc.THERMAL_UNIT).inner_text().strip()
        lowest_number = pairs.nth(1).locator(loc.THERMAL_NUMBER).inner_text().strip()
        lowest_unit = pairs.nth(1).locator(loc.THERMAL_UNIT).inner_text().strip()
        return highest_number, highest_unit, lowest_number, lowest_unit
