"""watch_dispatch_limits — LIVE monitor of Dispatch Limits & Tracking's 3
Fractal-fed blocks: simulator vs API vs UI, side by side, refreshed every
few seconds. Same idea as watch_three_layers.py (simulator vs API vs UI for
Power), applied to docs/OF-145.txt's Actual PCS Power / DC Bus Current /
DC Bus Voltage on BOLIVIA -- but instead of comparing a single instant
(which flickers FAIL just from ingestion latency, since the value keeps
changing live), each tick is checked against a short rolling history of
recent simulator samples -- the same convergence-window idea as
tests/ui/monitoring/test_dispatch_limits_tracking.py, just running
continuously instead of stopping at the first match. Watches in a loop
(doesn't assert/fail) -- for watching with your own eyes in a terminal.
Ctrl+C to exit.

    python -m monitors.watch_dispatch_limits
"""
from __future__ import annotations

import time
from collections import deque

import psycopg2

from shared.config.settings import (
    OMNIOPS_EVERY_S, BASE_URL, DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASSWORD,
)
from shared.config.credentials import load_credentials
from shared.datasource.db_source import get_site_ids
from shared.datasource.fractal_modbus_source import (
    read_fractal_site_total_kw, read_fractal_emu_dc_current_a, read_fractal_emu_dc_voltage_v,
)
from framework_api.client.api_client import ApiClient
from framework_api.services.monitoring_service import MonitoringService
from framework_ui.browser.browser_factory import BrowserFactory
from framework_ui.pages.auth.login_page import LoginPage
from framework_ui.pages.monitoring.monitoring_page import MonitoringPage

SITE_NAME = "BOLIVIA"

# Same tolerances as tests/ui/monitoring/test_dispatch_limits_tracking.py --
# kept in sync deliberately.
TOL_ABS_KW = 50.0
TOL_ABS_A = 50.0
TOL_ABS_V = 5.0

# How much recent simulator history to keep per field, and for how long a
# match is still considered "in sync" rather than stale -- same numbers as
# the pytest convergence window (POWER_HISTORY_DURATION_S/MAX_LATENCY_S).
HISTORY_WINDOW_S = 120
STALE_AFTER_S = 300


def _parse_number(text, unit_suffix):
    if text in (None, "N/A", "—"):
        return None
    return float(text.replace(unit_suffix, "").strip())


def _resolve_bolivia_site_id():
    conn = psycopg2.connect(host=DB_HOST, port=DB_PORT, dbname=DB_NAME, user=DB_USER, password=DB_PASSWORD)
    try:
        return get_site_ids(conn, [SITE_NAME])[SITE_NAME]
    finally:
        conn.close()


class _RollingMatch:
    """Keeps a rolling window of (timestamp, value) simulator samples for
    one field, and reports whether a given reading matches ANY sample still
    within HISTORY_WINDOW_S -- the live equivalent of the pytest
    convergence-window loop, but never stops: old samples just age out."""

    def __init__(self, tolerance):
        self.tolerance = tolerance
        self.samples = deque()  # [(monotonic_time, value), ...]

    def add_sample(self, value):
        now = time.monotonic()
        self.samples.append((now, value))
        while self.samples and now - self.samples[0][0] > HISTORY_WINDOW_S:
            self.samples.popleft()

    def check(self, reading):
        """Returns (ok, latency_s, matched_sim_value) -- the matched value
        is what makes two independently-timed reads visually "go hand in
        hand": even though the UI/API number was captured a few seconds
        after that simulator sample, printing THAT exact matched number
        next to it proves they're the same underlying reading, not a
        coincidence of rounding."""
        if reading is None:
            return None, None, None
        match = next(((t, v) for t, v in reversed(self.samples) if abs(v - reading) <= self.tolerance), None)
        if match is None:
            return False, None, None
        matched_time, matched_value = match
        latency_s = time.monotonic() - matched_time
        return latency_s <= STALE_AFTER_S, latency_s, matched_value


def _print_row(label, sim_value, unit, api_value, api_match, ui_value, ui_match):
    def fmt(value, match):
        if value is None:
            return f"{'—':>9}"
        ok, latency_s, matched_value = match
        if ok is None:
            return f"{value:9.1f} (no reading)"
        if not ok:
            return f"{value:9.1f} FAIL (no simulator sample in the last {HISTORY_WINDOW_S}s matches)"
        return f"{value:9.1f} == sim[{matched_value:9.1f}] from -{latency_s:4.1f}s  MATCH"

    print(f"{label:<18} sim now={sim_value:9.1f} {unit:<3} | api={fmt(api_value, api_match)} | "
          f"ui={fmt(ui_value, ui_match)}")


SIM_TICK_S = 2


