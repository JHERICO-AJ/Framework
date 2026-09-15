"""Selectors for the Environmental Monitoring card (Data & Monitoring --
docs/OF-151.txt): 2 device-card blocks (Ambient Temp, Humidity), each an
independently-resolved On-site (SYS sensor) vs API (Intake external
weather fallback) value -- always live, no 24h/7d/30d applicability
(CA-05), same .device-card/.metric-value pattern as PCS Energy
Statistics/Site Load & Backup Context.

Confirmed against the real deployed app (2026-09-13, BOLIVIA).
"""
TITLE_TEXT = "Environmental Monitoring"
CARD_TITLE = ".card-title"
SUBTITLE = ".card-subtitle"

BLOCK = ".device-card"
BLOCK_TITLE = ".device-card-title"
BLOCK_VALUE = ".metric-value"
BLOCK_SOURCE_FLAG = ".metric-source"
BLOCK_HELP_TEXT = ".device-card-body .metric-desc"

AMBIENT_TEMP_TITLE = "Ambient Temp"
HUMIDITY_TITLE = "Humidity"

NA_TEXT = "—"
ON_SITE_SOURCE = "On-site"
API_SOURCE = "API"
