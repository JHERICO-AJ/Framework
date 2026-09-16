"""Selectors for the PCS Energy Statistics card (Data & Monitoring --
docs/OF-150.txt): a 2-block period-energy summary (PCS Charge Energy, PCS
Discharge Energy), following the page's GLOBAL 24h/7d/30d selector (no
selector of its own -- CA-03).

Confirmed against the real deployed app (2026-09-11, BOLIVIA). Same
`.card`-scoped-by-title pattern as every other card in this module.
"""
TITLE_TEXT = "PCS Energy Statistics"
CARD_TITLE = ".card-title"
SUBTITLE = ".card-subtitle"

TIME_RANGE_BADGE = ".monitoring-time-range-badge"
TIME_RANGE_PERIOD = ".monitoring-time-range-period"

BLOCK = ".device-card"
BLOCK_TITLE = ".device-card-title"
BLOCK_VALUE = ".metric-value"
BLOCK_HELP_TEXT = ".device-card-body span"
