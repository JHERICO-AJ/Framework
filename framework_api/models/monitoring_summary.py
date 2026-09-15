"""Models for GET /api/monitoring/summary/{site_id} -- the Data & Monitoring
screen's backing endpoint. Separate from SiteSummary (which only extracts a
narrower dispatchDiagnostics.actualPcsPower for Fleet Overview's Power
cross-layer tests): this covers the sections in scope for Data & Monitoring
automation -- Device Status Panel (`statusPanel`), Gateway Diagnostics
(`gatewayDiagnostics`), and Dispatch Limits & Tracking
(`dispatchDiagnostics`, confirmed 2026-09-10 via a raw payload capture for
BOLIVIA -- this card DOES have a real, queryable API layer, unlike Battery
Diagnostics which only reads the in-memory cache with nothing exposed
here)."""
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


@dataclass(frozen=True)
class DispatchDiagnostics:
    """Dispatch Limits & Tracking's 6 blocks (docs/OF-145.txt), as the API
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


@dataclass(frozen=True)
class ThermalDiagnostics:
    """Thermal Diagnostics' 3 blocks (docs/OF-149.txt), as the API itself
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


@dataclass(frozen=True)
class SiteLoadContext:
    """Site Load & Backup Context's 3 blocks (docs/OF-152.txt), as the API
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


@dataclass(frozen=True)
class FaultLocalizationData:
    """Fault Localization's 8 rendered rows plus the 3 backend-only fields
    the HU says are computed but never shown on this panel (docs/OF-153.txt)
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


@dataclass(frozen=True)
class EnvironmentalMonitoringData:
    """Environmental Monitoring's 2 rendered metrics (docs/OF-151.txt): a
    site-level ambient temperature/humidity, each independently resolved
    with its own On-site (SYS sensor) vs API (Intake external weather
    fallback) source flag -- confirmed 2026-09-13 via a raw payload
    capture for BOLIVIA (ambientTemp=25/humidity=50, both source="API",
    matching the HU's documented Fractal gap "sin mapeo ambiental" -- no
    SYS on-site sensor mapped, so both fall back to
    docs/omniops_data_intake_BOLIVIA.xlsx's own configured
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


@dataclass(frozen=True)
class MonitoringSummary:
    status_panel: list[DeviceStatusCard]
    gateway_diagnostics: GatewayDiagnostics
    dispatch_diagnostics: DispatchDiagnostics
    thermal_diagnostics: ThermalDiagnostics
    site_load_context: SiteLoadContext
    fault_localization: FaultLocalizationData
    environmental_monitoring: EnvironmentalMonitoringData

    @classmethod
    def from_json(cls, payload: dict) -> "MonitoringSummary":
        payload = payload or {}
        return cls(
            status_panel=[DeviceStatusCard.from_json(c) for c in (payload.get("statusPanel") or [])],
            gateway_diagnostics=GatewayDiagnostics.from_json(payload.get("gatewayDiagnostics")),
            dispatch_diagnostics=DispatchDiagnostics.from_json(payload.get("dispatchDiagnostics")),
            thermal_diagnostics=ThermalDiagnostics.from_json(payload.get("thermalDiagnostics")),
            site_load_context=SiteLoadContext.from_json(payload.get("siteLoadContext")),
            fault_localization=FaultLocalizationData.from_json(payload.get("faultLocalization")),
            environmental_monitoring=EnvironmentalMonitoringData.from_json(payload.get("environmentalMonitoring")),
        )

    def card(self, title: str) -> DeviceStatusCard | None:
        return next((c for c in self.status_panel if c.title == title), None)
