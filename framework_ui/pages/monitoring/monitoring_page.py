"""MonitoringPage — Data & Monitoring screen. Delegates each section to its
own component."""
from __future__ import annotations

from framework_ui.base.base_page import BasePage
from framework_ui.pages.monitoring import monitoring_locators as loc
from framework_ui.pages.monitoring.components.power_card import PowerCard
from framework_ui.pages.monitoring.components.device_status_panel import DeviceStatusPanel
from framework_ui.pages.monitoring.components.gateway_diagnostics import GatewayDiagnostics
from framework_ui.pages.monitoring.components.telemetry_data_table import TelemetryDataTable
from framework_ui.pages.monitoring.components.battery_diagnostics import BatteryDiagnostics
from framework_ui.pages.monitoring.components.dispatch_limits_tracking import DispatchLimitsTracking
from framework_ui.pages.monitoring.components.site_power_telemetry import SitePowerTelemetry
from framework_ui.pages.monitoring.components.event_log import EventLog
from framework_ui.pages.monitoring.components.alarm_history import AlarmHistory
from framework_ui.pages.monitoring.components.thermal_diagnostics import ThermalDiagnostics
from framework_ui.pages.monitoring.components.pcs_energy_statistics import PcsEnergyStatistics
from framework_ui.pages.monitoring.components.site_load_backup_context import SiteLoadBackupContext
from framework_ui.pages.monitoring.components.raw_event_bit_viewer import RawEventBitViewer
from framework_ui.pages.monitoring.components.fault_localization import FaultLocalization
from framework_ui.pages.monitoring.components.environmental_monitoring import EnvironmentalMonitoring
from framework_ui.pages.monitoring.components.site_import_export_power import SiteImportExportPower
from framework_ui.pages.monitoring.components import device_status_panel_locators as device_status_panel_loc


class MonitoringPage(BasePage):
    PATH = "/monitoring?timeRange=24h"

    def open(self):
        """Deliberately NOT calling self.goto(): a direct hard navigation to
        this path bounces back to "/" on the real deployed app (confirmed
        2026-09-04 -- same SPA deep-link limitation FleetOverviewPage.open()
        already works around). Navigate via the sidebar link from wherever
        the page currently is instead."""
        self.page.get_by_role("link", name=loc.SIDEBAR_LINK_TEXT).click()
        self.page.locator(loc.LOADED_MARKER).first.wait_for(timeout=20000)
        return self

    def select_site(self, name):
        """Data & Monitoring is per-site (unlike Fleet Overview's fleet-wide
        view) -- switch the site selector and wait for the new site's
        Device Status Panel to actually render at least one card (the page
        shell itself doesn't change on a site switch, so it's not a useful
        "did it refresh" signal here)."""
        self.page.locator(loc.SITE_SELECT).first.select_option(label=name)
        self.page.locator(device_status_panel_loc.CARD).first.wait_for(timeout=20000)
        return self

    def power_card(self) -> PowerCard:
        return PowerCard(self.page)

    def read_pcs_power_kw(self):
        return self.power_card().value_kw()

    def device_status_panel(self) -> DeviceStatusPanel:
        return DeviceStatusPanel(self.page)

    def gateway_diagnostics(self) -> GatewayDiagnostics:
        return GatewayDiagnostics(self.page)

    def telemetry_data_table(self) -> TelemetryDataTable:
        return TelemetryDataTable(self.page)

    def battery_diagnostics(self) -> BatteryDiagnostics:
        return BatteryDiagnostics(self.page)

    def dispatch_limits_tracking(self) -> DispatchLimitsTracking:
        return DispatchLimitsTracking(self.page)

    def site_power_telemetry(self) -> SitePowerTelemetry:
        return SitePowerTelemetry(self.page)

    def event_log(self) -> EventLog:
        return EventLog(self.page)

    def alarm_history(self) -> AlarmHistory:
        return AlarmHistory(self.page)

    def thermal_diagnostics(self) -> ThermalDiagnostics:
        return ThermalDiagnostics(self.page)

    def pcs_energy_statistics(self) -> PcsEnergyStatistics:
        return PcsEnergyStatistics(self.page)

    def site_load_backup_context(self) -> SiteLoadBackupContext:
        return SiteLoadBackupContext(self.page)

    def raw_event_bit_viewer(self) -> RawEventBitViewer:
        return RawEventBitViewer(self.page)

    def fault_localization(self) -> FaultLocalization:
        return FaultLocalization(self.page)

    def environmental_monitoring(self) -> EnvironmentalMonitoring:
        return EnvironmentalMonitoring(self.page)

    def site_import_export_power(self) -> SiteImportExportPower:
        return SiteImportExportPower(self.page)

    def select_time_range(self, label):
        self.page.locator(loc.TIME_RANGE_SELECT).select_option(label=label)
        return self
