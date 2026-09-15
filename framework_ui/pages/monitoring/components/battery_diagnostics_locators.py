"""Selectors for the Battery Diagnostics card (Data & Monitoring --
docs/OF-142.txt): a 4-block cell-health summary, not a table or chart.

Confirmed against the real deployed app (2026-09-10). `.card` is reused
across many sections (same issue already documented for other cards in
this module), so CARD is scoped by its own title text rather than a
dedicated class. NOT built with `:text-is(...)` (with or without the `i`
flag): the real DOM title is "Battery Diagnostics" but CSS renders it
uppercase, and `:text-is()i` was already confirmed unreliable against
this same uppercase-transform pattern for another card this session --
`.filter(has=...has_text=...)` (substring, case-insensitive by default)
is the version that actually works.
"""
TITLE_TEXT = "Battery Diagnostics"
CARD_TITLE = ".card-title"

# Each of the 4 blocks (Cell Voltage Delta, Balance Status, Average Cell
# Voltage, Highest / Lowest Cell -- CA-03) is one ".device-card" inside the
# card's ".monitor-metrics-grid". Reused class names from Device Status
# Panel's own cards -- always queried relative to CARD (see
# BatteryDiagnostics.card()), never as a bare page-wide selector, so they
# don't collide with those other cards' own blocks.
BLOCK = ".device-card"
BLOCK_LABEL = ".device-card-title"
BLOCK_VALUE = ".metric-value"
