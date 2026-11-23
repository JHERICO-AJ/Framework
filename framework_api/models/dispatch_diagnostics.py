"""DispatchDiagnostics -- one block of the monitoring summary payload."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DispatchDiagnostics:
    """Dispatch Limits & Tracking's 6 blocks (Jira story OF-145), as the API
    itself computes them -- confirmed 2026-09-10 via a raw payload capture
    for BOLIVIA (dispatchDiagnostics.chargeLimitA=null, actualPcsPower=1.4,
    dcBusVoltage=1200, dcBusCurrent=1.2, ...). chargeLimitKw/dischargeLimitKw/
    conversionBasis/maxChargeLimit/maxDischargeLimit exist in the raw
    payload too but aren't shown on this card per OF-145.txt (internal-only
    kW derivation) -- not modeled here since nothing in this module reads
    them."""
    charge_limit_a: float | None
    discharge_limit_a: float | None
    pcs_setpoint: float | None
    actual_pcs_power: float | None
    dc_bus_voltage: float | None
    dc_bus_current: float | None
    timestamp: str | None

    @classmethod
    def from_json(cls, payload_dict: dict) -> "DispatchDiagnostics":
        payload_dict = payload_dict or {}
        return cls(
            charge_limit_a=payload_dict.get("chargeLimitA"),
            discharge_limit_a=payload_dict.get("dischargeLimitA"),
            pcs_setpoint=payload_dict.get("pcsSetpoint"),
            actual_pcs_power=payload_dict.get("actualPcsPower"),
            dc_bus_voltage=payload_dict.get("dcBusVoltage"),
            dc_bus_current=payload_dict.get("dcBusCurrent"),
            timestamp=payload_dict.get("timestamp"),
        )
