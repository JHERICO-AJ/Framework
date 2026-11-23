"""Selectors and texts of the Quotation landing list: the two tabs, the toolbar (three filters, search, Clear), the table and the pager
(OP-12 / HU-05 "Historical Quotes"; the table of "Quotes in Progress" is the same component).

Confirmed against the real deployed app (2026-10-26):
  - The tabs are two buttons in one pill: "Quotes in Progress (N)" and "Historical Quotes (N)"; the active tab shows its number in a span, the other shows none.
  - The toolbar has, in this order: the tabs, the selects OEM ("All OEMs"), Site ("All Sites"), Type of Work ("All Types") -- "Quotes in Progress" also has a fourth
    select, Item ("All" / workflow stages) -- the search box and a "Clear" button. While their options load, the OEM and Type of Work selects are disabled and show "Loading...".
  - The table is a CSS grid, not a <table>: a header row of 8 cells and one grid per quotation. Inside a row, one button (class "group") holds the first 7 cells (WO / Quote #
    with two lines -- GSP # and Quote # --, WO Title, Site, Waiting on as "<name> · <ROLE>", Age, Current step, Source) and a second button, the status pill, has the accessible
    name "<Status> - open history". Clicking the first button opens the quotation, clicking the pill opens the history panel.
  - The pager is a span "Page X of Y" next to the buttons Previous and Next; a button that cannot be used carries the disabled attribute.
The global search box in the page header ("Search site / device / WO ID") is NOT the list's search box.
"""
import re

TAB_IN_PROGRESS_TEXT = "Quotes in Progress"
TAB_HISTORICAL_TEXT = "Historical Quotes"
TAB_COUNT_PATTERN = re.compile(r"\((\d+)\)")

CLEAR_BUTTON_TEXT = "Clear"
FILTER_ALL_LABELS = {"oem": "All OEMs", "site": "All Sites", "type": "All Types"}
FILTER_POSITION = {"oem": 0, "site": 1, "type": 2}           # among the selects inside the toolbar
ITEM_FILTER_ALL_LABEL = "Item"
SEARCH_MAX_LENGTH = 300

HEADER_TEXTS = ["WO / Quote #", "WO Title", "Site", "Waiting on", "Age", "Current step", "Source", "Status"]
ROW_BUTTON = "button.group"
STATUS_PILL = "button[aria-haspopup='dialog']"
PAGER_TEXT_PATTERN = re.compile(r"Page \d+ of \d+")
PREVIOUS_BUTTON_TEXT = "Previous"
NEXT_BUTTON_TEXT = "Next"

MESSAGE_NO_HISTORICAL = "There are no historical quotations yet."
MESSAGE_NO_RESULTS = "No results for this filter."
MESSAGE_LOADING = "Loading quotations..."
MESSAGE_LOAD_ERROR = "Could not load quotations."
MESSAGE_SITES_ERROR = "Some sites couldn't be loaded"
MESSAGE_NO_ROLE = "Quotation access requires an AM, FPM/FSM, BU, or CEO role assignment."   # build of 2026-11-09 (OP-145 fixed: the CEO is named; the story lists BU before FPM/FSM, the order is not significant)
PENDING_APPROVAL_TEXT = "Pending approval"

LIST_API_PATH = "/api/quotations?"                  # the list call: page, pageSize, includeClosed, oemName, siteName, typeOfWork, search
