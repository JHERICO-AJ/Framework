"""GatewayDiagnostics -- one block of the monitoring summary payload."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class GatewayDiagnostics:
    """The Gateway Diagnostics card row (Communication Status / Gateway ID /
    MAC ID / Data Freshness)."""
    heartbeat_status: str  # "Connected" / "Watch" / "Disconnected"
    gateway_id: str | None
    mac_id: str | None
    system_id: str | None
    last_comms: str | None
    sampling_interval: float | None
    aggregation_window: float | None
    latency: float | None
    data_freshness: str  # "Fresh" / "Watch" / "Stale"
    freshness_seconds: float | None

    @classmethod
    def from_json(cls, payload_dict: dict) -> "GatewayDiagnostics":
        payload_dict = payload_dict or {}
        return cls(
            heartbeat_status=payload_dict.get("heartBeatStatus", ""),
            gateway_id=payload_dict.get("gatewayId"),
            mac_id=payload_dict.get("macId"),
            system_id=payload_dict.get("systemId"),
            last_comms=payload_dict.get("lastComms"),
            sampling_interval=payload_dict.get("samplingInterval"),
            aggregation_window=payload_dict.get("aggregationWindow"),
            latency=payload_dict.get("latency"),
            data_freshness=payload_dict.get("dataFreshness", ""),
            freshness_seconds=payload_dict.get("freshnessSeconds"),
        )
