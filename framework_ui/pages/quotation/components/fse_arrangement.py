"""FseArrangement -- reusable component: the "FSE Arrangement (Flat Rate)"
tab of the Quotation (WO) Creation form (OP-20 / HU-09).

Confirmed differences between the documented spec (Jira OP-20, HUsACC,
Quotation_Spec_bilingual_V13/V14) and the real deployed app (2026-09-24):
  - Total Man Working Hours is read-only and calculated, but its formula
    ignores Total Over Hours/Tech entirely: it always equals SUPPORT
    ENGINEERS x Total Working Hour/Tech, never the documented SUPPORT
    ENGINEERS x (Total Working Hour + Total Over Hours).
  - The Onsite Support Subtotal does not apply the developer-confirmed Per
    Diem formula (rate x SUPPORT ENGINEERS x days worked, see Qase #846's
    Teams clarification, 2026-09-24) -- Per Diem contributes only its raw
    entered rate, with no multiplier at all.
  - The Onsite Support Subtotal triples Travel & Drive Time's contribution
    (entering 10 adds exactly 30) instead of counting it once.
  - Switching to "FSE Select (Variable Rate)" (its real panel heading is
    "Engineer Selection", OP-28 / HU-10 -- a separate story, not this one)
    is gated by a real precondition, not broken: with no Site selected in
    WO Snapshot
    yet, clicking it shows a "Site Selection Required" modal (dismissed via
    its "Accept" button) and the tab never switches; once a Customer and
    Site are chosen, the switch works correctly.
  - Engineer Selection's own Support Engineers control (a +/- stepper, not
    a plain input) is NOT synced with FSE Arrangement's Support Engineers
    field: setting 5 on FSE Arrangement and switching tabs still shows the
    stepper's own default of 1.
"""
from __future__ import annotations

import re

from framework_ui.base.base_component import BaseComponent
from framework_ui.pages.quotation.components import fse_arrangement_locators as loc

_SUBTOTAL_SECTION_ORDER = [
    loc.SECTION_HEADING_LABOR, loc.SECTION_HEADING_ONSITE, loc.SECTION_HEADING_REIMBURSABLE,
]


class FseArrangement(BaseComponent):
    def __init__(self, page):
        super().__init__(page, root=page)

    def _section(self, heading_text):
        return self.page.locator("section").filter(
            has=self.page.get_by_role("heading", name=heading_text, exact=True))

    def _field_row(self, section_heading, label_text):
        return self._section(section_heading).locator(loc.FIELD_CONTAINER).filter(
            has=self.page.get_by_text(label_text, exact=True))

    def field_row(self, section_heading, label_text):
        """The field's whole container (label + input/computed value) --
        for structural checks that need more than just the input itself."""
        return self._field_row(section_heading, label_text)

    def field(self, section_heading, label_text):
        """The input/select for an EDITABLE field."""
        return self._field_row(section_heading, label_text).locator("input, select, textarea")

    def computed_value_locator(self, section_heading, label_text):
        """The <div> holding a READ-ONLY calculated field's displayed text
        -- pass this to Playwright's expect(...).to_have_text(...) so
        assertions poll for the recalculated value instead of guessing a
        fixed sleep."""
        return self._field_row(section_heading, label_text).locator("div")

    def computed_value(self, section_heading, label_text):
        """The displayed text of a READ-ONLY calculated field, read once,
        with no wait -- prefer computed_value_locator() with expect() in
        any test that just changed an input and needs the recalculation to
        land first."""
        return self.computed_value_locator(section_heading, label_text).inner_text().strip()

    def error_locator(self, section_heading, label_text):
        return self._field_row(section_heading, label_text).locator(loc.ERROR_TEXT)

    def error_for(self, section_heading, label_text):
        error = self.error_locator(section_heading, label_text)
        return error.inner_text().strip() if error.count() > 0 else ""

    def section_field_labels(self, section_heading):
        rows = self._section(section_heading).locator(loc.FIELD_CONTAINER)
        return [rows.nth(i).locator("label").text_content().strip() for i in range(rows.count())]

    def subtotal_locator(self, section_heading):
        """The <strong> holding a block's Subtotal amount, found by
        position among the page's 3 "Subtotal" rows (Labor, Onsite,
        Reimbursable, in that DOM order) -- scoping get_by_text("Subtotal")
        to a .filter(has=...) section locator times out in this app (the
        filtered locator never re-resolves), so this indexes the page-wide
        list instead. Pass this to expect(...).to_have_text(...) to poll
        for a recalculated amount instead of guessing a fixed sleep."""
        index = _SUBTOTAL_SECTION_ORDER.index(section_heading)
        row = self.page.locator("text=Subtotal").nth(index)
        return row.locator("xpath=following-sibling::strong")

    def subtotal_text(self, section_heading):
        return self.subtotal_locator(section_heading).inner_text().strip()

    def total_locator(self):
        row = self.page.get_by_text("Total", exact=True)
        return row.locator("xpath=following-sibling::strong")

    def total_text(self):
        return self.total_locator().inner_text().strip()

    def fse_arrangement_tab_locator(self):
        return self.page.get_by_role("button", name=loc.TAB_FSE_ARRANGEMENT, exact=True)

    def fse_select_tab_locator(self):
        return self.page.get_by_role("button", name=loc.TAB_FSE_SELECT, exact=True)

    def open_fse_arrangement_tab(self):
        self.fse_arrangement_tab_locator().click()
        return self

    def open_fse_select_tab(self):
        self.fse_select_tab_locator().click()
        return self

    def is_fse_arrangement_tab_active(self):
        cls = self.fse_arrangement_tab_locator().get_attribute("class")
        return "bg-transparent" not in cls

    def site_required_modal(self):
        return self.page.get_by_text(loc.SITE_REQUIRED_MODAL_TEXT, exact=False)

    def dismiss_site_required_modal(self):
        self.page.get_by_role("button", name=loc.SITE_REQUIRED_MODAL_ACCEPT_BUTTON_TEXT, exact=True).click()
        return self

    def engineer_selection_support_engineers_locator(self):
        """The <span> holding Engineer Selection's own Support Engineers
        +/- stepper value (not an <input> -- see module docstring)."""
        row = self._section(loc.SECTION_HEADING_ENGINEER_SELECTION).locator(loc.FIELD_CONTAINER).filter(
            has=self.page.get_by_text(loc.LABEL_ENGINEER_SELECTION_SUPPORT_ENGINEERS, exact=True))
        return row.locator("span")

    def engineer_selection_required_locator(self, expected):
        """The "Selected: 0 . Required: N" summary at the top of Engineer Selection, which
        mirrors SUPPORT ENGINEERS (the stepper is now an <input> between the -/+ buttons)."""
        return self.page.get_by_text(re.compile(rf"Required:\s*{expected}\b"))

    def engineer_selection_support_engineers_value(self):
        return self.engineer_selection_support_engineers_locator().inner_text().strip()
