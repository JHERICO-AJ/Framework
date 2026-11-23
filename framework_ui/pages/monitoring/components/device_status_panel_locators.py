"""Selectors for the Device Status Panel (6 cards: Battery/BMS, PCS/Inverter,
HVAC/Thermal, EMS IPC & Gateway, Meters/CT-PT, Network/Tunnel).

Confirmed against the real deployed app (2026-09-04)."""
GRID = ".device-status-grid"
# Scoped to the grid: ".device-card" alone is too broad -- Gateway
# Diagnostics and other sections reuse the same class name (confirmed
# 2026-09-04, an unscoped query pulled in "MAC ID", "Charge Limit", etc.).
CARD = f"{GRID} .device-card"
CARD_TITLE = ".device-card-title"
CARD_STATUS_PILL = ".status-pill"
CARD_BODY = ".device-card-body"
CARD_BODY_INFO_LINE = ".device-card-body > span:not(.link-text)"
CARD_LINK = ".device-card-body .link-text"
