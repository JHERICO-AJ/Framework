"""Selectors for the Alarm History card (Data & Monitoring -- docs/OF-148.txt):
a live table (Time/Device/Alarm/Severity/Status) plus a "Browse history"
modal -- Event Log's direct sibling in the same "Logs" section.

Confirmed against the real deployed app (2026-09-11, BOLIVIA, live PCS
alarms). `.card` is reused across many sections, so CARD is scoped by its
own title text -- same `.filter(has=...has_text=...)` pattern as every
other card in this module.
"""
TITLE_TEXT = "Alarm History"
CARD_TITLE = ".card-title"

TIME_RANGE_BADGE = ".monitoring-time-range-badge"
TIME_RANGE_PERIOD = ".monitoring-time-range-period"
SUBTITLE = ".card-subtitle"

BROWSE_HISTORY_BUTTON = ".monitoring-history-open-btn"

TABLE_HEADER_CELL = "table thead th"
TABLE_ROW = "table tbody tr"
TABLE_CELL = "td"

# Confirmed live: each live row carries this class + a "Filter telemetry by
# this device" title -- CA-17's row-click-to-filter-Telemetry-Data-Table
# affordance.
TABLE_ROW_CLICKABLE = "tr.telemetry-filter-row"

# Severity pill (CA-13) and WO-status badge (CA-14) -- confirmed live:
# sev-pill has a per-severity modifier class (sev-warning blue, sev-critical
# red); wo-status always carries wo-open plus a colored wo-dot.
SEVERITY_PILL = ".sev-pill"
STATUS_BADGE = ".wo-status"

# Browse history modal -- confirmed 2026-09-11 against the real deployed
# app, same shared modal component as Event Log's own "Browse history"
# (event_log_locators.py) and Telemetry Data Table's "Browse snapshots" --
# reusing its exact class names rather than guessing new ones.
OVERLAY = ".monitoring-modal-overlay"
MODAL_TITLE = f"{OVERLAY} .monitoring-modal-title"
MODAL_SUBTITLE = f"{OVERLAY} .monitoring-modal-subtitle"
MODAL_CLOSE_BUTTON = f"{OVERLAY} .monitoring-modal-close"

WINDOW_BUTTON = f"{OVERLAY} .monitoring-modal-filter-btn"
WINDOW_BUTTON_ACTIVE = f"{OVERLAY} .monitoring-modal-filter-btn.active"

MODAL_TABLE = f"{OVERLAY} .monitoring-modal-table-wrap table"
MODAL_HEADER_CELL = f"{MODAL_TABLE} thead th"
MODAL_ROW = f"{MODAL_TABLE} tbody tr"
# 24h rows split day/clock into two spans; 7d/30d rows use a single
# full-datetime span instead (both confirmed live 2026-09-11, same pattern
# as Event Log's own modal -- CA-28).
MODAL_ROW_TIME_DAY = ".monitoring-modal-time-day"
MODAL_ROW_TIME_CLOCK = ".monitoring-modal-time-clock"
MODAL_ROW_TIME_DATETIME = ".monitoring-modal-time-datetime"

MODAL_ROW_SEVERITY_PILL = ".sev-pill"
MODAL_ROW_STATUS_BADGE = ".wo-status"

# Day-range filter -- only present for 7d/30d windows (CA-25), confirmed
# live 2026-09-11.
DAY_RANGE = f"{OVERLAY} .monitoring-modal-day-range"
DAY_RANGE_FROM_SELECT = f"{DAY_RANGE} .monitoring-modal-day-range-field:has(span:text-is('From')) select"
DAY_RANGE_TO_SELECT = f"{DAY_RANGE} .monitoring-modal-day-range-field:has(span:text-is('To')) select"
DAY_RANGE_SUMMARY = f"{DAY_RANGE} .monitoring-modal-day-range-summary"
DAY_RANGE_WARNING = f"{DAY_RANGE} .monitoring-modal-day-range-warning"

# Pagination (CA-24) and the modal's own "no live updates" footer note
# (reinforces CA-21) -- confirmed live 2026-09-11.
PAGINATION_INFO = f"{OVERLAY} .monitoring-pagination-info"
PAGE_SIZE_SELECT = f"{OVERLAY} .monitoring-pagination-size-select"
PREV_PAGE_BUTTON = f"{OVERLAY} .monitoring-pagination-controls button[aria-label='Previous page']"
NEXT_PAGE_BUTTON = f"{OVERLAY} .monitoring-pagination-controls button[aria-label='Next page']"
PAGE_INPUT = f"{OVERLAY} .monitoring-pagination-page-input input"
JUMP_TO_LATEST_BUTTON = f"{OVERLAY} .monitoring-pagination-jump-btn[title='Jump to latest']"
JUMP_TO_OLDEST_BUTTON = f"{OVERLAY} .monitoring-pagination-jump-btn[title='Jump to oldest']"
SNAPSHOT_NOTE = f"{OVERLAY} .monitoring-modal-snapshot-note"

# Telemetry Data Table -- CA-17's click target (row click filters this
# table by device and scrolls to it).
TELEMETRY_TABLE_CONTAINER_ID = "monitoring-telemetry-table"
TELEMETRY_SUBSYSTEM_SELECT = f"#{TELEMETRY_TABLE_CONTAINER_ID}"
