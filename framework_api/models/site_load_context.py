"""SiteLoadContext -- one block of the monitoring summary payload."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SiteLoadContext:
    """Site Load & Backup Context's 3 blocks (Jira story OF-152), as the API
    itself computes them -- confirmed 2026-09-13 via a raw payload capture
    for BOLIVIA (atsStatus null, matching the documented Fractal gap "Sin
    RealLoad ni AtsSt mapeados" -- realLoad/netPower use the MeterDemand +
    ΣPCS fallback instead)."""
    real_load: float | None
    net_power: float | None
    ats_status: int | None
    estimated_backup_minutes: float | None
    context: str | None

    @classmethod
    def from_json(cls, payload_dict: dict) -> "SiteLoadContext":
        payload_dict = payload_dict or {}
        return cls(
            real_load=payload_dict.get("realLoad"),
            net_power=payload_dict.get("netPower"),
            ats_status=payload_dict.get("atsStatus"),
            estimated_backup_minutes=payload_dict.get("estimatedBackupMinutes"),
            context=payload_dict.get("context"),
        )
