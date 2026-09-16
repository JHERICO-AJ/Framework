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

Reuses shared/domain/power.py's matches() for the sim-vs-api comparison --
the SAME domain function watch_three_layers.py uses for Monitoring -- rather
than reinventing tolerance logic locally (confirmed 2026-09-02 this file had
drifted from that shared pattern; fixed to match). A single point-in-time
comparison (this file has no convergence window, unlike the pytest tests)
will still show FAIL during a fast-changing period (e.g. right after the
simulator restarts and ramps up, or while a site is oscillating through
zero on a charge/discharge cycle) -- that's expected, see
docs/HOW_IT_WORKS.md §7.

    python -m monitors.watch_fleet_power              # all 6 BOLIVIA sites
    python -m monitors.watch_fleet_power "BOLIVIA 1"   # just one site
"""
from __future__ import annotations

import time

import psycopg2

from shared.config.settings import (
    BASE_URL, FRACTAL_SITE_MODBUS, UI_TOL_KW, LOGIN_METHOD,
    DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASSWORD,
)
from shared.config.credentials import load_credentials
from shared.datasource.db_source import get_site_ids
from shared.datasource.fractal_modbus_source import read_fractal_site_total_kw
from shared.auth.browser_cookie_export import write_cookie_file
from shared.domain import power
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


def _login_and_open_fleet(factory, creds):
    """Logs in, wires up the API client (post-login, so "microsoft" mode
    picks up a fresh cookie instead of a stale one -- see the docstring
    this comment replaces below for the full "why"), and opens Fleet
    Overview's Sites List. Returns (svc, sites_list)."""
    page = factory.__enter__()
    LoginPage(page).login(creds["email"], creds["password"])

    # Build the API client AFTER login, not before -- in "microsoft"
    # mode the native token endpoint can't validate an SSO password
    # (see shared/auth/factory.py), so ApiClient falls back to
    # CookieAuth reading whatever's in omniops_cookie.txt. Constructing
    # it before login used a STALE cookie left over from a previous
    # run and failed with 401 (confirmed 2026-09-02) -- writing a
    # fresh one from THIS session's browser context first fixes that,
    # same as tests/conftest.py's api_client fixture does.
    if LOGIN_METHOD == "microsoft":
        write_cookie_file(factory.context, domain_substring=BASE_URL.split("//")[1])
    svc = MonitoringService(ApiClient(BASE_URL))

    fleet = FleetOverviewPage(page).open()
    return svc, fleet.sites_list()


def _print_site_row(site_name, site_ids, svc, sites_list):
    """One site's sim/api/ui power read + PASS/FAIL comparison line."""
    try:
        sim_kw = read_fractal_site_total_kw(site_name)
    except (ConnectionError, KeyError) as e:
        print(f"  {site_name:12s} sim unreachable: {e}")
        return

    site_id = site_ids.get(site_name)
    api_kw = svc.get_summary(site_id).actual_pcs_power_kw if site_id else None

    row = sites_list.row_index_by_site_name(site_name)
    ui_kw = sites_list.power_kw(row) if row is not None else None

    # sim vs api: reuse the SAME domain function watch_three_layers.py
    # uses for Monitoring, instead of a locally-reinvented tolerance
    # check (abs+rel tolerance -- see shared/domain/power.py).
    calc_ok = api_kw is not None and power.matches(sim_kw, float(api_kw))
    # api vs ui: NOT the sim-latency comparison above -- both are reads
    # of the same already-ingested value, so the only real "tolerance"
    # needed is the screen's rounding to 1 decimal (UI_TOL_KW), same
    # constant/reasoning watch_three_layers.py uses for its ui_ok.
    screen_ok = (ui_kw is not None and api_kw is not None and
                 abs(round(ui_kw, 1) - round(float(api_kw), 1)) <= UI_TOL_KW)
    print(f"  {site_name:12s} sim={sim_kw:8.1f}  api={api_kw}  ui={ui_kw}   "
          f"calc:{'PASS' if calc_ok else 'FAIL'}  screen:{'PASS' if screen_ok else 'FAIL'}")


def _watch_loop(site_names, site_ids, svc, sites_list):
    while True:
        print(time.strftime("%H:%M:%S"))
        for site_name in site_names:
            _print_site_row(site_name, site_ids, svc, sites_list)
        print()
        time.sleep(POLL_INTERVAL_S)


def run(site_filter=None):
    """site_filter: one BOLIVIA site name (e.g. "BOLIVIA 1") to watch just
    that site instead of all 6 -- see the CLI arg in __main__ below."""
    site_names = SITE_NAMES if site_filter is None else [site_filter]
    site_ids = _site_ids()
    creds = load_credentials()
    print(f"watch_fleet_power — sim vs API vs UI, {site_names} (Ctrl+C to exit)\n")

    factory = BrowserFactory()
    try:
        svc, sites_list = _login_and_open_fleet(factory, creds)
        _watch_loop(site_names, site_ids, svc, sites_list)
    except KeyboardInterrupt:
        print("\ndone.")
    finally:
        factory.__exit__(None, None, None)


if __name__ == "__main__":
    import sys

    arg = sys.argv[1] if len(sys.argv) > 1 else None
    if arg is not None and arg not in FRACTAL_SITE_MODBUS:
        sys.exit(f"{arg!r} isn't a known BOLIVIA site name. Known: {list(FRACTAL_SITE_MODBUS)}")
    run(site_filter=arg)
