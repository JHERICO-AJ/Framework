"""Selectors for the Quotation module shell (the landing list + the WO
Creation form's chrome). Field-level selectors for each form section live
in their own components/*_locators.py files.

Confirmed against the real deployed app (2026-09-22): the sidebar entry is
a plain <a class="nav-item" href="/quotation">, and the module has no
distinct route for the creation form -- clicking "Create Quotation" opens
it as an overlay on top of the same /quotation URL. The form's presence is
best detected via the "WO Snapshot" section heading, since the landing
list view never renders that text.
"""
SIDEBAR_LINK = 'a.nav-item[href="/quotation"]'
CREATE_QUOTATION_BUTTON_TEXT = "Create Quotation"
SUBMIT_QUOTATION_BUTTON_TEXT = "Submit Quotation"
SAVE_DRAFT_BUTTON_TEXT = "Save Draft"
CLOSE_BUTTON_TEXT = "CLOSE"
CURRENT_QUOTE_BUTTON_TEXT = "Current Quote"

# Landing list: search box + a row's bold WO/Quote # (confirmed 2026-09-23:
# "span.truncate.text-slate-100").
WO_NUMBER_SEARCH_PLACEHOLDER = "Search WO, Quote #, site..."   # the list search box (was "WO Number..." until the 2026-10 build)
WO_LIST_ROW_WO_NUMBER = "span.truncate.text-slate-100"

# Present only once the WO Creation form (manual/alarm/file) is open.
FORM_LOADED_MARKER_TEXT = "WO Snapshot"

# HU-20's CurrentConflictModal: shown by "Create Quotation" whenever a
# draft (from a previous, un-discarded session) already exists in
# localStorage -- confirmed live 2026-09-22, titled "Unsaved Quotation in
# Progress" with exactly these 3 buttons.
DISCARD_AND_START_NEW_BUTTON_TEXT = "Discard & Start New"
