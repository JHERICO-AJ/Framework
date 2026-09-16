"""Selectors for the Site Power Telemetry chart (Data & Monitoring --
docs/OF-143.txt, docs/GraficasMonitoring.md): a Recharts line chart with a
Trend Focus selector (Battery/BMS, PCS Power, Container & Rack, HVAC &
Aux, EMS & Network, Meter/CT-PT), Site SOC always on the left axis, and a
right axis that changes series depending on the selected focus.

Confirmed against the real deployed app (2026-09-10/2026-09-13, BOLIVIA).
"""
TITLE_TEXT = "Site Power Telemetry"
CARD_TITLE = ".card-title"
SUBTITLE = ".card-subtitle"
TIME_RANGE_BADGE = ".monitoring-time-range-badge"
TIME_RANGE_PERIOD = ".monitoring-time-range-period"

TREND_FOCUS_SELECT = ".filters-bar select.select"

CHART_SVG = 'svg[role="application"]'
X_AXIS_TICK_LINE = ".recharts-xAxis .recharts-cartesian-axis-tick-line"
LEGEND_ITEM = ".recharts-legend-item"
LEGEND_ITEM_TEXT = ".recharts-legend-item-text"
LEGEND_ITEM_INNER_SPAN = f"{LEGEND_ITEM_TEXT} span"
LINE_CURVE = "path.recharts-curve.recharts-line-curve"
TOOLTIP_WRAPPER = ".recharts-tooltip-wrapper"
