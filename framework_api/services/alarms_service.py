"""AlarmsService — the ALARMS domain of the API. Returns Alarm models, not dicts."""
from __future__ import annotations

from framework_api.services.base_service import ApiListResponse, BaseService
from framework_api.models.alarm import Alarm


class AlarmsService(BaseService):
    PATH = "/api/events/alarms/filtered"

    def get_alarms(self) -> list[Alarm]:
        payload = self.client.get(self.PATH)
        items = ApiListResponse(payload).items()
        return [Alarm.from_json(d) for d in items if isinstance(d, dict)]

    def get_open_alarms(self) -> list[Alarm]:
        return [a for a in self.get_alarms() if a.is_open]

    def open_rule_ids(self) -> set[int]:
        return {a.rule_id for a in self.get_open_alarms() if a.rule_id is not None}

    def by_rule_id(self, rule_id) -> list[Alarm]:
        return [a for a in self.get_alarms() if a.rule_id == rule_id]
