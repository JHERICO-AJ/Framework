"""FleetAvailability — reusable component: the fleet availability bar +
legend ("Normal X% · With alarms Y% · Critical offline Z%")."""
from __future__ import annotations

import re

from framework_ui.base.base_component import BaseComponent
from framework_ui.pages.fleet_overview.components import fleet_availability_locators as loc


class FleetAvailability(BaseComponent):
    def wait_past_mount_animation(self, buffer_ms=500):
        """Confirmed via docs/fleet-availability.md §4.2: on first mount
        (isInitialLoad) the widget interpolates its displayed percentages
        over an 800ms animation using intermediate Math.round() values that
        do NOT sum to 100 mid-animation -- reading percentages() before
        this settles catches a transient, not the real reconciled value."""
        self.page.wait_for_timeout(800 + buffer_ms)

    def meta_text(self):
        return self.page.locator(loc.META).inner_text().strip()

    def percentages(self):
        """{'normal': float, 'with_alarms': float, 'critical_offline': float},
        parsed from the legend text. None for any figure not found."""
        text = self.meta_text()

        def _pct(label):
            match = re.search(re.escape(label) + r"\s*([\d.]+)%", text, re.IGNORECASE)
            return float(match.group(1)) if match else None

        return {
            "normal": _pct("Normal"),
            "with_alarms": _pct("With alarms"),
            "critical_offline": _pct("Critical offline"),
        }
