"""Model SiteSummary — monitoring summary (PCS power calculated by OmniOps)."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SiteSummary:
    actual_pcs_power_kw: float | None
    timestamp: str | None

    @classmethod
    def from_json(cls, payload_dict: dict) -> "SiteSummary":
        dispatch_diagnostics = (payload_dict or {}).get("dispatchDiagnostics") or {}
        return cls(
            actual_pcs_power_kw=dispatch_diagnostics.get("actualPcsPower"),
            timestamp=dispatch_diagnostics.get("timestamp"),
        )
