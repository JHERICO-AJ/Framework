"""watch_fleet_power — LIVE monitor of the 3 power layers (simulator vs
API vs UI), for ALL 6 BOLIVIA sites at once. Same pattern as
watch_three_layers.py (Monitoring's single-site version) -- opens the
browser once, logs in, and watches in a loop -- extended to Fleet
Overview's Sites List instead of the single-site Monitoring screen.

Watches only (doesn't assert/fail) -- for demo/debug, so you can watch the
Power column update live as telemetry streams in, right next to the
values it should match. The actual pass/fail assertions live in
tests/ui/fleet_overview/test_fleet_overview_sites_list_values.py
(test_power_matches_recent_simulator_history and friends).

    python -m monitors.watch_fleet_power
"""
from __future__ import annotations

import time

import psycopg2

from shared.config.settings import (
    BASE_URL, FRACTAL_SITE_MODBUS, TOL_ABS_KW,
    DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASSWORD,
)
from shared.config.credentials import load_credentials
from shared.datasource.db_source import get_site_ids
from shared.datasource.fractal_modbus_source import read_fractal_site_total_kw
from framework_api.client.api_client import ApiClient
from framework_api.services.monitoring_service import MonitoringService
from framework_ui.browser.browser_factory import BrowserFactory
from framework_ui.pages.auth.login_page import LoginPage
from framework_ui.pages.fleet_overview.fleet_overview_page import FleetOverviewPage

SITE_NAMES = list(FRACTAL_SITE_MODBUS.keys())
# < the simulator's own ~5s tick, same reasoning as
# test_fleet_overview_sites_list_values.py's POWER_HISTORY_INTERVAL_S: polling
# at exactly the tick rate risks aliasing (occasionally reading the same tick
# twice, or skipping one) -- polling faster avoids that.
POLL_INTERVAL_S = 3


def _site_ids():
    """{site_name: site_id} for the 6 BOLIVIA sites -- a plain read-only
    connection, same settings/pattern as tests/conftest.py's db_conn
    fixture, just without pytest around it."""
    conn = psycopg2.connect(host=DB_HOST, port=DB_PORT, dbname=DB_NAME,
                             user=DB_USER, password=DB_PASSWORD)
    conn.set_session(readonly=True, autocommit=True)
    try:
        return get_site_ids(conn, SITE_NAMES)
    finally:
        conn.close()


def run():
    site_ids = _site_ids()
    svc = MonitoringService(ApiClient(BASE_URL))
    creds = load_credentials()
    print("watch_fleet_power — sim vs API vs UI, all 6 BOLIVIA sites (Ctrl+C to exit)\n")

    factory = BrowserFactory()
    page = factory.__enter__()
    try:
        LoginPage(page).login(creds["email"], creds["password"])
        fleet = FleetOverviewPage(page).open()
        sites_list = fleet.sites_list()

        while True:
            print(time.strftime("%H:%M:%S"))
            for site_name in SITE_NAMES:
                try:
                    sim_kw = read_fractal_site_total_kw(site_name)
                except (ConnectionError, KeyError) as e:
                    print(f"  {site_name:12s} sim unreachable: {e}")
                    continue

                site_id = site_ids.get(site_name)
                api_kw = svc.get_summary(site_id).actual_pcs_power_kw if site_id else None

                row = sites_list.row_index_by_site_name(site_name)
                ui_kw = sites_list.power_kw(row) if row is not None else None

                calc_ok = api_kw is not None and abs(sim_kw - float(api_kw)) <= TOL_ABS_KW
                screen_ok = (ui_kw is not None and api_kw is not None and
                             abs(ui_kw - float(api_kw)) <= TOL_ABS_KW)
                print(f"  {site_name:12s} sim={sim_kw:8.1f}  api={api_kw}  ui={ui_kw}   "
                      f"calc:{'PASS' if calc_ok else 'FAIL'}  screen:{'PASS' if screen_ok else 'FAIL'}")
            print()
            time.sleep(POLL_INTERVAL_S)
    except KeyboardInterrupt:
        print("\ndone.")
    finally:
        factory.__exit__(None, None, None)


if __name__ == "__main__":
    run()
