"""PowerCard — componente reutilizable: la tarjeta 'Actual PCS Power'."""
from __future__ import annotations

import re

from framework_ui.base.base_component import BaseComponent
from framework_ui.pages.monitoring.components import power_card_locators as loc


def parse_kw(texto):
    """'2.486,5 kW' / '2486.5' -> 2486.5 (o None)."""
    if not texto:
        return None
    m = re.search(r"-?\d[\d,]*\.?\d*", texto.replace(",", ""))
    return float(m.group()) if m else None


class PowerCard(BaseComponent):
    def _card(self):
        return self.page.locator(loc.DEVICE_CARD, has_text=loc.PCS_POWER_LABEL)

    def value_kw(self):
        card = self._card()
        card.wait_for(timeout=15000)
        texto = card.locator(loc.METRIC_VALUE).inner_text()
        return parse_kw(texto)
