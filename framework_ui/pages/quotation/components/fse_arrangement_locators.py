"""Selectors for the FSE Arrangement tab (OP-20 / HU-09) of the Quotation
(WO Creation) form.

Confirmed against the real deployed app (2026-09-24): same no-id/name
convention as WO Snapshot (wo_snapshot_locators.py) -- every field is a
plain <label> immediately followed by its <input>/<select> inside a shared
"div.flex.flex-col.gap-1" container. Each of the 4 cost blocks is its own
<section>, identified by an <h2> heading with the block's real (mixed-case)
title -- CSS renders it uppercase, but text_content()/get_by_role("heading")
matching must use the real casing below.

The panel that holds all 4 blocks scrolls internally (AC-103 / Qase #821)
-- WO Snapshot's own outer scroll is unaffected.

Confirmed field behavior (2026-09-24, live exploration):
  - Total Working Hour/Tech, Total Man Working Hours and Total Days are
    read-only calculated <div>s, not <input>s (see wo_snapshot.py's
    input-vs-computed distinction) -- computed fields must be read via
    inner_text(), not input_value().
  - "Travel & Drive Time" is the documented AC's name for what the live
    label actually reads "Travel / Drive Time".
"""
SECTION_HEADING_STATEMENT = "Statement of FSE Resource"
SECTION_HEADING_LABOR = "Labor Costs"
SECTION_HEADING_ONSITE = "Onsite Support Costs"
SECTION_HEADING_REIMBURSABLE = "Reimbursable Costs"

FIELD_CONTAINER = "div.flex.flex-col.gap-1"
ERROR_TEXT = "p.text-red-400"

TAB_FSE_ARRANGEMENT = "FSE Arrangement (Flat Rate)"
TAB_FSE_SELECT = "FSE Select (Variable Rate)"
SECTION_HEADING_ENGINEER_SELECTION = "Engineer Selection"
SITE_REQUIRED_MODAL_TEXT = "Site Selection Required"
SITE_REQUIRED_MODAL_ACCEPT_BUTTON_TEXT = "Accept"
LABEL_ENGINEER_SELECTION_SUPPORT_ENGINEERS = "Support Engineers"

# --- Statement of FSE Resource (9 fields) ---
LABEL_SUPPORT_ENGINEERS = "Support Engineers"
LABEL_WORKING_HOUR_TECH_DAY = "Working Hour / Tech Day"
LABEL_ESTIMATED_WORKING_DAYS = "Estimated Working Days"
LABEL_TOTAL_OVER_HOURS_TECH = "Total Over Hours / Tech"
LABEL_EST_START_TIME = "Est. Start Time"
LABEL_EST_END_TIME = "Est. End Time"
LABEL_TOTAL_WORKING_HOUR_TECH = "Total Working Hour / Tech"
LABEL_TOTAL_MAN_WORKING_HOURS = "Total Man Working Hours"
LABEL_TOTAL_DAYS = "Total Days"

STATEMENT_FIELDS = [
    LABEL_SUPPORT_ENGINEERS, LABEL_WORKING_HOUR_TECH_DAY, LABEL_ESTIMATED_WORKING_DAYS,
    LABEL_TOTAL_OVER_HOURS_TECH, LABEL_EST_START_TIME, LABEL_EST_END_TIME,
    LABEL_TOTAL_WORKING_HOUR_TECH, LABEL_TOTAL_MAN_WORKING_HOURS, LABEL_TOTAL_DAYS,
]

# --- Labor Costs (2 inputs + Subtotal) ---
LABEL_LABOR_COST_HOUR = "Labor Cost / Hour"
LABEL_LABOR_OVER_COST_HOUR = "Labor Over Cost / Hour"

# --- Onsite Support Costs (3 inputs + Subtotal) ---
LABEL_HOTEL_COST = "Hotel Cost"
LABEL_PER_DIEM = "Per Diem / Person"  # renamed from "Per Diem" (2026-10)
LABEL_TRAVEL_DRIVE_TIME = "Travel / Drive Time"  # documented as "Travel & Drive Time"

# --- Reimbursable Costs (5 inputs + Subtotal) ---
LABEL_AIR_TRANSPORTATION = "Air Transportation"
LABEL_CAR_EXPENSE = "Car Expense"
LABEL_MATERIAL_EXPENSE = "Material Expense"
LABEL_EQUIPMENT_RENTAL = "Equipment Rental"
LABEL_MISCELLANEOUS = "Miscellaneous"
LABEL_MISCELLANEOUS_NOTE = "Miscellaneous Note"

REIMBURSABLE_FIELDS = [
    LABEL_AIR_TRANSPORTATION, LABEL_CAR_EXPENSE, LABEL_MATERIAL_EXPENSE,
    LABEL_EQUIPMENT_RENTAL, LABEL_MISCELLANEOUS,
]
