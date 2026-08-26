"""MonitoringService — the MONITORING domain (summary/power). Returns SiteSummary."""
from __future__ import annotations

from framework_api.services.base_service import BaseService
from framework_api.models.site_summary import SiteSummary
from shared.config.settings import SITE_ID


class MonitoringService(BaseService):
    PATH = "/api/monitoring/summary/{site_id}"

    def get_summary(self, site_id=SITE_ID) -> SiteSummary:
        payload = self.client.get(self.PATH.format(site_id=site_id))
        return SiteSummary.from_json(payload)
