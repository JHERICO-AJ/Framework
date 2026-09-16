"""SiteLoadBackupContext -- reusable component: Real Load / Estimated
Backup / ATS-Net power-Context on Data & Monitoring (docs/OF-152.txt)."""
from __future__ import annotations

from framework_ui.base.base_component import BaseComponent
from framework_ui.pages.monitoring.components import site_load_backup_context_locators as loc


class SiteLoadBackupContext(BaseComponent):
    def card(self):
        return self.page.locator(".card").filter(
            has=self.page.locator(loc.CARD_TITLE, has_text=loc.TITLE_TEXT))

    def subtitle(self):
        return self.card().locator(loc.SUBTITLE).inner_text().strip()

    def _named_block(self, title):
        return self.card().locator(loc.BLOCK).filter(
            has=self.page.locator(loc.BLOCK_TITLE, has_text=title))

    def value_text(self, title):
        """Raw value text for the "Real Load" or "Estimated Backup" block."""
        return self._named_block(title).locator(loc.BLOCK_VALUE).inner_text().strip()

    def help_text(self, title):
        return self._named_block(title).locator(loc.BLOCK_HELP_TEXT).inner_text().strip()

    def lateral_values(self):
        """{label: value} for the 3 lateral rows (ATS / grid transfer, Net
        power, Context), keyed by their own label text."""
        lateral = self.card().locator(loc.LATERAL_BLOCK)
        rows = lateral.locator(loc.BIT_ROW)
        values = {}
        for i in range(rows.count()):
            row = rows.nth(i)
            label = row.locator(loc.BIT_LABEL).inner_text().strip()
            value = row.locator(loc.BIT_VALUE).inner_text().strip()
            values[label] = value
        return values

    def ats_value(self):
        return self.lateral_values().get("ATS / grid transfer")

    def net_power_value(self):
        return self.lateral_values().get("Net power")

    def context_value(self):
        return self.lateral_values().get("Context")

    def real_load_kw(self):
        """Parses "1610 kW" -> 1610, or None if the value is "—"."""
        return self._parse_kw(self.value_text("Real Load"))

    def estimated_backup_min(self):
        text = self.value_text("Estimated Backup")
        if text.strip() == "—":
            return None
        return int(text.replace("min", "").strip())

    def net_power_kw(self):
        return self._parse_kw(self.net_power_value())

    @staticmethod
    def _parse_kw(text):
        if text is None or text.strip() == "—":
            return None
        return int(text.replace("kW", "").strip())
