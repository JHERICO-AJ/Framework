"""Selectors for the "Setup Approval Progress" modal (OP-24 / HU-16) of the
Quotation (WO Creation) form.

Confirmed against the real deployed app (2026-09-28): the modal has ONE
unified "ADDED SIGNERS" list (not the 3 separate groups -- Quote/BU/OEM
Approving Personnel -- Jira's own AC#2 and V13/V14 document), driven by a
single search box that does directory-first, manual-entry-fallback lookup.
"""
TRIGGER_BUTTON_TEXT = "Setup Approval Progress"
MODAL_HEADING_TEXT = "APPROVED PERSONNEL SETTINGS"

SEARCH_PLACEHOLDER = "Name, email or role..."   # was "...or business unit..." before the 2026-10-20 build
MANUAL_NAME_PLACEHOLDER = "First and last name"
MANUAL_EMAIL_PLACEHOLDER = "name@company.com"

ADD_BUTTON_TEXT = "Add"
REMOVE_BUTTON_TEXT = "Remove"
SAVE_SIGNERS_BUTTON_TEXT = "Save signers"

NO_SIGNERS_TEXT = "No signers added yet."
DEFAULT_APPROVER_HEADING = "DEFAULT APPROVER FOR THIS AMOUNT"
NOT_IN_DIRECTORY_TEXT = "NOT IN THE DIRECTORY"
ONE_AT_A_TIME_TEXT = "One at a time only."
