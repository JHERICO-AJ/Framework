"""Selectors for the Fleet Alarms Analytics section. Confirmed against the
real deployed app (2026-08-28): 4 ".card" siblings inside ".analytics-grid"
-- 2 ECharts canvases (time series, distribution pie -- not scraped, no
reliable DOM data to assert against) and 2 real HTML tables
(".small-table"), each identified by its ".mini-chart-title" heading text:
  "Top sites by alarms — last 24h"    -> <th>Site, Total Alarms, Critical</th>
  "Top 5 critical causes — last 24h"  -> <th>Cause, Count, Sites</th>
"""
MINI_CHART = ".mini-chart"
MINI_CHART_TITLE = ".mini-chart-title"
SMALL_TABLE = "table.small-table"
TABLE_ROW = "tbody tr"
TABLE_CELL = "td"

# The 2 ECharts CANVAS charts (hourly bars, subsystem pie) -- no readable
# DOM for the drawing itself, but hovering a data point opens ECharts'
# tooltip, which IS plain HTML with real text (confirmed 2026-09-01 by
# inspecting the live page). The tooltip has no distinct CSS class of its
# own (ECharts renders it as a bare styled <div>), but its z-index is
# consistent every time we've seen it -- used as the selector instead.
CHART_CANVAS = "canvas"
ECHARTS_TOOLTIP = 'div[style*="z-index: 9999999"]'
