"""EnvironmentalMonitoringData -- one block of the monitoring summary payload."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class EnvironmentalMonitoringData:
    """Environmental Monitoring's 2 rendered metrics (Jira story OF-151): a
    site-level ambient temperature/humidity, each independently resolved
    with its own On-site (SYS sensor) vs API (Intake external weather
    fallback) source flag -- confirmed 2026-09-13 via a raw payload
    capture for BOLIVIA (ambientTemp=25/humidity=50, both source="API",
    matching the HU's documented Fractal gap "sin mapeo ambiental" -- no
    SYS on-site sensor mapped, so both fall back to
    the internal QA note 'omniops_data_intake_BOLIVIA''s own configured
    ambient_temperature=25/relative_humidity=50). Fields present in the
    DTO but never rendered on THIS panel (containerTemp, cellHighTemp,
    cellLowTemp, cellTempDelta, rackHighTemperature, hvacStatus) are kept
    here too since the API genuinely exposes them -- same rationale as
    ThermalDiagnostics/FaultLocalizationData."""
    ambient_temp: float | None
    humidity: float | None
    ambient_temp_source: str | None  # "On-site" / "API" / None (no value at all)
    humidity_source: str | None
    container_temp: float | None
    cell_high_temp: float | None
    cell_low_temp: float | None
    cell_temp_delta: float | None
    rack_high_temperature: str | None
    hvac_status: str | None

    @classmethod
    def from_json(cls, payload_dict: dict) -> "EnvironmentalMonitoringData":
        payload_dict = payload_dict or {}
        return cls(
            ambient_temp=payload_dict.get("ambientTemp"),
            humidity=payload_dict.get("humidity"),
            ambient_temp_source=payload_dict.get("ambientTempSource"),
            humidity_source=payload_dict.get("humiditySource"),
            container_temp=payload_dict.get("containerTemp"),
            cell_high_temp=payload_dict.get("cellHighTemp"),
            cell_low_temp=payload_dict.get("cellLowTemp"),
            cell_temp_delta=payload_dict.get("cellTempDelta"),
            rack_high_temperature=payload_dict.get("rackHighTemperature"),
            hvac_status=payload_dict.get("hvacStatus"),
        )
