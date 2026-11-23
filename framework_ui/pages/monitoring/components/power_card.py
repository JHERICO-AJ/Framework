"""PowerCard — reusable component: the 'Actual PCS Power' card."""
from __future__ import annotations

from framework_ui.base.base_component import BaseComponent
from framework_ui.pages.monitoring.components import power_card_locators as loc
from shared.utils.parsing import parse_kw


class PowerCard(BaseComponent):
    def _card(self):
        return self.page.locator(loc.DEVICE_CARD, has_text=loc.PCS_POWER_LABEL)

    def value_kw(self):
        card = self._card()
        card.wait_for(timeout=15000)
        text = card.locator(loc.METRIC_VALUE).inner_text()
        return parse_kw(text)
