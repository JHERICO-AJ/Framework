"""SignerAssignment -- reusable component: the "Setup Approval Progress"
modal (OP-24 / HU-16) of the Quotation (WO) Creation form.

Confirmed differences between the documented spec (Jira OP-24, HUsACC,
Quotation_Spec_bilingual_V13/V14) and the real deployed app (2026-09-28):
  - (Fixed 2026-10) The modal shows a DEFAULT APPROVER FOR THIS AMOUNT block (Jason Park / BU OFFICE / CEO OFFICE
    for the 3 thresholds) and Submit adds the default approver (Approvers.EsAutoAsignado = 1).
  - There is a single unified "ADDED SIGNERS" list, not the 3 separate
    approver groups (Quote/BU/OEM Approving Personnel) with their own "+"
    control (V13/V14). Since 2026-10-05 Jira OP-24 no longer requires the groups.
  - The directory has no employee tagged "COO", and no role literally named
    "BU Manager" (the closest is "BU Director") -- searching either term
    falls straight to the manual/external fallback.
  - Submit is never blocked: neither with 0 signers ("Save without
    approver" bypasses it) nor with a signer whose role doesn't meet the
    amount's required authorization level.
  - No audit trail of any kind (who added a signer, or when) is shown
    anywhere on the page.
  - The manual/external entry panel's own copy claims "One at a time
    only", but a second manual/external entry can be added right after the
    first with no blocking.
  - The manual-entry email field enables "Add" even for a value that is not
    a real email address (e.g. one starting with an emoji character).
  - The name/email maxlength attributes (200/300) are client-side only --
    bypassing them (e.g. via JS) still saves without any error.
"""
from __future__ import annotations

import re

from framework_ui.base.base_component import BaseComponent
from framework_ui.pages.quotation.components import signer_assignment_locators as loc


class SignerAssignment(BaseComponent):
    def __init__(self, page):
        super().__init__(page, root=page)

    def open(self):
        """CSS renders the modal heading as all-caps, but the real DOM text
        is mixed-case ('Approved Personnel Settings') -- same pitfall
        documented in fse_arrangement_locators.py -- so the heading match
        must be case-insensitive, not an exact all-caps string."""
        self.page.wait_for_timeout(800)
        self.page.get_by_role("button", name=loc.TRIGGER_BUTTON_TEXT, exact=True).click()
        self.page.get_by_text(re.compile(loc.MODAL_HEADING_TEXT, re.I)).first.wait_for(timeout=15000)
        return self

    def close_without_saving(self):
        """Discards unsaved signer changes -- confirmed via reopen (does
        NOT close the underlying WO Creation form)."""
        self.page.keyboard.press("Escape")
        self.page.wait_for_timeout(300)
        return self

    def search_field(self):
        return self.page.get_by_placeholder(loc.SEARCH_PLACEHOLDER)

    def search(self, term):
        field = self.search_field()
        field.click()
        field.press("Control+A")
        field.press("Delete")
        field.type(term, delay=20)
        self.page.wait_for_timeout(700)
        return self

    def directory_result(self, name):
        return self.page.get_by_role("button", name=name, exact=False)

    def manual_name_field(self):
        return self.page.get_by_placeholder(loc.MANUAL_NAME_PLACEHOLDER)

    def manual_email_field(self):
        return self.page.get_by_placeholder(loc.MANUAL_EMAIL_PLACEHOLDER)

    def add_button(self):
        return self.page.get_by_role("button", name=loc.ADD_BUTTON_TEXT, exact=True)

    def add_directory_result(self, name):
        self.directory_result(name).first.click()
        self.page.wait_for_timeout(500)
        return self

    def add_manual(self, name, email):
        self.manual_name_field().fill(name)
        self.manual_email_field().fill(email)
        self.add_button().click()
        self.page.wait_for_timeout(500)
        return self

    def remove_button_for(self, name):
        row = self.page.locator("text=" + name).locator(
            "xpath=ancestor::*[self::li or self::div][1]")
        return row.get_by_role("button", name=loc.REMOVE_BUTTON_TEXT, exact=True)

    def save(self):
        self.page.get_by_role("button", name=loc.SAVE_SIGNERS_BUTTON_TEXT, exact=True).click()
        self.page.wait_for_timeout(800)
        return self

    def default_approver_text(self):
        """The 'DEFAULT APPROVER FOR THIS AMOUNT' block of the modal (name, role badge and email), shown since the
        2026-10 build; it follows the quotation total (approval default rules)."""
        # the block is loaded right after the modal opens (it depends on the quotation total)
        self.page.get_by_text(re.compile(loc.DEFAULT_APPROVER_HEADING, re.I)).first.wait_for(timeout=10000)
        self.page.wait_for_timeout(300)
        text = self.page.evaluate("() => document.body.innerText")
        start = text.find(loc.DEFAULT_APPROVER_HEADING)
        end = text.find("ADDED SIGNERS", start)
        return " ".join(text[start:end].split()) if start >= 0 and end > start else ""

    def body_text(self):
        return self.page.evaluate("() => document.body.innerText")
