"""Fleet Overview — Fleet Map site info popup (Qase #14).

REVISED 2026-09-01 against OF-345 (Jira user story, provided by the user)
-- the real spec is:
  "Dado que el usuario pasa el mouse por un marker, cuando se abre el
  popup, entonces se ven nombre, status, location, last seen, SOC, power y
  active alarms." -> HOVER opens the popup (a preview).
  "Dado que el usuario hace click en un marker, cuando se selecciona,
  entonces el mapa hace zoom a ese sitio y el popup queda fijo." -> CLICK
  zooms the map to that site AND pins the popup open.
There is NO "click elsewhere to dismiss" in the spec -- an earlier version
of this file assumed that and even got tests to pass by aiming clicks at
"empty" map area, but that was chasing a behavior that isn't in the actual
requirements. Confirmed live 2026-09-01: hovering opens
`.leaflet-popup`, moving the mouse away does NOT close it, and clicking
makes the marker's own bounding box go stale (the map re-centers/zooms).

Environment fixes that made ANY of this reproducible at all (still true):
  1. BrowserFactory's viewport is 1920x1080 (Playwright's 1280x720 default
     let fixed UI elements overlap the map, blocking real clicks/hovers).
  2. Each site marker is TWO overlapping <path>s (translucent halo + solid
     dot); interacting with the halo gets blocked by the dot on top of it
     -- FleetMap.clickable_marker_by_status() targets the dot.
  3. The popup pane exists in the DOM immediately, but its content renders
     an instant later -- FleetMap.wait_for_popup_content() waits for the
     real "Active Alarms" row instead of reading an empty pane.

Uses whichever site happens to be the first Critical marker (arbitrary,
not necessarily a BOLIVIA site if the shared fleet has other Critical
sites) -- the popup's own site name is read back and used to query the DB
for cross-layer verification of Active Alarms, rather than assuming which
site got clicked.
"""
import time

import pytest

from shared.config.settings import FRACTAL_SITE_MODBUS, TOL_ABS_KW
from shared.datasource.db_source import get_site_ids, count_all_alarms
from shared.datasource.fractal_modbus_source import read_fractal_site_total_kw

pytestmark = pytest.mark.ui


@pytest.fixture
def fresh_map(require_omniops, fleet_overview_page):
    """Reloads the page so each test starts from a genuinely clean map/
    popup state (a popup pinned by a previous test's click would otherwise
    still be open) -- the already-authenticated SSO session cookie means
    this does NOT bounce to /login the way the very first pre-login
    navigation once did."""
    fleet_overview_page.page.reload()
    fleet_overview_page.open()
    fmap = fleet_overview_page.map()
    marker = fmap.clickable_marker_by_status("critical")
    if marker is None:
        pytest.skip("no critical-status site right now")
    return fmap, marker


@pytest.fixture
def hovered_popup(fresh_map):
    """The preview popup -- opened by HOVER, per OF-345."""
    fmap, marker = fresh_map
    fmap.hover_marker(marker)
    fmap.wait_for_popup_content()
    return fmap


@pytest.fixture
def pinned_popup(fresh_map):
    """The pinned popup -- opened by CLICK, per OF-345 (also zooms the map,
    which this fixture doesn't separately verify -- see
    test_click_pins_popup_open_after_mouse_moves_away for that)."""
    fmap, marker = fresh_map
    fmap.click_marker(marker)
    fmap.wait_for_popup_content()
    return fmap


def test_hover_opens_popup(hovered_popup):
    assert hovered_popup.is_popup_open()


def test_popup_shows_expected_fields(hovered_popup):
    fields = hovered_popup.popup_fields()
    for label in ("Location", "Last Seen", "SOC", "Power", "Active Alarms"):
        assert label in fields, f"popup missing {label!r} row: {fields}"


def test_popup_status_matches_critical(hovered_popup):
    assert hovered_popup.popup_status().upper() == "CRITICAL"


def test_popup_active_alarms_matches_db(hovered_popup, db_conn):
    """"Active Alarms" is the ALL-severity count, not just Critical --
    confirmed 2026-08-31 (BOLIVIA showed Active Alarms=11 vs
    Critical-only=9; 11 matches the "Total Alarms" column in the Fleet
    Alarms Analytics "Top sites by alarms" table for the same site)."""
    site_name = hovered_popup.popup_site_name()
    site_ids = get_site_ids(db_conn, [site_name])
    if site_name not in site_ids:
        pytest.skip(f"couldn't resolve {site_name!r} to a site_id in the DB")
    expected = count_all_alarms(db_conn, [site_ids[site_name]])
    actual = int(hovered_popup.popup_fields()["Active Alarms"])
    assert actual == expected


def test_popup_last_seen_is_populated(hovered_popup):
    """Closes a gap flagged 2026-09-01 against
    FLEET_OVERVIEW_FRACTAL_COMPATIBILITY.md §2.4: Last Seen was only
    confirmed to be PRESENT as a field
    (test_popup_shows_expected_fields), never that it holds a real value
    once telemetry is flowing -- same "not the placeholder" check Sites
    List's test_last_seen_is_populated_when_online already does for its
    own Last Seen column."""
    text = hovered_popup.popup_fields().get("Last Seen")
    assert text not in (None, "", "—", "-", "Never"), f"expected a real Last Seen value, got {text!r}"


