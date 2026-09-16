"""FleetAlarmsAnalytics — reusable component: the "Top sites by alarms" and
"Top 5 critical causes" tables, plus the section's 2 ECharts canvases
(hourly bar, subsystem pie). The canvases themselves have no readable DOM,
but hovering a data point opens ECharts' own tooltip, which IS plain HTML
-- confirmed 2026-09-01 by inspecting the live page. `scan_hourly_chart()`/
`scan_subsystem_pie()` sweep points across each chart's area and parse
whatever tooltip text appears, for cross-layer verification of the
RENDERED chart content (not just its underlying API data, already covered
by test_fleet_overview_charts_data.py)."""
from __future__ import annotations

import re

from framework_ui.base.base_component import BaseComponent
from framework_ui.pages.fleet_overview.components import fleet_alarms_analytics_locators as loc


class FleetAlarmsAnalytics(BaseComponent):
    def wait_loaded(self, timeout=20000):
        """The section shows "Loading analytics..." as its subtitle until
        the data arrives (confirmed 2026-08-31: reading the tables before
        this resolves returns an empty/incomplete result, not an error --
        same "looks fine, quietly wrong" trap as MTTR/Fleet Availability's
        own loading placeholders). ".section-subtitle" isn't unique to this
        section (Sites List, Fleet Availability use it too) -- scope to the
        row whose title is "Fleet Alarms Analytics" specifically."""
        self.page.wait_for_function(
            """() => {
                const rows = document.querySelectorAll('.section-title-row');
                for (const row of rows) {
                    const title = row.querySelector('.section-title')?.textContent || '';
                    if (title.includes('Fleet Alarms Analytics')) {
                        const sub = row.querySelector('.section-subtitle')?.textContent || '';
                        return !sub.includes('Loading analytics');
                    }
                }
                return false;
            }""",
            timeout=timeout,
        )

    def _table_by_title(self, title_substring):
        card = self.page.locator(loc.MINI_CHART).filter(
            has=self.page.locator(loc.MINI_CHART_TITLE, has_text=title_substring)
        )
        return card.locator(loc.SMALL_TABLE)

    def panel_title_text(self, title_substring):
        """Full text of a panel's own title element (e.g. 'Top sites by
        alarms · Last 7 days') -- for verifying the window-label suffix
        the title is expected to append per the currently selected time
        range (Qase case #281: 'Analytics titles update with the window
        label'), not just the panel's data."""
        self.wait_loaded()
        return self.page.locator(loc.MINI_CHART_TITLE, has_text=title_substring).first.inner_text().strip()

    def _table_rows(self, table):
        rows = table.locator(loc.TABLE_ROW)
        result = []
        for i in range(rows.count()):
            cells = rows.nth(i).locator(loc.TABLE_CELL)
            result.append(tuple(cells.nth(c).inner_text().strip() for c in range(cells.count())))
        return result

    def top_sites_by_alarms(self):
        """{site_name: (total_alarms, critical)} -- as a dict, not a list,
        since row ORDER isn't something we assert against (only the values
        per site)."""
        self.wait_loaded()
        table = self._table_by_title("Top sites by alarms")
        return {
            site: (int(total), int(critical))
            for site, total, critical in self._table_rows(table)
        }

    def top_critical_causes(self):
        """{cause: (count, distinct_sites)}."""
        self.wait_loaded()
        table = self._table_by_title("Top 5 critical causes")
        return {
            cause: (int(count), int(sites))
            for cause, count, sites in self._table_rows(table)
        }

    # ---- ECharts canvas tooltips (rendered-content verification) ----

    def _chart_canvas_by_title(self, title_substring):
        self.wait_loaded()
        card = self.page.locator(loc.MINI_CHART).filter(
            has=self.page.locator(loc.MINI_CHART_TITLE, has_text=title_substring)
        )
        return card.locator(loc.CHART_CANVAS)

    def _read_tooltip_at(self, x, y, settle_ms=100):
        """Moves the mouse to (x, y) and returns the ECharts tooltip's text
        if one is visible right after, else None (most swept points land
        between data points/slices and show nothing -- not an error)."""
        self.page.mouse.move(x, y)
        self.page.wait_for_timeout(settle_ms)
        tooltip = self.page.locator(loc.ECHARTS_TOOLTIP).last
        if tooltip.count() == 0 or not tooltip.is_visible():
            return None
        text = tooltip.inner_text().strip()
        return text or None

    @staticmethod
    def _parse_bar_tooltip(text):
        """"21 h\nCritical 26\nMajor 0\nMinor 12" (exact whitespace varies
        by render) -> ("21 h", {"critical": 26, "major": 0, "minor": 12}).
        None if the text doesn't look like this chart's tooltip at all."""
        hour_match = re.search(r"(\d{1,2}\s*h)\b", text)
        if not hour_match:
            return None
        values = {}
        for label in ("Critical", "Major", "Minor"):
            match = re.search(rf"{label}\D*(\d+)", text)
            if match:
                values[label.lower()] = int(match.group(1))
        if not values:
            return None
        return re.sub(r"\s+", " ", hour_match.group(1)), values

    @staticmethod
    def _parse_pie_tooltip(text):
        """"PCS / Inverter: 39 alarms (76.47%)" ->
        ("PCS / Inverter", 39, 76.47). None if unparseable."""
        match = re.match(r"(.+?):\s*(\d+)\s*alarms\s*\(([\d.]+)%\)", text)
        if not match:
            return None
        name, count, pct = match.groups()
        return name.strip(), int(count), float(pct)

    def scan_hourly_chart(self, steps=48):
        """Sweeps evenly-spaced x positions across the hourly bar chart,
        reading whatever tooltip appears at each. Returns
        {hour_label: {"critical": N, "major": N, "minor": N}} -- only for
        hours where a bar was actually under the cursor; gaps are skipped,
        not an error (a 24-bar chart doesn't fill its whole width)."""
        canvas = self._chart_canvas_by_title("by hour")
        box = canvas.bounding_box()
        results = {}
        for i in range(steps):
            x = box["x"] + box["width"] * (i + 0.5) / steps
            y = box["y"] + box["height"] * 0.6
            text = self._read_tooltip_at(x, y)
            if not text:
                continue
            parsed = self._parse_bar_tooltip(text)
            if parsed:
                hour_label, values = parsed
                results[hour_label] = values
        return results

    def scan_subsystem_pie(self, step_px=18):
        """Grid-sweeps the whole canvas area (NOT just points computed
        around an assumed ring center/radius -- confirmed 2026-09-01 via a
        screenshot that the donut is NOT centered in its own canvas: a
        legend occupies the right portion of the box, and there's padding
        elsewhere, so an angle/radius-based sweep around the box's own
        center missed the smaller slice entirely). A plain grid over the
        full box finds every slice regardless of where ECharts actually
        drew the ring. Returns {display_name: (count, pct)}."""
        canvas = self._chart_canvas_by_title("by system")
        box = canvas.bounding_box()
        results = {}
        y = box["y"] + step_px / 2
        while y < box["y"] + box["height"]:
            x = box["x"] + step_px / 2
            while x < box["x"] + box["width"]:
                text = self._read_tooltip_at(x, y, settle_ms=60)
                if text:
                    parsed = self._parse_pie_tooltip(text)
                    if parsed:
                        name, count, pct = parsed
                        results[name] = (count, pct)
                x += step_px
            y += step_px
        return results
