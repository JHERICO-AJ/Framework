"""EventsService — the EVENTS analytics domain (Fleet Alarms Analytics'
2 charts' underlying data -- the charts themselves render on an HTML5
<canvas> via ECharts, which has no readable DOM/text content, so the
drawing itself can't be scraped. This is the next best thing: verify the
DATA that feeds the drawing is correct, even though the pixels can't be
directly asserted on. Confirmed via network capture 2026-08-31."""
from __future__ import annotations

from framework_api.services.base_service import BaseService
from shared.config.settings import CLIENT_TIMEZONE


class EventsService(BaseService):
    def get_hourly_distribution(self, hours=24, client_timezone=CLIENT_TIMEZONE) -> list[dict]:
        """[{'hour': '14 h', 'timestamp': '...', 'critical': N, 'major': N,
        'minor': N}, ...] -- one entry per hour bucket.

        `client_timezone` DEFAULTS to CLIENT_TIMEZONE (settings.py):
        confirmed via network capture 2026-09-16 that the REAL frontend
        ALWAYS sends this as a 'ClientTimeZone' query param -- per the
        developer, the BACKEND (not the frontend) does the UTC -> local
        conversion using this value, shifting bucket boundaries to LOCAL
        midnight and building correctly-localized labels. This method used
        to omit it unconditionally, which is a genuinely different request
        than what the real UI ever sends -- confirmed this produced a
        FALSE POSITIVE "day label is UTC" defect (retracted, see Qase):
        the bucket timestamps themselves shift (e.g. '00:00:00Z' -> the
        equivalent 'T+4h:00:00Z' boundary) once this param is included, and
        the label is then already correct. Pass client_timezone=None
        explicitly only if a test genuinely needs the old, timezone-blind
        request."""
        params = {"hours": hours}
        if client_timezone:
            params["ClientTimeZone"] = client_timezone
        return self.client.get("/api/events/analytics/hourly-distribution", **params)

    def get_subsystem_distribution(self, hours=24) -> list[dict]:
        """[{'name': 'TRANSFORMER_PCS', 'value': N}, ...] -- one entry per
        subsystem, ALL severities."""
        return self.client.get("/api/events/analytics/subsystem-distribution", hours=hours)
