"""EngineerSelection -- reusable component: the "Engineer Selection" panel
(OP-28 / HU-10) shown under the "FSE Select (Variable Rate)" tab.

Confirmed differences between the documented spec (Jira OP-28, HUsACC,
Quotation_Spec_bilingual_V13 section 7) and the real deployed app
(2026-09-25):
  - Possible Check-In/Check-Out never populate for ANY selectable engineer.
    Root cause: the calculation needs each engineer's current/next task end
    times (currentEnd/nextEnd per V13 AC-7.5.1), but the real employee
    catalog (api/amxcpcatalog/employees, checked directly) has no such
    fields for any of its 19 records -- it's an HR-style catalog, not a
    dispatch/scheduling system. The "Add FSE" button that would let a
    planner manually supply that data for a custom engineer (V13 AC-7.10.1)
    does not exist in the live MAP sub-window either.
  - V13 documents separate ENGINEER (dropdown), MOBILE/EMAIL and
    LOCATION/DISTANCE fields -- the real app instead shows a single
    compact "Selected FSE" card (name + company + a star icon of
    unconfirmed purpose) once an engineer is selected.

Confirmed HU-11 (OP-29 / ENGINEER SELECTION MAP) findings (2026-09-26/27),
Sprint 1 Test Plan section 4.3's 20% suspension rule triggered for this
story -- Qase suite 48, run 23, 5 passed / 6 failed (54.5%):
  - Selecting more candidates than Required is not blocked (OP-29 AC #3):
    reproducible either by selecting beyond the limit, or by lowering
    Required (decreasing Support Engineers) below an already-selected
    count -- same root cause, both paths never trim Selected to Required.
  - No genuine "Add Engineer" path exists (OP-29 AC #5): the only manual
    add-when-not-found flow is "ADD EXTERNAL CONTRACTOR" (OP-29 AC #6,
    which IS implemented and working end-to-end), but it creates a
    Contractor record (Name/Phone/City only), not an engineer record, and
    is explicitly labelled CONTRACTOR in the Selected FSE card.
  - The candidate search box does not filter the list at all -- typing a
    partial match (e.g. "Pedro") still shows the full, unfiltered pool;
    only a zero-match search triggers the Add-Contractor flow.
  - Simulating a candidate-catalog load failure does show an error state
    (a "Connection Error" toast + an empty candidate list), but no Retry
    action exists anywhere (OP-29 AC #7, partially met).
  - Contractor Name/Phone/Location accept unescaped HTML/script and
    SQL-injection-style input with no validation (same root-cause class as
    Qase #88/#880) -- not a live XSS (React escapes it on render), but no
    input sanitization exists.
  - The candidate pool size does follow the required*2 formula (V13) and
    Add Contractor itself correctly updates Selected/Field Leader/Selected
    FSE -- both confirmed working.
"""
from __future__ import annotations

import re

from framework_ui.base.base_component import BaseComponent
from framework_ui.pages.quotation.components import engineer_selection_locators as loc


