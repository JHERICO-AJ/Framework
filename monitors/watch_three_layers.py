"""watch_three_layers — LIVE monitor of the 3 power layers:
simulator vs API vs screen (UI). Opens the browser once and watches in a loop.
    python -m monitors.watch_three_layers
"""
from __future__ import annotations

import time

from shared.config.settings import BASE_URL, SITE_ID, OMNIOPS_EVERY_S, UI_TOL_KW
from shared.config.credentials import load_credentials
from shared.datasource.modbus_source import read_sim_total_kw, close_sim
from shared.domain import power
from framework_api.client.api_client import ApiClient
from framework_api.services.monitoring_service import MonitoringService
from framework_ui.browser.browser_factory import BrowserFactory
from framework_ui.pages.auth.login_page import LoginPage
from framework_ui.pages.monitoring.monitoring_page import MonitoringPage


def run():
    svc = MonitoringService(ApiClient(BASE_URL))
    creds = load_credentials()
    print("watch_three_layers — sim vs API vs UI (Ctrl+C to exit)\n")
    factory = BrowserFactory()
    page = factory.__enter__()
    try:
        LoginPage(page).login(creds["email"], creds["password"])
        mon = MonitoringPage(page).open()
        while True:
            sim_kw, _ = read_sim_total_kw()
            api_kw = svc.get_summary(SITE_ID).actual_pcs_power_kw
            ui_kw = mon.read_pcs_power_kw()
            calc_ok = api_kw is not None and power.matches(sim_kw, float(api_kw))
            ui_ok = (ui_kw is not None and api_kw is not None and
                     abs(round(ui_kw, 1) - round(float(api_kw), 1)) <= UI_TOL_KW)
            print(f"sim={sim_kw:8.0f}  api={api_kw}  ui={ui_kw}   "
                  f"calc:{'PASS' if calc_ok else 'FAIL'}  "
                  f"screen:{'PASS' if ui_ok else 'FAIL'}")
            time.sleep(OMNIOPS_EVERY_S)
    except KeyboardInterrupt:
        print("\ndone.")
    finally:
        factory.__exit__(None, None, None)
        close_sim()


if __name__ == "__main__":
    run()
