"""Model for GET /api/monitoring/power-trend/{siteId} -- Site Power
Telemetry/Import-Export Power's shared backing endpoint (docs/OF-143.txt,
docs/GraficasMonitoring.md). Both charts read this same series; nothing
here is specific to one Trend Focus -- the frontend just picks which
fields to plot.

Values here are in kW (the API's own unit) -- the frontend divides by
1000 to render MW (see shared.utils.parsing helpers used by tests for the
matching kW-vs-MW comparisons)."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PowerTrendPoint:
    timestamp: str
    site_soc: float | None
    charge_power_kw: float | None
    discharge_power_kw: float | None
    cell_voltage_delta_mv: float | None
    import_power_kw: float | None
    export_power_kw: float | None
    pcs_total_power_kw: float | None
    container_avg_temp_c: float | None
    max_rack_temp_c: float | None
    data_freshness_seconds: float | None
    sample_gap_count: int | None
    comms_latency_ms: float | None
    data_delay_seconds: float | None
    hvac_power_kw: float | None

    @classmethod
    def from_json(cls, point_dict: dict) -> "PowerTrendPoint":
        return cls(
            timestamp=point_dict.get("timestamp"),
            site_soc=point_dict.get("siteSoc"),
            charge_power_kw=point_dict.get("chargePower"),
            discharge_power_kw=point_dict.get("dischargePower"),
            cell_voltage_delta_mv=point_dict.get("cellVoltageDelta"),
            import_power_kw=point_dict.get("importPower"),
            export_power_kw=point_dict.get("exportPower"),
            pcs_total_power_kw=point_dict.get("pcsTotalPower"),
            container_avg_temp_c=point_dict.get("containerAvgTemp"),
            max_rack_temp_c=point_dict.get("maxRackTemp"),
            data_freshness_seconds=point_dict.get("dataFreshnessSeconds"),
            sample_gap_count=point_dict.get("sampleGapCount"),
            comms_latency_ms=point_dict.get("commsLatencyMs"),
            data_delay_seconds=point_dict.get("dataDelaySeconds"),
            hvac_power_kw=point_dict.get("hvacPower"),
        )

    @staticmethod
    def list_from_json(payload_list: list[dict]) -> list["PowerTrendPoint"]:
        return [PowerTrendPoint.from_json(point_dict) for point_dict in (payload_list or [])]
