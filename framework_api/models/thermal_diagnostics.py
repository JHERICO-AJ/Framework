"""ThermalDiagnostics -- one block of the monitoring summary payload."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ThermalDiagnostics:
    """Thermal Diagnostics' 3 blocks (Jira story OF-149), as the API itself
    computes them -- confirmed 2026-09-11 via a raw payload capture for
    BOLIVIA (all 4 fields null, matching the UI's "—" for a Fractal
    site with no strings mapped). Kept as a real, queryable API layer
    (unlike the HU's own claim that this panel is RAM-only/non-persisted --
    it IS exposed here) so that once a site with real string/BMS
    temperature data exists, this same model plugs straight into a genuine
    UI-vs-API-vs-simulator cross-layer test without needing a rewrite."""
    temp_delta: float | None
    highest_temp: float | None
    lowest_temp: float | None
    average_temp: float | None

    @classmethod
    def from_json(cls, payload_dict: dict) -> "ThermalDiagnostics":
        payload_dict = payload_dict or {}
        return cls(
            temp_delta=payload_dict.get("tempDelta"),
            highest_temp=payload_dict.get("highestTemp"),
            lowest_temp=payload_dict.get("lowestTemp"),
            average_temp=payload_dict.get("averageTemp"),
        )
