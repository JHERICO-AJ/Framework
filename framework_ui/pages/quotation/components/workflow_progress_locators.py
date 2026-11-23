"""Selectors for the Workflow Progress widget (OP-25 / HU-07), reachable
from the "Current step: <state>" button in the WO Creation form's header.

Confirmed against the real deployed app (2026-09-27):
  - The trigger is a single button, accessible name starting with "Open
    workflow progress." (its full accessible name embeds the current step,
    e.g. "Open workflow progress. Current step: WO Quoting").
  - Clicking it opens a "WORKFLOW PROGRESS" modal containing an inline SVG
    (role="img", accessible name "Quotation workflow progress diagram")
    with 5 column headers -- EVENT LEVEL, AM/FPM/FSM LEVEL, BU LEVEL,
    OEM LEVEL, FSE LEVEL -- differing from the literal shorthand in Jira's
    own AC #1 ("Event, PM, BU, Vendor, FSE"); not treated as a defect since
    V13's own detailed narrative uses these same AM/FPM/FSM/OEM role names
    throughout.
  - Each node is an SVG <g>, with a <rect> (border/fill) and 3 <text>
    labels (title, subtitle, status). The status text reads a real
    timestamp ("YYYY-MM-DD HH:MM") once a step is completed, "Pending" for
    the current step and any not-yet-reached step -- completion is
    reliably distinguished by the timestamp, not by the word itself.
  - The current node's <g> carries filter="url(#workflow-current-glow)"
    plus a filled rect and a thicker (2 vs 1.5/1.25) stroke -- confirmed by
    dumping the raw SVG, not by eyeballing the render (the completed node's
    own brighter-than-pending border can look similar to the glow at a
    glance).
  - The modal has only a "Close" button; clicking any node (pending,
    current or completed) never changes the current step (read-only).
  - Two distinct error states exist on a load failure: a page-level
    "Could not load this quotation." (whole record fetch fails) and a
    widget-level "Could not load workflow progress" / "The workflow
    diagram is unavailable right now..." (only the diagram's own fetch
    fails, reachable by cutting network only AFTER a quotation is already
    open, then clicking the trigger button).
"""
TRIGGER_BUTTON_ACCESSIBLE_NAME = "Open workflow progress"
MODAL_HEADING = "WORKFLOW PROGRESS"
MODAL_CLOSE_BUTTON_TEXT = "Close"
SVG_ACCESSIBLE_NAME = "Quotation workflow progress diagram"
CURRENT_STEP_TEXT_PREFIX = "Current step:"
CURRENT_GLOW_FILTER_ID = "workflow-current-glow"

COLUMN_HEADINGS = ["EVENT LEVEL", "AM/FPM/FSM LEVEL", "BU LEVEL", "OEM LEVEL", "FSE LEVEL"]

PAGE_LEVEL_LOAD_FAILURE_TEXT = "Could not load this quotation."
WIDGET_LEVEL_LOAD_FAILURE_HEADING = "Could not load workflow progress"
