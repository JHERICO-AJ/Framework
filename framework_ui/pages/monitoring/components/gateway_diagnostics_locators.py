"""Selectors for the Gateway Diagnostics card row (Communication Status /
Gateway ID / MAC ID / Data Freshness), each its own ".gateway-card" tile
inside ".gateway-grid".

Confirmed against the real deployed app (2026-09-04)."""
GRID = ".gateway-grid"
CARD = ".gateway-card"
CARD_TITLE = ".device-card-title"
# The main value can render as ".metric-value" (Communication Status,
# Gateway ID, MAC ID) or ".status" (Data Freshness) -- comma-selector
# covers both without needing to know which card uses which up front.
CARD_VALUE = ".metric-value, .status"
MINI_METRIC_ROW = ".mini-metrics > div"
MINI_METRIC_LABEL = "span"
MINI_METRIC_VALUE = "strong"
