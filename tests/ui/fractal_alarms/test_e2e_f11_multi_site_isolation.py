"""E2E-F11 · Concurrent multi-site isolation — the internal QA note 'Plan_Integral_Fractal'
section 7 ("Site: any. IDs: any. An alarm on one site must not generate
events on the others; the rest of the fleet stays healthy").

Unlike E2E-F09/F10 (a single site, `baseline=True` to force a clean "0
alarms" starting point), F11 deliberately does NOT force a clean baseline
on the CONTROL sites -- some of them already carry old stuck-open alerts
from earlier testing (see the internal QA note 'FRACTAL_ALARM_INJECTION_SETUP''s GOTCHA
CRITICO), and "cleaning them up" would defeat the point of an isolation
check. Instead this uses a DELTA comparison: snapshot each control site's
open (rule_id, device) pairs BEFORE injecting on the target site, then
assert none of them gained a NEW pair afterward -- this is valid regardless
of how "dirty" a control site's starting state already is.

Target: BOLIVIA 4, alarm #66 (Container Smoke Detected, PCS-2) -- confirmed
via a direct API check to be a genuinely fresh (site, PCS, rule)
combination (38/46/47/48/49/52/53/70 are all already open on this site
from earlier testing) -- see that same GOTCHA CRITICO section for why
reusing an already-fired combination silently defeats this test instead
of failing loudly. If this file is re-run later, RE-CHECK via the API
rather than assuming #66/PCS-2 is still clean -- it won't be, once this
file itself has run once.

Requires the real local stack for BOLIVIA 4 (simulator + our proxy + edge).
Skips (doesn't fail) if that site's proxy isn't reachable. The 5 control
sites don't need their own stack running -- their alarm state is read
straight from the API/DB, not live telemetry, so an offline control site
works fine for this delta comparison.
"""
from __future__ import annotations

import re
import time

import pytest

from framework_ui.pages.fleet_overview.fleet_overview_page import FleetOverviewPage
from framework_ui.pages.monitoring.monitoring_page import MonitoringPage
from framework_ui.pages.site_view.site_view_page import SiteViewPage
from shared.domain.fractal_register_injection import save_state, clear_state

pytestmark = [pytest.mark.ui, pytest.mark.local_fractal_sim]

TARGET_SITE = "BOLIVIA 4"
TARGET_SITE_ID = "8eae282b-2b6b-44cf-8d6b-bb9540444c63"
# 66 (Container Smoke Detected) -- confirmed via API 2026-09-20 to be a
# genuinely fresh (site, PCS, rule) combo: BOLIVIA 4 already has 38/46/47/
# 48/49/52/53/70 open on one or more PCS from earlier testing THIS SAME DAY
# (FOUR earlier debugging attempts used 46/PCS-1, 47/PCS-2, 48/PCS-3 and
# 49/PCS-1 -- all got burned even when their OWN assertion failed, because
# the injection itself still succeeded and opened a real, permanently-open
# Alert). ALWAYS re-check via the API (`get_alarms()` filtered by site_id)
# for a genuinely unused combo before reusing this file, rather than
# assuming any specific ID is still clean.
TARGET_RULE = 66
TARGET_PCS = 2

# The other 5 BOLIVIA sites -- none of them should gain anything from an
# injection targeted at BOLIVIA 4.
CONTROL_SITES = [
    ("BOLIVIA", "c062518f-d01b-472e-a65c-1047dfb5a605"),
    ("BOLIVIA 1", "97c18d04-d3ca-4ba0-9785-e83c35f3cf57"),
    ("BOLIVIA 2", "35a16c0a-88ec-43dd-8d75-52519290f649"),
    ("BOLIVIA 3", "b278e303-fa68-490c-a537-4c54f16d1bba"),
    ("BOLIVIA 5", "45cb399d-a86b-4dc2-aed2-a9e6a5c18db3"),
]


def _open_keys(alarms, site_id):
    """{(rule_id, device_name)} currently Open for one site -- the identity
    of an alarm occurrence, for a before/after delta comparison."""
    return {(a.rule_id, a.device_name) for a in alarms if a.site_id == site_id and a.is_open}


