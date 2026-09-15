"""Selectors for the Telemetry Data Table (Data & Monitoring, top row next
to the Device Status Panel -- docs/OF-141.txt).

Confirmed against the real deployed app (2026-09-09). `.card` is reused
across many sections (same issue already documented for `.device-card`), so
CARD is scoped by its own title text rather than a dedicated class.

The Live table body is a virtualized list (react-window style): row 0 is
always an `aria-hidden` spacer with no `data-index` and no real cells --
ROW excludes it by requiring `[data-index]`.
"""
TITLE_TEXT = "Telemetry Data Table"
CARD = f".card:has(.card-title:text-is('{TITLE_TEXT}'))"

SUBSYSTEM_SELECT = f"{CARD} select.select"
BROWSE_SNAPSHOTS_BUTTON = f"{CARD} button.monitoring-history-open-btn"
LIVE_CHIP = f"{CARD} .chip"

SCROLL_CONTAINER = f"{CARD} #monitoring-telemetry-table"
TABLE = f"{CARD} table.telemetry-data-table"
HEADER_CELL = f"{TABLE} thead th"
ROW = f"{TABLE} tbody tr[data-index]"
EMPTY_STATE = f"{TABLE} tbody .empty-state"
QUALITY_BADGE = ".quality"
