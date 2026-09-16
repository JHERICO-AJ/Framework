"""Selectors for the Thermal Diagnostics card (Data & Monitoring --
docs/OF-149.txt): a 3-block site-level thermal summary (Cell Temperature
Delta, Highest / Lowest Temp, Average Cell Temp) -- always live, no
24h/7d/30d applicability (CA-05).

Confirmed against the real deployed app (2026-09-11, BOLIVIA). Same
`.card`-scoped-by-title pattern as every other card in this module
(`.filter(has=...has_text=...)`, not `:text-is()`, per the same
CSS-uppercase caveat already documented for Battery Diagnostics).
"""
TITLE_TEXT = "Thermal Diagnostics"
CARD_TITLE = ".card-title"
SUBTITLE = ".card-subtitle"

# No .monitoring-time-range-badge / .monitoring-time-range-period anywhere
# in this card -- confirmed live 2026-09-11, matching CA-05 ("El rango
# 24h/7d/30d no cambia estos valores"): unlike Site Power Telemetry or
# Event Log, this card doesn't even show a badge, since the concept of a
# historical range doesn't apply to it at all (always-live aggregate).

BLOCK = ".device-card"
BLOCK_TITLE = ".device-card-title"
BLOCK_VALUE = ".metric-value"
BLOCK_HELP_TEXT = ".device-card-body span"

# Each block's number(s) + unit are nested spans, not plain text -- reused
# thermal-* class names, always queried relative to one block.
THERMAL_PAIR = ".thermal-pair"
THERMAL_NUMBER = ".thermal-number"
THERMAL_UNIT = ".thermal-unit"
THERMAL_SEP = ".thermal-sep"
