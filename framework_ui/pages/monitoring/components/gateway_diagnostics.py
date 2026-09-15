"""GatewayDiagnostics — reusable component: the 4-card Gateway Diagnostics
row (Communication Status / Gateway ID / MAC ID / Data Freshness)."""
from __future__ import annotations

from framework_ui.base.base_component import BaseComponent
from framework_ui.pages.monitoring.components import gateway_diagnostics_locators as loc


class GatewayDiagnostics(BaseComponent):
    def cards(self):
        return self.page.locator(loc.CARD)

    def card_by_title(self, title):
        return self.cards().filter(has=self.page.locator(loc.CARD_TITLE, has_text=title))

    def value(self, title):
        return self.card_by_title(title).locator(loc.CARD_VALUE).first.inner_text().strip()

    def mini_metric(self, title, label):
        """One "label: value" row from a card's mini-metrics block (e.g.
        MAC ID's "Data latency"/"Last comms", Data Freshness's "System ID"/
        "Sampling interval"/"Aggregation window")."""
        card = self.card_by_title(title)
        rows = card.locator(loc.MINI_METRIC_ROW)
        for i in range(rows.count()):
            row = rows.nth(i)
            if row.locator(loc.MINI_METRIC_LABEL).inner_text().strip() == label:
                return row.locator(loc.MINI_METRIC_VALUE).inner_text().strip()
        return None
