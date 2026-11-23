"""Selectors and texts of the Quotation history drawer, titled "Quotation workflow" (OP-13 / HU-06).

Confirmed against the real deployed app (2026-10-27):
  - It opens from the Status pill of a row in 'Quotes in Progress' and 'Historical Quotes' (the pill is a button with aria-haspopup="dialog" and the accessible name
    "<Status> - open history"). The drawer is an element with role="dialog" and aria-modal="true", 400 px wide, fixed at the right edge; behind it a fixed layer
    (class "fixed inset-0", 40% black) is the dark backdrop.
  - Header: an h2 "Quotation workflow", a line with the Quote # and a "Close" button. While the data loads the body shows "Loading history..."; a failed load shows
    "Could not load the history.". A short line under the timeline repeats what the drawer is ("Workflow grouped by phase ...").
  - Summary card: a <dl> with three rows: Status (a pill), Current phase and "Waiting on:" (the name and role, "<name> · <ROLE>", or an em dash).
  - Timeline: an <ol> of phase groups; each group has an h3 with the phase title ("Case origin", "WO Quoting · AM/FPM/FSM", "BU Review", "OEM Review") and an <ol> of
    entries. Each entry (<li>) holds: the actor (span.truncate), the role chip (next span), an optional "Here" badge, the action chip (p.inline-flex), the reason
    (p.whitespace-pre-line, clamped to 4 lines, with a "Show more" / "Show less" button when it is longer), the note (a plain p) and the date (p.font-mono, "YYYY-MM-DD HH:mm",
    or "In progress" for the current step).
  - The current approver's entry has the action chip "Under review", the note "No decision yet." and the "Here" badge.
"""
import re

DIALOG_ROLE = "dialog"
TITLE_TEXT = "Quotation workflow"
CLOSE_BUTTON_TEXT = "Close"
LOADING_TEXT = "Loading history..."
LOAD_ERROR_TEXT = "Could not load the history."
SHOW_MORE_TEXT = "Show more"
SHOW_LESS_TEXT = "Show less"
DRAFT_WITHOUT_QUOTE_TEXT = "Draft · no Quote #"
EMPTY_VALUE = "—"

SUMMARY_LABELS = ("Status", "Current phase", "Waiting on")
PHASE_TITLES = ("Case origin", "WO Quoting · AM/FPM/FSM", "BU Review", "OEM Review")
ROLE_CHIPS = ("AM", "FPM/FSM", "BU", "CEO", "OEM")
DATE_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}$")

ACTION_CREATED = "Created / drafted"
ACTION_SUBMITTED = "Submitted for review"
ACTION_RESUBMITTED = "Re-submitted for review"
ACTION_APPROVED = "Approved"
ACTION_REJECTED = "Rejected"
ACTION_UNDER_REVIEW = "Under review"

NOTE_CREATED_MANUAL = "Created manually"
NOTE_CREATED_DOCUMENT = "Created from an uploaded document"
NOTE_FIRST_SUBMIT = "Quotation prepared and sent to the signature circuit"
NOTE_RESUBMIT = "Corrected and sent back to the signature circuit"
NOTE_FPM_APPROVED = "Returned to the AM before the next level"
NOTE_FORWARDED = "Forwarded to the next level"
NOTE_OEM_APPROVED = "Final approval"
NOTE_NO_DECISION = "No decision yet."
NOTE_OEM_WAITING_TITLE = "Waiting on OEM approval"
NOTE_OEM_WAITING = "The OEM decides from the link in the email"

CURRENT_DATE_TEXT = "In progress"
HERE_BADGE_TEXT = "Here"

STATUS_PILL_NAME_SUFFIX = "open history"
EVENTS_API_PATTERN = re.compile(r".*/api/quotations/[0-9a-f-]+/events.*")
