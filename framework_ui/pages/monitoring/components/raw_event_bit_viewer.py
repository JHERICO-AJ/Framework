"""RawEventBitViewer -- reusable component: the evt1/evt2/pcsevt1 compacted
bitfield card + its "Event bit decode" modal on Data & Monitoring
(Jira story OF-381)."""
from __future__ import annotations

from framework_ui.base.base_component import BaseComponent
from framework_ui.pages.monitoring.components import raw_event_bit_viewer_locators as loc
from framework_ui.pages.monitoring.components.event_bit_decode_modal import EventBitDecodeModal


class RawEventBitViewer(BaseComponent):
    def card(self):
        return self.page.locator(".card").filter(
            has=self.page.locator(loc.CARD_TITLE, has_text=loc.TITLE_TEXT))

    def subtitle(self):
        return self.card().locator(loc.SUBTITLE).inner_text().strip()

    def footer_help_text(self):
        return self.card().locator(loc.FOOTER_HELP_TEXT).inner_text().strip()

    def _row(self, label):
        """Exact label match, not substring: "evt1" must not also match
        "pcsevt1" (which contains "evt1" as a substring) -- confirmed live
        this collision is real with a plain has_text filter."""
        import re
        return self.card().locator(loc.BIT_ROW).filter(
            has=self.page.locator(loc.BIT_LABEL, has_text=re.compile(f"^{re.escape(label)}$")))

    def word_value(self, label):
        """Raw compacted text for "evt1"/"evt2"/"pcsevt1" (e.g. "—",
        "0×11", or a binary string)."""
        return self._row(label).locator(loc.BIT_VALUE).inner_text().strip()

    def word_title_attr(self, label):
        """The value span's `title` attribute -- CA-07/CA-09: hover shows
        the full raw string, even when the visible text is compacted."""
        return self._row(label).locator(loc.BIT_VALUE).get_attribute("title")

    def decode_button_text(self):
        return self.card().locator(loc.DECODE_BUTTON).inner_text().strip()

    def open_decode(self):
        self.card().locator(loc.DECODE_BUTTON).click()
        self.page.locator(loc.OVERLAY).wait_for(state="visible")
        return EventBitDecodeModal(self.page)


