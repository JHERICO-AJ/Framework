"""Selectors for the "Browse snapshots" modal (Telemetry -- Historical
snapshot), opened from the Telemetry Data Table's "Browse snapshots"
button.

Confirmed against the real deployed app (2026-09-09)."""
OVERLAY = ".monitoring-modal-overlay"
TITLE = f"{OVERLAY} .monitoring-modal-title"
SUBTITLE = f"{OVERLAY} .monitoring-modal-subtitle"
CLOSE_BUTTON = f"{OVERLAY} .monitoring-modal-close"

SUBSYSTEM_SELECT = f"{OVERLAY} .monitoring-modal-toolbar select.select"
WINDOW_BUTTON = f"{OVERLAY} .monitoring-modal-filter-btn"
WINDOW_BUTTON_ACTIVE = f"{OVERLAY} .monitoring-modal-filter-btn.active"

TABLE = f"{OVERLAY} .monitoring-modal-table-wrap table"
HEADER_CELL = f"{TABLE} thead th"
ROW = f"{TABLE} tbody tr"

PAGINATION_INFO = f"{OVERLAY} .monitoring-pagination-info"
PAGINATION_CHRONOLOGY = f"{OVERLAY} .monitoring-pagination-chronology"
PAGE_SIZE_SELECT = f"{OVERLAY} .monitoring-pagination-size-select"
PREV_PAGE_BUTTON = f"{OVERLAY} .monitoring-pagination-controls button[aria-label='Previous page']"
NEXT_PAGE_BUTTON = f"{OVERLAY} .monitoring-pagination-controls button[aria-label='Next page']"
PAGE_INPUT = f"{OVERLAY} .monitoring-pagination-page-input input"

SNAPSHOT_NOTE = f"{OVERLAY} .monitoring-modal-snapshot-note"
FOOTER_CLOSE_BUTTON = f"{OVERLAY} .monitoring-modal-footer button.btn-outline"
