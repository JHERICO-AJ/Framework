"""SiteImportExportPower -- reusable component: the Import/Export line
chart on Data & Monitoring (docs/OF-143.txt CA-22, docs/GraficasMonitoring.md).
No Trend Focus selector -- always plots Import (MW) + Export (MW), sharing
the same power-trend data as Site Power Telemetry's Meter / CT-PT focus."""
from __future__ import annotations

from framework_ui.base.base_component import BaseComponent
from framework_ui.pages.monitoring.components import site_import_export_power_locators as loc


class SiteImportExportPower(BaseComponent):
    def card(self):
        return self.page.locator(".card").filter(
            has=self.page.locator(loc.CARD_TITLE, has_text=loc.TITLE_TEXT))

    def time_range_badge(self):
        return self.card().locator(loc.TIME_RANGE_BADGE).inner_text().strip()

    def time_range_period(self):
        return self.card().locator(loc.TIME_RANGE_PERIOD).inner_text().strip()

    def legend_series(self):
        items = self.card().locator(loc.LEGEND_ITEM_TEXT)
        return [items.nth(i).inner_text().strip() for i in range(items.count())]

    def line_names(self):
        curves = self.card().locator(loc.LINE_CURVE)
        names = [curves.nth(i).get_attribute("name") for i in range(curves.count())]
        return [n for n in names if n]

    def _chart_svg(self):
        svg = self.card().locator(loc.CHART_SVG)
        svg.scroll_into_view_if_needed()
        return svg

    def _hover_tooltip_at(self, x, y):
        """Same nudge-retry pattern already confirmed for
        SitePowerTelemetry._hover_tooltip_at -- a tick's own x can land
        sub-pixel outside Recharts' interactive hit area."""
        svg = self._chart_svg()
        tooltip = self.card().locator(loc.TOOLTIP_WRAPPER).first
        for nudge in (0, 2, 4, 6, -2, -4):
            svg.hover(position={"x": x + nudge, "y": y})
            try:
                tooltip.wait_for(state="visible", timeout=1500)
                return tooltip.inner_text().strip()
            except Exception:
                continue
        tooltip.wait_for(state="visible", timeout=5000)
        return tooltip.inner_text().strip()

    def hover_latest_point_tooltip_text(self):
        """Hovers EXACTLY on the chart's most recent (rightmost) plotted
        point, using the x-axis's own last tick line position."""
        svg = self._chart_svg()
        svg_box = svg.bounding_box()
        tick = self.card().locator(loc.X_AXIS_TICK_LINE).last
        tick_box = tick.bounding_box()
        x = (tick_box["x"] + tick_box["width"] / 2) - svg_box["x"]
        return self._hover_tooltip_at(x, svg_box["height"] * 0.5)

    def hover_earliest_point_tooltip_text(self):
        """Same as hover_latest_point_tooltip_text but for the FIRST
        (oldest/leftmost) plotted point."""
        svg = self._chart_svg()
        svg_box = svg.bounding_box()
        tick = self.card().locator(loc.X_AXIS_TICK_LINE).first
        tick_box = tick.bounding_box()
        x = (tick_box["x"] + tick_box["width"] / 2) - svg_box["x"]
        return self._hover_tooltip_at(x, svg_box["height"] * 0.5)
