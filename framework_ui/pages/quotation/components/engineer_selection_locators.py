"""Selectors for the "Engineer Selection" panel (OP-28 / HU-10) of the
Quotation (WO) Creation form -- shown when the "FSE Select (Variable Rate)"
tab is active (see fse_arrangement.py for the tab-switch mechanics and the
"Site Selection Required" precondition).

Confirmed against the real deployed app (2026-09-25): same no-id/name,
"div.flex.flex-col.gap-1" field container convention as WO Snapshot and FSE
Arrangement.

Confirmed field types:
  - Support Engineers is a +/- stepper (aria-labelled buttons + a <span>
    value), not a plain <input> -- the decrease button is natively disabled
    at the minimum (1), rather than showing a validation error.
  - Planned Check-in/out and Possible Check-in/out are native
    <input type="datetime-local">.
  - Field Leader is a <select>, natively disabled while no engineer is
    selected (not just showing an empty option).
"""
SECTION_HEADING = "Engineer Selection"
FIELD_CONTAINER = "div.flex.flex-col.gap-1"

LABEL_SUPPORT_ENGINEERS = "Support Engineers"
LABEL_PLANNED_CHECK_IN = "Planned Check-in"
LABEL_PLANNED_CHECK_OUT = "Planned Check-out"
LABEL_POSSIBLE_CHECK_IN = "Possible Check-in"
LABEL_POSSIBLE_CHECK_OUT = "Possible Check-out"
LABEL_FIELD_LEADER = "Field Leader"

MAP_BUTTON_TEXT = "MAP"
MAP_CLOSE_BUTTON_TEXT = "Close"
DECREASE_SUPPORT_ENGINEERS_ARIA_LABEL = "Decrease support engineers"
INCREASE_SUPPORT_ENGINEERS_ARIA_LABEL = "Increase support engineers"

# ENGINEER SELECTION MAP sub-window (HU-11 / OP-29)
MAP_MODAL_HEADING = "ENGINEER SELECTION MAP"
MAP_SEARCH_PLACEHOLDER = "Name, email, or city"
MAP_CONTRACTOR_NAME_PLACEHOLDER = "e.g. John Smith"
MAP_CONTRACTOR_PHONE_PLACEHOLDER = "+1 555-0199"
MAP_CONTRACTOR_LOCATION_PLACEHOLDER = "e.g. Dallas, TX"
MAP_ADD_SELECT_CONTRACTOR_BUTTON = "Add & Select Contractor"
MAP_CONTRACTOR_ROLE_TEXT = "CONTRACTOR"
