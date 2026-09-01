"""Selectors for the Sites List section: a real <table> nested inside
.sites-table-body (itself inside .sites-table). Confirmed against the real
deployed app (2026-08-26). Real header order:
    Site | Status | Critical | SoC | Power (kW) | Last Seen
SoC is rendered as a visual bar (.soc-bar > .soc-fill, width:N%), not text.
"""
TABLE = ".sites-table"
HEADER_CELL = ".sites-table thead th"
ROW = ".sites-table tbody tr"
CELL = "td"
STATUS_PILL = ".status-pill"
SOC_FILL = ".soc-fill"
