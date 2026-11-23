"""Selectors for the Budget Summary panel (HU-15 / OP-23) in the footer of a quotation.

Confirmed against the real deployed app (2026-10-22): a footer button 'Budget Summary' (it reads 'Hide Budget Summary' while the panel is open)
opens a panel above the footer with three read-only cards (Est. Start Time, Est. End Time, Support Engineers), the tabs 'BU View' and
'OEM View', a 'Close' button, and ONE table <table class="table-fixed"> for the figures. BU View has a header row
'Description | Quotation/Revenue [| Expense]'; OEM View has no header row and two columns.
"""
BUTTON_OPEN_TEXT = "Budget Summary"
BUTTON_HIDE_TEXT = "Hide Budget Summary"
CLOSE_BUTTON_TEXT = "Close"
TAB_BU = "BU View"
TAB_OEM = "OEM View"
HEADING_TEXT = "BUDGET SUMMARY"
SHEET_TABLE = "table.table-fixed"
SECTION_TITLES = ("Statement of Work (SOW)", "Labor Cost", "Onsite Support Costs", "Reimbursable Costs")
NOT_AVAILABLE = "N/D"
