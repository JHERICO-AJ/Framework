"""Selectors for the decision bar (HU-22 / OP-31): the Recommendation field with the Reject and Approve buttons
at the bottom of a quotation, shown only to the approver whose turn it is.

Confirmed against the real deployed app (2026-10-20): the field is a single-line <input> with maxlength 1000 and the
placeholder below; the bar sits next to the Budget Summary button; after a decision the approver is sent back to the
Pending approval list.
"""
RECOMMENDATION_PLACEHOLDER = "Recommendation (required for Approve/Reject)"
REJECT_BUTTON_TEXT = "Reject"
APPROVE_BUTTON_TEXT = "Approve"
SAVING_BUTTON_TEXT = "Saving..."
DEFAULT_ERROR_TEXT = "Could not save this decision."
MAX_LENGTH = 1000
COUNTER_STARTS_AT = 900

PENDING_APPROVAL_TAB_TEXT = "Pending approval"