class EngineerSelection(BaseComponent):
    def __init__(self, page):
        section = page.locator("section").filter(
            has=page.get_by_role("heading", name=loc.SECTION_HEADING, exact=True))
        super().__init__(page, root=section)

    def _field_row(self, label_text):
        return self.root.locator(loc.FIELD_CONTAINER).filter(has=self.page.get_by_text(label_text, exact=True))

    def field(self, label_text):
        """The input/select of a field, found through its <label for=...> (the Support Engineers input, the
        Planned Check-in/out date pickers and the Field Leader select all have one since the 2026-10 UI change)."""
        # and_(): the selected engineer's star icon also has aria-label="Field Leader"; only form controls count here
        return self.root.get_by_label(label_text, exact=True).and_(self.root.locator("input, select, textarea"))

    def field_row(self, label_text):
        return self._field_row(label_text)

    def support_engineers_value(self):
        """Support Engineers is a number <input> between the - and + buttons (it used to be a <span>)."""
        return self.field(loc.LABEL_SUPPORT_ENGINEERS).input_value().strip()

    def increase_support_engineers(self):
        self.root.get_by_role("button", name=loc.INCREASE_SUPPORT_ENGINEERS_ARIA_LABEL).click()
        return self

    def decrease_support_engineers(self):
        self.root.get_by_role("button", name=loc.DECREASE_SUPPORT_ENGINEERS_ARIA_LABEL).click()
        return self

    def is_decrease_support_engineers_disabled(self):
        return self.root.get_by_role("button", name=loc.DECREASE_SUPPORT_ENGINEERS_ARIA_LABEL).is_disabled()

    def selected_required_text(self):
        """The "Selected: X · Required: Y" status text next to the panel
        title."""
        return self.root.get_by_text("Selected:", exact=False).inner_text().strip()

    def open_map(self):
        self.root.get_by_role("button", name=loc.MAP_BUTTON_TEXT, exact=True).click()
        return self

    def select_engineer_in_map(self, name):
        """Clicks the candidate card (a button whose name includes the engineer's name) inside the MAP sub-window."""
        self.page.locator("div.fixed.inset-0").get_by_role("button", name=name, exact=False).first.click()
        return self

    def complete_map(self):
        """Applies the selection (the sub-window now has Clear / Close / Save Draft / Complete; Close discards it)."""
        self.page.locator("div.fixed.inset-0").get_by_role("button", name="Complete", exact=True).click()
        return self

    def close_map(self):
        # scoped to the sub-window overlay: the date pickers (react-datepicker) also render "Close" icon buttons
        self.page.locator("div.fixed.inset-0").get_by_role("button", name=loc.MAP_CLOSE_BUTTON_TEXT, exact=True).click()
        return self

    def candidate_cards(self):
        """The candidate cards of the MAP sub-window (each one shows "N / Name / Company . X mi / AVAILABLE")."""
        return self.page.locator("div.fixed.inset-0").last.get_by_role("button").filter(
            has_text=re.compile(r"\u00b7 [\d.]+ mi"))

    def select_first_engineers(self, count=1):
        """Opens MAP, picks the first `count` candidates (the candidate pool depends on the selected Site, so tests must
        not rely on a fixed name) and applies the selection with Complete. Returns the picked names, in order."""
        self.open_map()
        cards = self.candidate_cards()
        cards.first.wait_for(timeout=15000)
        names = [cards.nth(i).inner_text().split("\n")[1].strip() for i in range(count)]
        for i in range(count):
            cards.nth(i).click()
        self.complete_map()
        return names

    def select_one_engineer(self, name=None):
        """Convenience: used purely as a precondition to reach a populated state, not as a test of MAP's own
        selection mechanics (that's HU-11's scope). Without a name it picks the first candidate. Returns the name."""
        if name is None:
            return self.select_first_engineers(1)[0]
        self.open_map()
        self.select_engineer_in_map(name)
        self.complete_map()
        return name

    # -- ENGINEER SELECTION MAP sub-window (HU-11 / OP-29) -----------------

    def map_modal(self):
        return self.page.locator("text=" + loc.MAP_MODAL_HEADING).locator(
            "xpath=ancestor::div[1]")

    def map_candidate_card(self, name):
        """The clickable candidate card button in the MAP sub-window,
        scoped precisely to avoid the strict-mode ambiguity that a bare
        get_by_text(name) hits once the same name also appears in the
        ENGINEER/FIELD LEADER dropdowns or the Selected FSE card."""
        return self.page.get_by_role("button", name=name, exact=False)

    def map_selected_required_text(self):
        """The "Selected X / Required Y" text inside the MAP sub-window
        header (distinct from the panel's own "Selected: X · Required: Y")."""
        return self.page.get_by_text("Selected", exact=False).filter(
            has_text="Required").last

    def map_search(self, text):
        self.page.get_by_placeholder(loc.MAP_SEARCH_PLACEHOLDER).fill(text)
        return self

    def map_search_by_keyboard(self, text):
        """Real keystrokes (not .fill()) -- needed to faithfully exercise
        the search box's own filtering/no-match logic."""
        box = self.page.get_by_placeholder(loc.MAP_SEARCH_PLACEHOLDER)
        box.click()
        box.type(text, delay=20)
        return self

    def is_contractor_form_visible(self):
        return self.page.get_by_placeholder(loc.MAP_CONTRACTOR_NAME_PLACEHOLDER).is_visible()

    def fill_contractor_form(self, name, phone=None, location=None):
        self.page.get_by_placeholder(loc.MAP_CONTRACTOR_NAME_PLACEHOLDER).fill(name)
        if phone is not None:
            self.page.get_by_placeholder(loc.MAP_CONTRACTOR_PHONE_PLACEHOLDER).fill(phone)
        if location is not None:
            self.page.get_by_placeholder(loc.MAP_CONTRACTOR_LOCATION_PLACEHOLDER).fill(location)
        return self

    def add_and_select_contractor(self):
        self.page.get_by_role(
            "button", name=loc.MAP_ADD_SELECT_CONTRACTOR_BUTTON, exact=False).click()
        return self
