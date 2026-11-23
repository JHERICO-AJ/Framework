"""DecisionBar -- reusable component: the approver's decision bar (HU-22 / OP-31) at the bottom of a quotation."""
from __future__ import annotations

import re

from framework_ui.base.base_component import BaseComponent
from framework_ui.pages.quotation.components import decision_bar_locators as loc


class DecisionBar(BaseComponent):
    def __init__(self, page):
        super().__init__(page, root=page)

    def recommendation(self):
        return self.page.get_by_placeholder(loc.RECOMMENDATION_PLACEHOLDER)

    def reject_button(self):
        return self.page.get_by_role("button", name=loc.REJECT_BUTTON_TEXT, exact=True)

    def approve_button(self):
        """Also matches the 'Saving...' label while a decision is being saved (same button)."""
        return self.page.get_by_role("button", name=re.compile(rf"^({loc.APPROVE_BUTTON_TEXT}|{re.escape(loc.SAVING_BUTTON_TEXT)})$"))

    def is_visible(self):
        """True when the whole bar (field + both buttons) is shown."""
        return all(c.count() > 0 and c.first.is_visible()
                   for c in (self.recommendation(), self.reject_button(), self.approve_button()))

    def wait_until_visible(self, timeout=15000):
        self.recommendation().wait_for(state="visible", timeout=timeout)
        return self

    def type_recommendation(self, text):
        """Types key by key (the way a person would), so the counter and the emoji filter run as they do for real."""
        field = self.recommendation()
        field.click()
        field.press("Control+A")
        field.press("Delete")
        field.type(text, delay=5)
        return self

    def paste_recommendation(self, text):
        """Sets the whole value in one input event (like a paste)."""
        field = self.recommendation()
        field.click()
        field.press("Control+A")
        field.press("Delete")
        field.fill(text)
        return self

    def value(self):
        return self.recommendation().input_value()

    def counter_text(self):
        """The visible '<n> / 1000' counter near the field, or None when it is not shown."""
        loc_counter = self.page.get_by_text(re.compile(rf"^\s*\d+\s*/\s*{loc.MAX_LENGTH}\s*$"))
        for i in range(loc_counter.count()):
            if loc_counter.nth(i).is_visible():
                return loc_counter.nth(i).inner_text().strip()
        return None

    def decide(self, outcome, text):
        """Types the recommendation and clicks Approve or Reject ('approve' | 'reject')."""
        self.type_recommendation(text)
        (self.approve_button() if outcome == "approve" else self.reject_button()).click()
        return self

    def bar_text(self):
        """Text of the strip that holds the bar (for error messages shown 'in the decision bar')."""
        field = self.recommendation()
        return field.locator("xpath=ancestor::*[.//button[normalize-space()='Reject']][1]").inner_text()
