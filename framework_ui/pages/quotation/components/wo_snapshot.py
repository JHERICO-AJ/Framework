"""WoSnapshot -- reusable component: the "WO Snapshot" section of the
Quotation (WO) Creation form (OP-19 / HU-08).

Confirmed differences between the documented spec (Jira OP-19, HUsACC,
Quotation_Spec_bilingual_V13) and the real deployed app (2026-09-22):
  - The real form has a "Customer" field the spec never documents; "Site
    Name" is a <select> populated only after a Customer is chosen (its
    options are plain site names, not the "internal site code" the spec
    describes), instead of the free-text display field with a regex-
    validated site code (AC-5.5.2/5.5.3) the spec assumes.
  - "Type of Work" and "Site Location" are swapped relative to the
    documented field order (AC-5.0.1).
  - "Type of Work" offers only 4 options (Commissioning, Rework, Warranty
    Repair, Chargeable Repair) -- "PMP" (AC-5.7.1's 5th documented value)
    is missing from the live dropdown.
  - "Severity" is a free-text input, not a field restricted to the 5
    documented values (AC-5.9.2).
  - "Quote # / WO Number" accepts any text on blur or Submit -- no
    FSO-ABCDEFGH format validation exists (AC-5.2.2/5.2.3).
  - "GSP # / Alarm ID" and "Site Location" are mandatory ("Can't be empty")
    on Submit in the real app; neither is documented as mandatory anywhere
    in the spec.
"""
from __future__ import annotations

from framework_ui.base.base_component import BaseComponent
from framework_ui.pages.quotation.components import wo_snapshot_locators as loc


class WoSnapshot(BaseComponent):
    def __init__(self, page):
        section = page.locator("section").filter(
            has=page.get_by_role("heading", name=loc.SECTION_HEADING_TEXT, exact=True))
        super().__init__(page, root=section)

    def _field_row(self, label_text):
        return self.root.locator(loc.FIELD_CONTAINER, has=self.page.get_by_text(label_text, exact=True))

    def field(self, label_text):
        """The input/select/textarea for the given field label."""
        return self._field_row(label_text).locator("input, select, textarea")

    def error_for(self, label_text):
        """The field-level validation error text (e.g. "Can't be empty"),
        or "" if none is shown."""
        error = self._field_row(label_text).locator(loc.ERROR_TEXT)
        return error.inner_text().strip() if error.count() > 0 else ""

    def visible_field_labels_in_order(self):
        """text_content(), not inner_text(): every label here has a CSS
        'uppercase' class, and inner_text() returns the rendered (CSS-
        transformed, all-caps) text while text_content() returns the raw
        DOM text this module's label constants are written in."""
        rows = self.root.locator(loc.FIELD_CONTAINER)
        return [rows.nth(i).locator("label").text_content().strip() for i in range(rows.count())]

    def selected_option_text(self, label_text):
        """The visible text of a <select>'s currently selected option --
        NOT the same as Locator.input_value(), which returns the option's
        underlying 'value' attribute (e.g. a raw database id) instead of
        the label a user actually sees."""
        return self.field(label_text).evaluate("e => e.options[e.selectedIndex]?.text ?? ''")

    def select_option_values(self, label_text):
        options = self.field(label_text).locator("option")
        return [options.nth(i).inner_text().strip() for i in range(options.count())]
