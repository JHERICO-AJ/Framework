"""Selectors for the Site Import / Export Power card (Data & Monitoring --
docs/OF-143.txt CA-22, docs/GraficasMonitoring.md): a Recharts line chart
with NO Trend Focus selector -- always just Import (MW) + Export (MW),
domain clamped to [0, auto] on the client. Shares the same power-trend data
as Site Power Telemetry's Meter / CT-PT focus (confirmed live 2026-09-14).

Confirmed against the real deployed app (2026-09-14, BOLIVIA).
"""
TITLE_TEXT = "Site Import / Export Power"
CARD_TITLE = ".card-title"
SUBTITLE = ".card-subtitle"
TIME_RANGE_BADGE = ".monitoring-time-range-badge"
TIME_RANGE_PERIOD = ".monitoring-time-range-period"

CHART_SVG = 'svg[role="application"]'
X_AXIS_TICK_LINE = ".recharts-xAxis .recharts-cartesian-axis-tick-line"
LEGEND_ITEM_TEXT = ".recharts-legend-item-text"
LINE_CURVE = "path.recharts-curve.recharts-line-curve"
TOOLTIP_WRAPPER = ".recharts-tooltip-wrapper"
