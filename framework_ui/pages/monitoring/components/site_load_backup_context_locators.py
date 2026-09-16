"""Selectors for the Site Load & Backup Context card (Data & Monitoring --
docs/OF-152.txt): 2 metric blocks (Real Load, Estimated Backup) plus a
3-row "lateral" block (ATS / grid transfer, Net power, Context) -- always
live, no 24h/7d/30d applicability (CA-05), same pattern as Thermal
Diagnostics.

Confirmed against the real deployed app (2026-09-13, BOLIVIA).
"""
TITLE_TEXT = "Site Load & Backup Context"
CARD_TITLE = ".card-title"
SUBTITLE = ".card-subtitle"

BLOCK = ".device-card"
BLOCK_TITLE = ".device-card-title"
BLOCK_VALUE = ".metric-value"
BLOCK_HELP_TEXT = ".device-card-body span"

# The 3rd block ("lateral") has no its own title -- just 3 label/value rows
# (bit-row/bit-label, same reused pattern as Gateway Diagnostics' mini-metrics
# and Fault Localization).
LATERAL_BLOCK = ".site-load-stack"
BIT_ROW = ".bit-row"
BIT_LABEL = ".bit-label"
BIT_VALUE = "strong"
