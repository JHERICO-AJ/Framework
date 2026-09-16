"""Selectors for the Fault Localization card (Data & Monitoring --
docs/OF-153.txt): 3 device-card blocks (Highest V, Lowest V, Temperature)
holding 8 rack/pack/cell location rows -- always live via diagnostics push
(~5s), no 24h/7d/30d applicability (CA-05), same .device-card/.bit-row
pattern as Site Load & Backup Context/Raw Event Bit Viewer.

Confirmed against the real deployed app (2026-09-13, BOLIVIA -- all 8 rows
show N/A, matching the HU's documented Fractal gap: no BMS string/rack
telemetry mapped yet).
"""
TITLE_TEXT = "Fault Localization"
CARD_TITLE = ".card-title"
SUBTITLE = ".card-subtitle"

GRID = ".fault-grid"
DEVICE_CARD = ".device-card"
BIT_ROW = ".bit-row"
BIT_LABEL = ".bit-label"
BIT_VALUE = "strong"

# Documented row order (HU CA-24: 8 rows in 3 cards).
HIGHEST_V_ROWS = ["Highest V rack", "Highest V pack", "Highest V cell"]
LOWEST_V_ROWS = ["Lowest V rack", "Lowest V pack", "Lowest V cell"]
TEMP_ROWS = ["Highest temp rack", "Lowest temp rack"]
ALL_ROWS = HIGHEST_V_ROWS + LOWEST_V_ROWS + TEMP_ROWS

# CONFIRMED DEFECT (2026-09-13): the live app shows the literal text
# "N/A" for absent rows; the correct/expected placeholder is "—" (a dash),
# per the HU's own format table example, team-lead confirmation, and the
# sitewide convention (see tests/ui/monitoring/test_fault_localization.py).
NA_UI_TEXT = "N/A"
NA_EXPECTED_TEXT = "—"