def _sample_simulator(kw_history, a_history, v_history):
    """One simulator tick's (kw, a, v) reading, recorded into each rolling
    history. Returns None on a transient read error instead of raising, so
    the caller can just skip this tick and keep looping."""
    try:
        sim_kw = read_fractal_site_total_kw(SITE_NAME)
        sim_a = read_fractal_emu_dc_current_a(SITE_NAME)
        sim_v = read_fractal_emu_dc_voltage_v(SITE_NAME)
    except Exception as e:
        print(f"(transient simulator read error, retrying: {e.__class__.__name__})")
        return None
    kw_history.add_sample(sim_kw)
    a_history.add_sample(sim_a)
    v_history.add_sample(sim_v)
    return sim_kw, sim_a, sim_v


def _read_api_and_ui(monitoring_service, site_id, card):
    """(api_kw, api_a, api_v, ui_kw, ui_a, ui_v), or None on a transient
    read error -- the card re-renders every ~5s (CA-12), so reading it
    mid-render can transiently detach a node Playwright was mid-evaluate
    on. Not a real failure, just skip this print and keep sampling."""
    try:
        dispatch = monitoring_service.get_monitoring_summary(site_id=site_id).dispatch_diagnostics
        api_kw, api_a, api_v = (
            dispatch.actual_pcs_power, dispatch.dc_bus_current, dispatch.dc_bus_voltage)

        values = card.block_values()
        ui_kw = _parse_number(values.get("Actual PCS Power"), " kW")
        ui_a = _parse_number(values.get("DC Bus Current"), " A")
        ui_v = _parse_number(values.get("DC Bus Voltage"), " V")
    except Exception as e:
        print(f"(transient API/UI read error, retrying: {e.__class__.__name__})")
        return None
    return api_kw, api_a, api_v, ui_kw, ui_a, ui_v


def _print_tick(sim_values, api_ui_values, kw_history, a_history, v_history):
    sim_kw, sim_a, sim_v = sim_values
    api_kw, api_a, api_v, ui_kw, ui_a, ui_v = api_ui_values
    _print_row("Actual PCS Power", sim_kw, "kW",
               api_kw, kw_history.check(api_kw), ui_kw, kw_history.check(ui_kw))
    _print_row("DC Bus Current", sim_a, "A",
               api_a, a_history.check(api_a), ui_a, a_history.check(ui_a))
    _print_row("DC Bus Voltage", sim_v, "V",
               api_v, v_history.check(api_v), ui_v, v_history.check(ui_v))
    print("-" * 78)


def _watch_loop(monitoring_service, site_id, card, kw_history, a_history, v_history, api_ui_every):
    tick = 0
    while True:
        sim_values = _sample_simulator(kw_history, a_history, v_history)
        if sim_values is None:
            time.sleep(SIM_TICK_S)
            continue

        if tick % api_ui_every == 0:
            api_ui_values = _read_api_and_ui(monitoring_service, site_id, card)
            if api_ui_values is not None:
                _print_tick(sim_values, api_ui_values, kw_history, a_history, v_history)

        tick += 1
        time.sleep(SIM_TICK_S)


def run():
    creds = load_credentials()
    site_id = _resolve_bolivia_site_id()
    api_client = ApiClient(BASE_URL)
    monitoring_service = MonitoringService(api_client)

    print(f"watch_dispatch_limits — simulator vs API vs UI for {SITE_NAME} (Ctrl+C to exit)")
    print(f"(each PASS/FAIL is a convergence-window match against the last "
          f"{HISTORY_WINDOW_S}s of simulator samples, not a single instant)\n")

    kw_history = _RollingMatch(TOL_ABS_KW)
    a_history = _RollingMatch(TOL_ABS_A)
    v_history = _RollingMatch(TOL_ABS_V)

    # Sample the simulator on its own, tighter tick -- it's the fastest-
    # moving layer (changes every simulator tick, ~1s), so the rolling
    # window needs denser coverage than the ~6s cadence that's reasonable
    # for hitting the API + browser each loop. API/UI are only read every
    # `api_ui_every` sim-ticks, but the sim history in between still gets
    # built up, so when they ARE read there's already a close-in-time
    # sample to match against instead of a stale one from 6s ago.
    api_ui_every = max(1, round(OMNIOPS_EVERY_S / SIM_TICK_S))

    factory = BrowserFactory()
    page = factory.__enter__()
    try:
        LoginPage(page).login(creds["email"], creds["password"])
        mon = MonitoringPage(page).open().select_site(SITE_NAME)
        card = mon.dispatch_limits_tracking()
        _watch_loop(monitoring_service, site_id, card, kw_history, a_history, v_history, api_ui_every)
    except KeyboardInterrupt:
        print("\ndone.")
    finally:
        factory.__exit__(None, None, None)


if __name__ == "__main__":
    run()
