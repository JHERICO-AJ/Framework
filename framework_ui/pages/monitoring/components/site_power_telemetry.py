"""SitePowerTelemetry -- reusable component: the Trend Focus line chart on
Data & Monitoring (docs/OF-143.txt, docs/GraficasMonitoring.md)."""
from __future__ import annotations

import re

from framework_ui.base.base_component import BaseComponent
from framework_ui.pages.monitoring.components import site_power_telemetry_locators as loc


class SitePowerTelemetry(BaseComponent):
    def card(self):
        return self.page.locator(".card").filter(
            has=self.page.locator(loc.CARD_TITLE, has_text=loc.TITLE_TEXT))

    def time_range_badge(self):
        return self.card().locator(loc.TIME_RANGE_BADGE).inner_text().strip()

    def time_range_period(self):
        return self.card().locator(loc.TIME_RANGE_PERIOD).inner_text().strip()

    def trend_focus_select(self):
        return self.card().locator(loc.TREND_FOCUS_SELECT)

    def select_trend_focus(self, focus_label):
        """`focus_label` is the visible option text (e.g. "Battery / BMS"),
        not the underlying <option value=...>."""
        self.trend_focus_select().select_option(label=focus_label)
        return self

    def legend_series(self):
        """Every series with a legend entry, regardless of whether it
        actually has a plotted line -- see line_names() for that
        distinction (a Fractal gap can hide the line entirely while the
        legend entry stays, e.g. Container & Rack for BOLIVIA)."""
        items = self.card().locator(loc.LEGEND_ITEM_TEXT)
        return [items.nth(i).inner_text().strip() for i in range(items.count())]

    def line_names(self):
        """Series that actually rendered a plotted `<path>` -- Recharts
        only renders a Line's curve path when its dataset has at least one
        real value; an all-null series (e.g. HVAC on a site that never
        sends it) gets a legend entry but no path here."""
        curves = self.card().locator(loc.LINE_CURVE)
        names = [curves.nth(i).get_attribute("name") for i in range(curves.count())]
        return [n for n in names if n]

    def _legend_item(self, label):
        """Exact label match, not substring -- "Charge Power (MW)" must
        not also match "Discharge Power (MW)" (same collision class
        already confirmed for Raw Event Bit Viewer's evt1/pcsevt1)."""
        return self.card().locator(loc.LEGEND_ITEM).filter(
            has=self.page.locator(loc.LEGEND_ITEM_TEXT, has_text=re.compile(f"^{re.escape(label)}$")))

    def toggle_series(self, label):
        self._legend_item(label).click()
        return self

    def is_series_struck_through(self, label):
        style = self._legend_item(label).locator(loc.LEGEND_ITEM_INNER_SPAN).first.get_attribute("style") or ""
        return "line-through" in style

    def _chart_svg(self):
        svg = self.card().locator(loc.CHART_SVG)
        svg.scroll_into_view_if_needed()
        return svg

    def _hover_tooltip_at(self, x, y):
        """A tick's own x can land sub-pixel outside Recharts' interactive
        hit area (confirmed live: the exact leftmost tick's x sometimes
        needs a few extra pixels before a tooltip appears) -- nudges
        rightward in small steps rather than failing on the first miss."""
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

    def hover_tooltip_text(self):
        """Hovers near the middle of the plotted area and returns the raw
        tooltip text (first line = time/date label, following lines =
        "Series name: value")."""
        box = self._chart_svg().bounding_box()
        return self._hover_tooltip_at(box["width"] * 0.5, box["height"] * 0.5)

    def hover_latest_point_tooltip_text(self):
        """Hovers EXACTLY on the chart's most recent (rightmost) plotted
        point, using the x-axis's own last tick line position -- not an
        approximate fraction of the SVG width, which can land in the
        margin/label area or on the wrong point when the series has fewer
        points than the nominal 24/7/30 slots (a real, confirmed gap for
        BOLIVIA -- some hours have no MonitoringStat bucket at all)."""
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
