"""SitesList — reusable component: the fleet sites table."""
from __future__ import annotations

import re

from framework_ui.base.base_component import BaseComponent
from framework_ui.pages.fleet_overview.components import sites_list_locators as loc


class SitesList(BaseComponent):
    def header_labels(self):
        headers = self.page.locator(loc.HEADER_CELL)
        return [headers.nth(i).inner_text().strip() for i in range(headers.count())]

    def row_count(self):
        return self.page.locator(loc.ROW).count()

    def cell_text(self, row_index, col_index):
        row = self.page.locator(loc.ROW).nth(row_index)
        return row.locator(loc.CELL).nth(col_index).inner_text().strip()

    def row_index_by_site_name(self, name):
        """Exact match on the Site column only -- a substring check against
        the whole row's text (the previous approach) wrongly matches
        "BOLIVIA 3"/"BOLIVIA 4"/etc. when looking up "BOLIVIA", since
        "BOLIVIA" is a substring of those other site names too."""
        rows = self.page.locator(loc.ROW)
        col = self._col_index("SITE")
        for i in range(rows.count()):
            if rows.nth(i).locator(loc.CELL).nth(col).inner_text().strip() == name:
                return i
        return None

    def status_text(self, row_index):
        row = self.page.locator(loc.ROW).nth(row_index)
        return row.locator(loc.STATUS_PILL).inner_text().strip()

    def soc_percent(self, row_index):
        """SoC is a visual bar (width:N%), not text. Returns the width as a
        float (0-100), or None if the bar isn't present."""
        row = self.page.locator(loc.ROW).nth(row_index)
        fill = row.locator(loc.SOC_FILL)
        if fill.count() == 0:
            return None
        style = fill.get_attribute("style") or ""
        match = re.search(r"width:\s*([\d.]+)%", style)
        return float(match.group(1)) if match else None

    def _col_index(self, header_name):
        return self.header_labels().index(header_name)

    def power_kw(self, row_index):
        """"Power (kW)" column -- parses the number out regardless of exact
        formatting (comma thousands separator, unit suffix, etc). None for
        the empty-cell placeholder ("-"/"—")."""
        text = self.cell_text(row_index, self._col_index("POWER (KW)"))
        match = re.search(r"-?[\d,]+\.?\d*", text)
        return float(match.group(0).replace(",", "")) if match else None

    def critical_count(self, row_index):
        """"Critical" column -- plain integer count."""
        return int(self.cell_text(row_index, self._col_index("CRITICAL")))

    def last_seen_text(self, row_index):
        return self.cell_text(row_index, self._col_index("LAST SEEN"))

    def header_is_clipped(self, header_name):
        """True if this column header's text overflows its own cell width
        (scrollWidth > clientWidth) -- the header uses white-space: nowrap
        + text-overflow: clip (not ellipsis, no wrap), so an overflow here
        means part of the label is genuinely invisible, not just visually
        tight. Confirmed 2026-09-16: "POWER (KW)" fits at the 1920x1080
        automation-default viewport but clips (loses the "(KW)" suffix)
        at common laptop resolutions (1366x768, 1536x864, 1280x800)."""
        headers = self.page.locator(loc.HEADER_CELL)
        idx = self._col_index(header_name)
        return headers.nth(idx).evaluate("el => el.scrollWidth > el.clientWidth")