def test_popup_soc_shows_placeholder(hovered_popup):
    """Per FLEET_OVERVIEW_FRACTAL_COMPATIBILITY.md §2.5: SOC averages
    Battery BMS racks specifically, and Fractal never sends those -- so the
    popup's SOC field should ALWAYS read "-%", regardless of the site's
    health/status. Closes a gap flagged 2026-09-01: SOC was only confirmed
    present as a field, never that its value is specifically the expected
    placeholder (vs., say, silently showing a wrong/stale number)."""
    soc = hovered_popup.popup_fields().get("SOC")
    assert soc == "-%", f"expected the SOC placeholder '-%', got {soc!r}"


POPUP_POWER_HISTORY_DURATION_S = 120
POPUP_POWER_HISTORY_INTERVAL_S = 3
POPUP_POWER_HISTORY_MAX_LATENCY_S = 300


def test_popup_power_matches_recent_simulator_history(pinned_popup):
    """Per FLEET_OVERVIEW_FRACTAL_COMPATIBILITY.md §2.6: popup Power should
    be Σ p_ac_kw across the site's PCS units -- same value/source Sites
    List's Power column uses (see
    test_fleet_overview_sites_list_values.py's 3-layer coverage), just
    read from a different UI location. Closes a gap flagged 2026-09-01:
    the popup's Power was only confirmed present as a field, never
    cross-layer verified like Sites List's Power already is.

    Uses the PINNED (clicked) popup, not the hovered one -- this loop can
    run up to 2 minutes, and only a pinned popup is guaranteed to survive
    that long (a hovered one closes if anything disturbs the mouse).

    Same convergence-window technique as
    test_power_matches_recent_simulator_history: re-reads the popup on
    every loop iteration and checks it against a growing history of
    simulator samples, since a single live comparison can't account for
    real ingestion latency."""
    site_name = pinned_popup.popup_site_name()
    if site_name not in FRACTAL_SITE_MODBUS:
        pytest.skip(f"{site_name!r} isn't a BOLIVIA site with a known Modbus mapping")

    history = []
    elapsed = 0
    while elapsed <= POPUP_POWER_HISTORY_DURATION_S:
        try:
            sim_value = read_fractal_site_total_kw(site_name)
        except ConnectionError as e:
            pytest.skip(f"Fractal simulator for {site_name!r} not reachable: {e}")
        history.append((time.monotonic(), sim_value))

        popup_value = pinned_popup.popup_power_kw()
        assert popup_value is not None, "popup shows no Power value at all"
        match = next((t for t, v in history if abs(v - popup_value) <= TOL_ABS_KW), None)
        if match is not None:
            latency_s = time.monotonic() - match
            print(f"\n[{site_name}] Measured popup->simulator latency for Power: ~{latency_s:.1f}s "
                  f"(popup={popup_value} kW matched a simulator sample from {latency_s:.1f}s ago)")
            assert latency_s <= POPUP_POWER_HISTORY_MAX_LATENCY_S, (
                f"matched, but {latency_s:.1f}s is beyond the sanity ceiling "
                f"of {POPUP_POWER_HISTORY_MAX_LATENCY_S}s -- likely a stale/stuck value")
            return

        pinned_popup.page.wait_for_timeout(POPUP_POWER_HISTORY_INTERVAL_S * 1000)
        elapsed += POPUP_POWER_HISTORY_INTERVAL_S

    pytest.fail(
        f"[{site_name}] popup Power never matched any of the simulator's last "
        f"{POPUP_POWER_HISTORY_DURATION_S}s of ticks ({len(history)} samples, "
        f"within {TOL_ABS_KW} kW). Simulator samples: {[v for _, v in history]}")


def test_click_pins_popup_open_after_mouse_moves_away(pinned_popup):
    """The defining difference between hover and click, per OF-345: a
    CLICKED popup stays open even once the mouse is no longer over the
    marker (a hovered one's persistence isn't specified either way by the
    doc, so this is deliberately only asserted for the click path)."""
    pinned_popup.page.mouse.move(10, 10)
    pinned_popup.page.wait_for_timeout(800)
    assert pinned_popup.is_popup_open(), "pinned popup closed after the mouse moved away"


def test_click_map_background_dismisses_pinned_popup(pinned_popup):
    """Confirmed live 2026-09-01 (the user reported seeing this manually):
    clicking the map's own background — not a marker, not the popup —
    DOES dismiss a pinned popup. Needs the zoom-to-site animation to fully
    settle first (2.5s here; shorter waits were flaky) and the click has
    to land on the map's actual center — corner-area clicks consistently
    failed to close it across repeated tries, likely landing outside the
    rendered tile bounds at that zoom level."""
    pinned_popup.page.wait_for_timeout(2500)
    pinned_popup.click_map_background()
    pinned_popup.page.wait_for_timeout(1000)
    assert not pinned_popup.is_popup_open(), "popup stayed open after clicking the map background"
