"""DispatchLimitsTracking — reusable component: the 6-block dispatch/
setpoint/DC-bus summary on Data & Monitoring (docs/OF-145.txt)."""
from __future__ import annotations

from framework_ui.base.base_component import BaseComponent
from framework_ui.pages.monitoring.components import dispatch_limits_tracking_locators as loc


class DispatchLimitsTracking(BaseComponent):
    def card(self):
        """Scoped via .filter(has=...has_text=...), not a CSS :text-is()
        selector: the real title is "Dispatch Limits & Tracking" but CSS
        renders it uppercase, and :text-is() (with or without its
        case-insensitive "i" flag) was already confirmed unreliable
        against that same pattern for other cards this session --
        has_text (substring, case-insensitive by default) is the version
        that actually works."""
        return self.page.locator(".card").filter(
            has=self.page.locator(loc.CARD_TITLE, has_text=loc.TITLE_TEXT))

    def blocks(self):
        return self.card().locator(loc.BLOCK)

    def block_count(self):
        return self.blocks().count()

    def block_values(self):
        """{label: value} for every block currently rendered, keyed by its
        own label text (e.g. "Charge Limit") -- reads both label and
        value via textContent (evaluate), not inner_text(): CSS uppercases
        some of this card's text, and inner_text() would reflect that
        instead of the real underlying string."""
        blocks = self.blocks()
        values = {}
        for i in range(blocks.count()):
            block = blocks.nth(i)
            label = block.locator(loc.BLOCK_LABEL).evaluate("el => el.textContent").strip()
            value = block.locator(loc.BLOCK_VALUE).evaluate("el => el.textContent").strip()
            values[label] = value
        return values

    def value_for(self, label):
        """The single block's value matching `label` exactly, or None if
        no such block is currently rendered."""
        return self.block_values().get(label)
