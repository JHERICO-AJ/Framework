"""Selectors for the Dispatch Limits & Tracking card (Data & Monitoring --
docs/OF-145.txt): a 6-block dispatch/setpoint/DC-bus summary, not a table
or chart.

Confirmed against the real deployed app (2026-09-10). `.card` is reused
across many sections (same issue already documented for other cards in
this module), so CARD is scoped by its own title text rather than a
dedicated class. NOT built with `:text-is(...)` (with or without the `i`
flag): the real DOM title is "Dispatch Limits & Tracking" but CSS renders
it uppercase, and `:text-is()i` was already confirmed unreliable against
this same uppercase-transform pattern for other cards this session --
`.filter(has=...has_text=...)` (substring, case-insensitive by default)
is the version that actually works.
"""
TITLE_TEXT = "Dispatch Limits & Tracking"
CARD_TITLE = ".card-title"

# Each of the 6 blocks (Charge Limit, Discharge Limit, PCS Setpoint,
# Actual PCS Power, DC Bus Voltage, DC Bus Current -- CA-03) is one
# ".device-card" inside the card's grid. Same reused class names as
# Battery Diagnostics/Device Status Panel's own blocks -- always queried
# relative to CARD (see DispatchLimitsTracking.card()), never as a
# bare page-wide selector, so they don't collide with those other cards'
# own blocks.
BLOCK = ".device-card"
BLOCK_LABEL = ".device-card-title"
BLOCK_VALUE = ".metric-value"
