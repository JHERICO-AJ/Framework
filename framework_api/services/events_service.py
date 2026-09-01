"""EventsService — the EVENTS analytics domain (Fleet Alarms Analytics'
2 charts' underlying data -- the charts themselves render on an HTML5
<canvas> via ECharts, which has no readable DOM/text content, so the
drawing itself can't be scraped. This is the next best thing: verify the
DATA that feeds the drawing is correct, even though the pixels can't be
directly asserted on. Confirmed via network capture 2026-08-31."""
from __future__ import annotations

from framework_api.services.base_service import BaseService


class EventsService(BaseService):
    def get_hourly_distribution(self, hours=24) -> list[dict]:
        """[{'hour': '14 h', 'timestamp': '...', 'critical': N, 'major': N,
        'minor': N}, ...] -- one entry per hour bucket."""
        return self.client.get("/api/events/analytics/hourly-distribution", hours=hours)

    def get_subsystem_distribution(self, hours=24) -> list[dict]:
        """[{'name': 'TRANSFORMER_PCS', 'value': N}, ...] -- one entry per
        subsystem, ALL severities."""
        return self.client.get("/api/events/analytics/subsystem-distribution", hours=hours)
