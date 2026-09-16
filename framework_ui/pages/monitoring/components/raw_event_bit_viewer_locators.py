"""Selectors for the Raw Event Bit Viewer card (Data & Monitoring --
docs/OF-381.txt): evt1/evt2/pcsevt1 compacted bitfield words + a "Decode"
button opening the Event bit decode modal. Always live, no 24h/7d/30d
applicability (CA-05), same pattern as Thermal Diagnostics/Site Load &
Backup Context.

Confirmed against the real deployed app (2026-09-13, BOLIVIA).
"""
TITLE_TEXT = "Raw Event Bit Viewer"
CARD_TITLE = ".card-title"
SUBTITLE = ".card-subtitle"
FOOTER_HELP_TEXT = ".card-soft > .link-text"

BIT_ROW = ".bit-row"
BIT_LABEL = ".bit-label"
BIT_VALUE = ".metric-value"

DECODE_BUTTON = ".event-bit-decode-open"

# Decode modal -- confirmed 2026-09-13, NOT the same shared
# .monitoring-modal-* component as Event Log/Alarm History/Telemetry
# snapshots (no window buttons, no pagination -- it's a simple summary +
# grouped-by-field table), but does reuse the same overlay/container/
# title/close class names.
OVERLAY = ".monitoring-modal-overlay"
MODAL_TITLE = f"{OVERLAY} .monitoring-modal-title"
MODAL_SUBTITLE = f"{OVERLAY} .monitoring-modal-subtitle"
MODAL_CLOSE_BUTTON = f"{OVERLAY} .monitoring-modal-close"

DECODE_ROOT = f"{OVERLAY} .event-bit-decode"
DECODE_SUMMARY = f"{DECODE_ROOT} .event-bit-decode-summary"
DECODE_SUMMARY_WORD = f"{DECODE_SUMMARY} .event-bit-decode-word"
DECODE_SUMMARY_META = f"{DECODE_SUMMARY} .event-bit-decode-meta"

DECODE_COUNT = f"{DECODE_ROOT} .event-bit-decode-count"
DECODE_GROUP = f"{DECODE_ROOT} .event-bit-decode-group"
DECODE_GROUP_FIELD_TITLE = ".event-bit-decode-field"
DECODE_TABLE = ".event-bit-decode-table"
DECODE_TABLE_ROW = f"{DECODE_TABLE} tbody tr"
