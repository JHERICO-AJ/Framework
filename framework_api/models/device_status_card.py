"""DeviceStatusCard -- one block of the monitoring summary payload."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DeviceStatusCard:
    """One card in the Device Status Panel (Battery/BMS, PCS/Inverter,
    HVAC/Thermal, EMS IPC & Gateway, Meters/CT-PT, Network/Tunnel)."""
    title: str
    status: str  # "Warning" / "Fault" / "Online" -- UI pill shows it lowercase
    info: list[str]
    communication_warning_count: int
    first_communication_warning_description: str | None

    @classmethod
    def from_json(cls, payload_dict: dict) -> "DeviceStatusCard":
        return cls(
            title=payload_dict.get("title", ""),
            status=payload_dict.get("status", ""),
            info=payload_dict.get("info") or [],
            communication_warning_count=payload_dict.get("communicationWarningCount", 0),
            first_communication_warning_description=payload_dict.get("firstCommunicationWarningDescription"),
        )