@pytest.fixture(scope="module")
def isolation_snapshot_then_inject(require_fractal_site, alarms_service, logged_in_page):
    """Module-scoped ON PURPOSE: all 5 tests in this file must share ONE
    injection cycle. Confirmed live 2026-09-20 that a function-scoped
    version breaks the before/after delta model -- alerts never auto-close
    (same lifecycle as the per-combo cache gotcha), so by the time a SECOND
    test's own fixture instantiation snapshots "before", it already
    includes what the FIRST test's injection created moments earlier,
    making every test after the first see an empty delta."""
    require_fractal_site(TARGET_SITE)

    all_before = alarms_service.get_alarms()
    before_by_site = {site_id: _open_keys(all_before, site_id) for _, site_id in CONTROL_SITES}
    target_before = _open_keys(all_before, TARGET_SITE_ID)

    # UI snapshot of the control site BEFORE injecting (for
    # test_fleet_overview_control_site_unaffected -- a real before/after
    # comparison, not just a bare number).
    control_name, _ = CONTROL_SITES[0]
    logged_in_page.get_by_role("link", name=re.compile("Fleet Overview", re.I)).click()
    fleet_overview_page = FleetOverviewPage(logged_in_page).open()
    sites = fleet_overview_page.sites_list()
    control_row = sites.row_index_by_site_name(control_name)
    control_critical_before = sites.critical_count(control_row) if control_row is not None else None

    # Data & Monitoring snapshot of the control site BEFORE injecting (for
    # test_data_monitoring_control_site_raw_bits_unaffected -- Plan
    # Integral: "the raw counters/bits of the other sites don't change
    # during the observation window"). Tolerant of the control site being
    # Offline (no device cards, e.g. the base "BOLIVIA" site) -- confirmed
    # live 2026-09-20 that select_site() hangs 20s waiting for a Device
    # Status Panel that never shows up in that case; don't let that break
    # the WHOLE fixture (and with it the other 6 tests).
    control_raw_bits_before = None
    try:
        logged_in_page.get_by_role("link", name=re.compile("Data & Monitoring", re.I)).click()
        mp = MonitoringPage(logged_in_page).open()
        mp.select_site(control_name)
        viewer = mp.raw_event_bit_viewer()
        control_raw_bits_before = (
            viewer.word_value("evt1"), viewer.word_value("evt2"), viewer.word_value("pcsevt1"))
    except Exception:
        pass

    # Same two-step pattern as F09/F10: observe a real "0" before forcing
    # the 0->1 transition (see GOTCHA CRITICO in
    # the internal QA note 'FRACTAL_ALARM_INJECTION_SETUP').
    save_state(TARGET_SITE, [], baseline=True)
    time.sleep(15)
    save_state(TARGET_SITE, [TARGET_RULE], baseline=True, pcs_override={TARGET_RULE: TARGET_PCS})
    time.sleep(15)

    yield before_by_site, target_before, control_critical_before, control_raw_bits_before

    clear_state(TARGET_SITE)


def test_control_sites_get_no_new_alarms(isolation_snapshot_then_inject, alarms_service):
    """Plan Integral: 'the other sites don't list new rows' / 'the other
    pins remain unchanged' -- verified via API (delta), not by visually
    reading a pin/color."""
    before_by_site, _, _, _ = isolation_snapshot_then_inject
    all_after = alarms_service.get_alarms()

    for name, site_id in CONTROL_SITES:
        after = _open_keys(all_after, site_id)
        new = after - before_by_site[site_id]
        assert not new, (
            f"{name} gained new alarm(s) while injecting into {TARGET_SITE} -- "
            f"fleet isolation broken: {new}")


def test_target_site_gets_the_new_alarm(isolation_snapshot_then_inject, alarms_service):
    """Confirms the injection DID take effect on the target site -- without
    this, a passing test_control_sites_get_no_new_alarms could be passing
    because the whole injection failed, not because isolation is actually
    working."""
    _, target_before, _, _ = isolation_snapshot_then_inject
    all_after = alarms_service.get_alarms()
    target_after = _open_keys(all_after, TARGET_SITE_ID)
    new = target_after - target_before
    assert (TARGET_RULE, f"PCS-{TARGET_PCS}") in new, (
        f"{TARGET_SITE} did NOT gain alarm #{TARGET_RULE} on PCS-{TARGET_PCS} -- "
        f"new keys found: {new!r}")


def test_alarms_and_events_shows_it_only_on_target_site(isolation_snapshot_then_inject, alarms_page):
    """Plan Integral, Alarms & Events: 'the injected alarm appears ONLY on
    the target site'."""
    alarms_page.open()
    rows = alarms_page.rows()

    target_rows = [r for r in rows if r.site == TARGET_SITE and "SMOKE" in r.name.upper()]
    assert target_rows, f"no Container Smoke Detected row appeared for {TARGET_SITE}"

    other_site_names = [name for name, _ in CONTROL_SITES]
    leaked = [r for r in rows if r.site in other_site_names and "SMOKE" in r.name.upper()
              and f"PCS-{TARGET_PCS}" in r.device]
    assert not leaked, (
        f"{TARGET_SITE}'s Container Smoke Detected alarm also appeared on another site: {leaked!r}")


