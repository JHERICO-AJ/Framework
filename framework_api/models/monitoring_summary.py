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

from framework_api.models.device_status_card import DeviceStatusCard
from framework_api.models.gateway_diagnostics import GatewayDiagnostics
from framework_api.models.dispatch_diagnostics import DispatchDiagnostics
from framework_api.models.thermal_diagnostics import ThermalDiagnostics
from framework_api.models.site_load_context import SiteLoadContext
from framework_api.models.fault_localization_data import FaultLocalizationData
from framework_api.models.environmental_monitoring_data import EnvironmentalMonitoringData


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
