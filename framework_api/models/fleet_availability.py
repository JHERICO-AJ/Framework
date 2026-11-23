"""FleetAvailability -- the API model of the fleet availability distribution."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class FleetAvailability:
    normal_pct: float
    warning_pct: float
    critical_pct: float

    @classmethod
    def from_json(cls, payload: dict) -> "FleetAvailability":
        return cls(
            normal_pct=payload["normalPercentage"],
            warning_pct=payload["warningPercentage"],
            critical_pct=payload["criticalPercentage"],
        )
