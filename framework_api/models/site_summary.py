"""Model SiteSummary — resumen de monitoreo (potencia PCS calculada por OmniOps)."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SiteSummary:
    actual_pcs_power_kw: float | None
    timestamp: str | None

    @classmethod
    def from_json(cls, d: dict) -> "SiteSummary":
        dd = (d or {}).get("dispatchDiagnostics") or {}
        return cls(
            actual_pcs_power_kw=dd.get("actualPcsPower"),
            timestamp=dd.get("timestamp"),
        )
