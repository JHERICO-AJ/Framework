"""Model Alarm — the API's JSON is parsed ONCE, here (DTO).

This is the ONLY place that knows the backend's field names. If the backend
renames 'alarmRuleId', only one line needs to change. Dates come in UTC.
"""
from __future__ import annotations

import datetime
from dataclasses import dataclass

from shared.utils.parsing import parse_api_datetime


@dataclass(frozen=True)
class Alarm:
    rule_id: int
    name: str
    severity: str
    status: str
    subsystem: str
    signal: str
    device_name: str
    site_id: str
    first_occurred: datetime.datetime | None
    last_occurred: datetime.datetime | None

    @property
    def is_open(self) -> bool:
        return (self.status or "").strip().lower() == "open"

    @classmethod
    def from_json(cls, alarm_dict: dict) -> "Alarm":
        return cls(
            rule_id=alarm_dict["alarmRuleId"],
            name=alarm_dict.get("alarm", ""),
            severity=alarm_dict.get("severity", ""),
            status=alarm_dict.get("status", ""),
            subsystem=alarm_dict.get("subsystem", ""),
            signal=alarm_dict.get("signal", ""),
            device_name=alarm_dict.get("deviceName", ""),
            site_id=alarm_dict.get("siteId", ""),
            first_occurred=parse_api_datetime(alarm_dict.get("firstOccurred")),
            last_occurred=parse_api_datetime(alarm_dict.get("lastOccurred")),
        )
