"""MonitoringService — the MONITORING domain (summary/power). Returns SiteSummary."""
from __future__ import annotations

from framework_api.services.base_service import BaseService
from framework_api.models.site_summary import SiteSummary
from framework_api.models.monitoring_summary import MonitoringSummary
from framework_api.models.power_trend_point import PowerTrendPoint
from shared.config.settings import SITE_ID


class MonitoringService(BaseService):
    PATH = "/api/monitoring/summary/{site_id}"

    def get_summary(self, site_id=SITE_ID) -> SiteSummary:
        payload = self.client.get(self.PATH.format(site_id=site_id))
        return SiteSummary.from_json(payload)

    def get_monitoring_summary(self, site_id=SITE_ID) -> MonitoringSummary:
        """Data & Monitoring screen's Device Status Panel + Gateway
        Diagnostics -- same endpoint as get_summary(), fuller parse."""
        payload = self.client.get(self.PATH.format(site_id=site_id))
        return MonitoringSummary.from_json(payload)

    def get_pcs_energy(self, site_id=SITE_ID, time_range="24h") -> dict:
        """PCS Energy Statistics' own endpoint (docs/OF-150.txt: "GET
        /monitoring/pcs-energy/{siteId}?timeRange="), confirmed via network
        capture 2026-09-11: {chargeEnergy, dischargeEnergy (kWh),
        chargeEnergyMWh, dischargeEnergyMWh (already rounded to 3
        decimals -- what the UI renders verbatim), netEnergyKwh/MWh,
        activePowerKw, reactivePowerKvar, dcBusVoltage, acVoltage,
        dcCurrent, acCurrent}."""
        return self.client.get(f"/api/monitoring/pcs-energy/{site_id}", timeRange=time_range)

    def get_power_trend(self, site_id=SITE_ID, time_range="24h") -> list[PowerTrendPoint]:
        """Site Power Telemetry / Import-Export Power's shared endpoint
        (docs/GraficasMonitoring.md: "Ambas graficas comparten el mismo
        powerTrendData -- no hay endpoint separado de Import/Export").
        Confirmed via network capture 2026-09-13: GET
        /api/monitoring/power-trend/{siteId}?timeRange=24h|7d|30d -> a
        list of hourly (24h) or daily (7d/30d) points, values in kW."""
        payload = self.client.get(f"/api/monitoring/power-trend/{site_id}", timeRange=time_range)
        return PowerTrendPoint.list_from_json(payload)

    def get_telemetry(self, site_id=SITE_ID, window="24h") -> list[dict]:
        """Telemetry Data Table's own live-feed endpoint (confirmed via
        network capture 2026-09-11: GET /api/monitoring/telemetry/{siteId}
        ?window=). Each row: {timestamp, siteId, subsystemCode, subsystem,
        device, tagId, metric, value, displayValue, textValue, unit,
        quality} -- this is the SAME 'device' field the UI's Telemetry Data
        Table renders verbatim, so a placeholder device here (e.g.
        '00:00:00:00:00:00') is a backend data issue, not a UI rendering
        bug."""
        return self.client.get(f"/api/monitoring/telemetry/{site_id}", window=window)
