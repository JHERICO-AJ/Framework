"""DeviceStatusPanel — reusable component: the 6-card Device Status Panel
grid at the top of Data & Monitoring."""
from __future__ import annotations

from framework_ui.base.base_component import BaseComponent
from framework_ui.pages.monitoring.components import device_status_panel_locators as loc


class DeviceStatusPanel(BaseComponent):
    def cards(self):
        return self.page.locator(loc.CARD)

    def card_titles(self):
        cards = self.cards()
        return [cards.nth(i).locator(loc.CARD_TITLE).inner_text().strip()
                for i in range(cards.count())]

    def card_by_title(self, title):
        return self.cards().filter(has=self.page.locator(loc.CARD_TITLE, has_text=title))

    def status(self, title):
        """The pill text (e.g. "warning", "fault", "online") -- lowercase in
        the UI regardless of the API's Title-Case status string."""
        return self.card_by_title(title).locator(loc.CARD_STATUS_PILL).inner_text().strip()

    def info_lines(self, title):
        """All info lines in the card body, excluding the trailing link
        text (that's a separate action, not status info)."""
        card = self.card_by_title(title)
        lines = card.locator(loc.CARD_BODY_INFO_LINE)
        return [lines.nth(i).inner_text().strip() for i in range(lines.count())]

    def link_text(self, title):
        return self.card_by_title(title).locator(loc.CARD_LINK).inner_text().strip()

    def click_link(self, title):
        self.card_by_title(title).locator(loc.CARD_LINK).click()
        return self
