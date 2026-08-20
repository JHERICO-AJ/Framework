"""Model Alarm — el JSON de la API se parsea UNA vez acá (DTO).

Es el ÚNICO lugar que conoce los nombres de campo del backend. Si el backend
renombra 'alarmRuleId', se toca una línea. Las fechas vienen en UTC.
"""
from __future__ import annotations

import datetime
from dataclasses import dataclass


def _parse_dt(texto):
    """'2026-08-18 13:29:15' (UTC) -> datetime aware en UTC (o None)."""
    if not texto:
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S.%f"):
        try:
            return datetime.datetime.strptime(texto, fmt).replace(
                tzinfo=datetime.timezone.utc)
        except ValueError:
            continue
    return None


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
    def from_json(cls, d: dict) -> "Alarm":
        return cls(
            rule_id=d["alarmRuleId"],
            name=d.get("alarm", ""),
            severity=d.get("severity", ""),
            status=d.get("status", ""),
            subsystem=d.get("subsystem", ""),
            signal=d.get("signal", ""),
            device_name=d.get("deviceName", ""),
            site_id=d.get("siteId", ""),
            first_occurred=_parse_dt(d.get("firstOccurred")),
            last_occurred=_parse_dt(d.get("lastOccurred")),
        )