def test_fleet_overview_control_site_unaffected(isolation_snapshot_then_inject, logged_in_page):
    """Plan Integral, Fleet Overview: '#kpiGrid goes up on the target site;
    the other pins remain unchanged'. Compares ONE control site's Critical
    count BEFORE vs AFTER injecting on the target site -- doesn't require
    it to be 0 (it may already carry old noise, see GOTCHA CRITICO), only
    that it didn't go up."""
    control_name, _ = CONTROL_SITES[0]
    _, _, control_critical_before, _ = isolation_snapshot_then_inject
    assert control_critical_before is not None, (
        f"{control_name} wasn't in Fleet Overview's Sites List BEFORE injecting")

    logged_in_page.get_by_role("link", name=re.compile("Fleet Overview", re.I)).click()
    fleet_overview_page = FleetOverviewPage(logged_in_page).open()
    sites = fleet_overview_page.sites_list()

    row = sites.row_index_by_site_name(control_name)
    assert row is not None, f"{control_name} doesn't appear in Fleet Overview's Sites List"
    critical_after = sites.critical_count(row)
    assert critical_after == control_critical_before, (
        f"{control_name}'s Critical count changed ({control_critical_before} -> "
        f"{critical_after}) while injecting into {TARGET_SITE} -- isolation broken")


def test_site_view_control_site_has_no_new_row(isolation_snapshot_then_inject, logged_in_page):
    """Plan Integral, Site View: 'When selecting another site, Recent Alarms
    stays...'. NOTE: doesn't literally require 'No alarms to display' --
    several control sites already have old alarms from earlier tests (see
    GOTCHA CRITICO) -- instead it requires that no NEW Container Smoke
    Detected row for the target site shows up under ANOTHER site."""
    control_name, _ = CONTROL_SITES[0]

    logged_in_page.get_by_role("link", name=re.compile("Site View", re.I)).click()
    sv = SiteViewPage(logged_in_page).open()
    sv.select_site(control_name)

    rows = sv.recent_alarms().rows()
    leaked = [r for r in rows if "SMOKE" in r.description.upper() and f"PCS-{TARGET_PCS}" in r.device]
    assert not leaked, (
        f"a Container Smoke Detected row from {TARGET_SITE} appeared in Site View for "
        f"{control_name}: {leaked!r}")


def test_simulator_control_site_register_unaffected(isolation_snapshot_then_inject):
    """Simulator layer (ground truth): confirms the injection targeted at
    {TARGET_SITE} didn't touch a control site's real register -- reads
    alarm_word_27 (where #66, bit7, lives) of PCS-{TARGET_PCS} on the
    control site and confirms its bit7 is still 0. If that control site
    doesn't have its own stack (simulator/proxy) running, it's skipped
    (not a requirement for F11 -- see the module docstring)."""
    from shared.datasource.fractal_modbus_source import read_fractal_pcs_alarm_words
    from shared.config.settings import FRACTAL_SITE_MODBUS
    import socket

    control_name, _ = CONTROL_SITES[0]
    if control_name not in FRACTAL_SITE_MODBUS:
        pytest.skip(f"{control_name!r} is not in FRACTAL_SITE_MODBUS")
    port, _unit = FRACTAL_SITE_MODBUS[control_name]
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=1.5):
            pass
    except OSError:
        pytest.skip(f"{control_name} doesn't have its own stack running right now -- "
                    f"not a requirement for F11, just an extra check when it's available")

    alarm_words = read_fractal_pcs_alarm_words(control_name, TARGET_PCS - 1)
    assert not (alarm_words[26] & (1 << 7)), (
        f"{control_name} PCS-{TARGET_PCS} alarm_word_27 has bit7 set -- "
        f"the injection into {TARGET_SITE} leaked into another site's real register")


def test_data_monitoring_control_site_raw_bits_unaffected(isolation_snapshot_then_inject, logged_in_page):
    """Plan Integral, Data & Monitoring: 'the raw counters/bits of the other
    sites don't change during the observation window'. Compares the 3
    packed words of the Raw Event Bit Viewer (evt1, evt2, pcsevt1) of a
    control site BEFORE vs AFTER injecting on {TARGET_SITE}."""
    control_name, _ = CONTROL_SITES[0]
    _, _, _, control_raw_bits_before = isolation_snapshot_then_inject
    if control_raw_bits_before is None:
        pytest.skip(f"{control_name} is Offline (no Device Status Panel) -- couldn't "
                    f"capture a 'before' snapshot of the Raw Event Bit Viewer to compare")

    logged_in_page.get_by_role("link", name=re.compile("Data & Monitoring", re.I)).click()
    mp = MonitoringPage(logged_in_page).open()
    mp.select_site(control_name)
    viewer = mp.raw_event_bit_viewer()
    raw_bits_after = (
        viewer.word_value("evt1"), viewer.word_value("evt2"), viewer.word_value("pcsevt1"))

    assert raw_bits_after == control_raw_bits_before, (
        f"{control_name}'s raw Raw Event Bit Viewer words changed "
        f"({control_raw_bits_before} -> {raw_bits_after}) while injecting into "
        f"{TARGET_SITE} -- isolation broken")
