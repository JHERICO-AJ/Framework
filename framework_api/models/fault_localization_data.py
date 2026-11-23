"""FaultLocalizationData -- one block of the monitoring summary payload."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class FaultLocalizationData:
    """Fault Localization's 8 rendered rows plus the 3 backend-only fields
    the HU says are computed but never shown on this panel (Jira story OF-153)
    -- confirmed 2026-09-13 via a raw payload capture for BOLIVIA (all 8
    location fields null, matching the documented Fractal gap "sin strings
    BMS mapeados"; faultDeviceId/faultType/faultLocation ARE populated from
    the most recent open alarm, exactly as the HU describes for the
    not-rendered fields)."""
    highest_rack: str | None
    highest_pack: str | None
    highest_cell: str | None
    lowest_rack: str | None
    lowest_pack: str | None
    lowest_cell: str | None
    highest_temp_rack: str | None
    highest_temp_pack: str | None
    highest_temp_cell: str | None
    lowest_temp_rack: str | None
    lowest_temp_pack: str | None
    lowest_temp_cell: str | None
    fault_device_id: str | None
    fault_type: str | None
    fault_location: str | None

    @classmethod
    def from_json(cls, payload_dict: dict) -> "FaultLocalizationData":
        payload_dict = payload_dict or {}
        return cls(
            highest_rack=payload_dict.get("highestRack"),
            highest_pack=payload_dict.get("highestPack"),
            highest_cell=payload_dict.get("highestCell"),
            lowest_rack=payload_dict.get("lowestRack"),
            lowest_pack=payload_dict.get("lowestPack"),
            lowest_cell=payload_dict.get("lowestCell"),
            highest_temp_rack=payload_dict.get("highestTempRack"),
            highest_temp_pack=payload_dict.get("highestTempPack"),
            highest_temp_cell=payload_dict.get("highestTempCell"),
            lowest_temp_rack=payload_dict.get("lowestTempRack"),
            lowest_temp_pack=payload_dict.get("lowestTempPack"),
            lowest_temp_cell=payload_dict.get("lowestTempCell"),
            fault_device_id=payload_dict.get("faultDeviceId"),
            fault_type=payload_dict.get("faultType"),
            fault_location=payload_dict.get("faultLocation"),
        )
