"""Data & Monitoring - Telemetry Data Table (docs/OF-141.txt) -- the raw
telemetry list next to the Device Status Panel.

BOLIVIA (Fractal) specifically. Confirmed 2026-09-09: after switching site,
the Live table's first real row batch can take noticeably longer than the
Device Status Panel cards (observed ~15-18s) -- TelemetryDataTable.wait_for_rows()
polls for either a real row or the documented empty-state message, rather
than a fixed sleep.
"""
import re
import time

import pytest

from shared.config.settings import TOL_ABS_KW
from shared.datasource.db_source import count_monitoring_stat_rows_by_interpolated, get_site_ids
from shared.datasource.fractal_modbus_source import (
    read_fractal_emu_soc_pct, read_fractal_pcs_active_power_kw, read_fractal_site_total_kw,
)
from shared.utils.parsing import parse_first_number
from framework_api.services.monitoring_service import MonitoringService
from framework_ui.pages.monitoring.components import telemetry_snapshots_modal_locators

pytestmark = pytest.mark.ui

SITE_NAME = "BOLIVIA"

# docs/OF-141.txt "Mapeo Fractal -> lecturas de tabla" (lines 247-317) +
# "Gaps Fractal" (line 317): only these 3 subsystems ever produce a row for
# a Fractal site -- HVAC has no Fractal mapping at all, Meter/Network
# metrics aren't in the approved allowlist as their own dropdown category.
SUBSYSTEMS_THAT_CAN_APPEAR_FOR_FRACTAL = {
    "EMS IPC & Gateway", "PCS / Inverter", "Battery / BMS",
}

# CA-03 (docs/OF-141.txt line 578): exactly 7 columns, this exact order.
EXPECTED_COLUMN_HEADERS = ["Timestamp", "Subsystem", "Device", "Metric", "Value", "Unit", "Quality"]

QUALITY_WORDS = {"Good", "Uncertain", "Stale", "Bad"}

# Same convergence-window constants/technique as
# tests/ui/monitoring/test_device_status_panel.py's
# _wait_for_ui_value_to_match_simulator -- kept in sync deliberately (same
# project convention as that file's own docstring notes, itself synced with
# Fleet Overview's copy). 120s (not that file's 60s used briefly here
# before): confirmed 2026-09-09 this table's per-row read is heavier
# (scroll_to_bottom + a full-DOM row snapshot each poll, vs a single
# locator read for a Device Status Panel line), so under full-suite load
# 60s wasn't always enough headroom -- 120s matches Device Status Panel's
# own SOC/SOH tests, which read the same underlying simulator value.
HISTORY_DURATION_S = 120
HISTORY_INTERVAL_S = 3
HISTORY_MAX_LATENCY_S = 300
TOL_ABS_PCT = 0.5


@pytest.fixture(scope="session")
def bolivia_site_id(db_conn):
    return get_site_ids(db_conn, [SITE_NAME])[SITE_NAME]


@pytest.fixture
def bolivia_monitoring_page(require_omniops, monitoring_page):
    return monitoring_page.select_site(SITE_NAME)


@pytest.fixture(autouse=True)
def _close_any_open_snapshots_modal(bolivia_monitoring_page):
    """The browser page is shared across tests in this session
    (BrowserFactory is session-scoped), so a test that opens the "Browse
    snapshots" modal and doesn't close it leaves its overlay blocking the
    NEXT test's navigation (confirmed 2026-09-09: ".monitoring-modal-overlay
    intercepts pointer events" broke the sidebar link click). Closes it
    after every test in this module, whether or not that test opened one."""
    yield
    page = bolivia_monitoring_page.page
    close_button = page.locator(telemetry_snapshots_modal_locators.CLOSE_BUTTON)
    if close_button.count() > 0:
        close_button.click()


@pytest.fixture(autouse=True)
def _reload_if_battery_rack_chip_is_stuck(bolivia_monitoring_page):
    """A test that clicks Battery/BMS's card link leaves behind a
    "Device: Rack" chip that blanks every subsystem's Live rows until
    it's removed -- switching the subsystem dropdown does NOT clear it
    (confirmed 2026-09-10), only the dedicated "Clear" button next to the
    chip does (see test_device_chip_can_be_cleared_per_ca17; this is
    correct, CA-17-compliant behavior, not a defect). Without this
    fixture, a test that clicks that link and forgets to press Clear
    would leave every subsequent test in this file looking at a blanked
    Live table. Clicks Clear (falling back to a full reload if the
    button isn't found for some reason) after every test in this module
    if the chip is still present."""
    yield
    page = bolivia_monitoring_page.page
    card = page.locator(".card:has(.card-title:text-is('Telemetry Data Table'))")
    chips = card.locator(".chip")
    stuck = any(
        "rack" in chips.nth(i).evaluate("el => el.textContent").lower()
        for i in range(chips.count())
    )
    if stuck:
        clear_button = card.locator("button.btn-outline", has_text="Clear")
        if clear_button.count() > 0:
            clear_button.first.click()
            page.wait_for_timeout(1000)
        else:
            page.reload()
            page.wait_for_timeout(3000)
            bolivia_monitoring_page.select_site(SITE_NAME)


def _wait_for_row_to_match_simulator(read_simulator_value, read_ui_value, tolerance, sleep_seconds,
                                      duration_s=HISTORY_DURATION_S, interval_s=HISTORY_INTERVAL_S,
                                      max_latency_s=HISTORY_MAX_LATENCY_S):
    """Same convergence-window technique as
    test_device_status_panel.py's _wait_for_ui_value_to_match_simulator:
    a single snapshot on each side can miss by a tick, so build a growing
    history of simulator samples and re-read the UI each iteration until
    one matches within `tolerance`. `read_ui_value` may return None (the
    row isn't rendered/mounted yet) -- treated as "no match this round",
    not an error."""
    history = []  # [(wall_clock_time, value), ...]
    elapsed = 0
    while elapsed <= duration_s:
        sim_value = read_simulator_value()
        history.append((time.monotonic(), sim_value))

        ui_value = read_ui_value()
        if ui_value is not None:
            match = next((sample_time for sample_time, value in history
                          if abs(value - ui_value) <= tolerance), None)
            if match is not None:
                latency_s = time.monotonic() - match
                assert latency_s <= max_latency_s, (
                    f"matched, but {latency_s:.1f}s is beyond the sanity ceiling "
                    f"of {max_latency_s}s -- likely a stale/stuck row")
                return latency_s

        sleep_seconds(interval_s)
        elapsed += interval_s

    raise AssertionError(
        f"row value never matched any of the simulator's last {duration_s}s of "
        f"ticks ({len(history)} samples, within {tolerance}) -- either latency "
        f"exceeds that window, the row was never rendered, or the table isn't "
        f"showing real simulator data. Simulator samples: {[v for _, v in history]}")


def _subsystem_label(option_text):
    """"EMS IPC & Gateway (84)" -> "EMS IPC & Gateway" -- strips the live
    row-count suffix, which changes every run and isn't part of the
    subsystem's identity."""
    return re.sub(r"\s*\(\d+\)\s*$", "", option_text).strip()


def test_column_headers_match_ca03(bolivia_monitoring_page):
    table = bolivia_monitoring_page.telemetry_data_table()
    assert table.column_headers() == EXPECTED_COLUMN_HEADERS


def test_subsystem_dropdown_only_lists_subsystems_that_produce_rows_for_fractal_site(bolivia_monitoring_page):
    """docs/OF-141.txt line 317: "Gaps Fractal: sin filas por rack/string,
    sin HVAC, sin heartbeat/IP/latencia gateway, sin entidades Rack/TtcStatus."
    Confirmed live 2026-09-09: the real dropdown for BOLIVIA lists only
    EMS IPC & Gateway / PCS Inverter / Battery BMS -- HVAC, Meter, and
    Network never appear as a filter option at all, because they never
    have a row to filter (docs/OF-141.txt: no data -> no row, not a
    disabled/empty option)."""
    table = bolivia_monitoring_page.telemetry_data_table()
    table.wait_for_rows()
    labels = {_subsystem_label(opt) for opt in table.subsystem_options()} - {"All Subsystems", "All"}
    assert labels == SUBSYSTEMS_THAT_CAN_APPEAR_FOR_FRACTAL, (
        f"expected exactly {SUBSYSTEMS_THAT_CAN_APPEAR_FOR_FRACTAL} for a "
        f"Fractal site, got: {labels}")


@pytest.mark.parametrize("card_title, subsystem_label", [
    ("Battery / BMS", "Battery / BMS"),
    ("PCS / Inverter", "PCS / Inverter"),
])
def test_card_link_filters_telemetry_table_and_scrolls_to_it(bolivia_monitoring_page, card_title, subsystem_label):
    """CA-16 (docs/OF-141.txt): "Clic desde el panel -> filtra ese grupo
    (si existe) ... y baja a la tabla." Confirmed live 2026-09-09 these 2
    are the only cards whose click SCROLLS to this table specifically --
    matching docs/OmniOps_Phase1_Demo10_V09.html's own handleDeviceStatusLink
    (batteryRacks/pcsFilter scroll to telemetryCard; the other 4 scroll to
    Site Power Telemetry or Import/Export instead). This is scroll-target
    coverage only, NOT filter coverage: per that same demo JS, ALL 6 cards
    call setSubsystem(...) on Telemetry's own filter regardless of where
    they scroll -- see test_card_link_filters_telemetry_subsystem_for_the_
    3_fractal_relevant_cards for the (broader, corrected) filter check
    covering all 3 Fractal-relevant cards, including EMS IPC & Gateway,
    which filters Telemetry too even though it scrolls elsewhere."""
    panel = bolivia_monitoring_page.device_status_panel()
    table = bolivia_monitoring_page.telemetry_data_table()
    table.wait_for_rows()

    panel.click_link(card_title)
    table.page.wait_for_timeout(1000)

    assert table.selected_subsystem().startswith(subsystem_label), (
        f"expected the telemetry subsystem filter to switch to "
        f"{subsystem_label!r}, got: {table.selected_subsystem()!r}")
    assert table.is_scrolled_into_view(), "expected the page to scroll down to the Telemetry Data Table"


def test_live_table_settles_on_rows_or_documented_empty_state(bolivia_monitoring_page):
    """Sanity check that the Live feed always resolves to one of its 2
    documented states (docs/OF-141.txt CA-19: "No telemetry for the
    selected filters." when there's nothing) -- never hangs indefinitely,
    never shows some third, undocumented state."""
    table = bolivia_monitoring_page.telemetry_data_table()
    table.wait_for_rows()
    assert table.row_count() > 0 or table.is_empty()


@pytest.mark.xfail(
    strict=True,
    reason="Client-approved design (docs/OmniOps_Phase1_Demo10_V09.html, "
           "lines 14154-14160: static example rows run 14:22:30 -> "
           "14:22:27, newest first) overrides docs/OF-141.txt's CA-04 text "
           "('mas antiguo arriba, mas nuevo abajo') where they conflict -- "
           "confirmed by the user 2026-09-09 the demo is what the client "
           "actually signed off on, CA-04's ordering is outdated. The real "
           "deployed app still follows the old CA-04 order (confirmed live: "
           "the card's own subtitle says 'Oldest first, newest at bottom', "
           "and data-index increases top-to-bottom), so this is a real "
           "defect against the approved design, not a doc misreading.")
def test_live_table_shows_newest_rows_first(bolivia_monitoring_page):
    table = bolivia_monitoring_page.telemetry_data_table()
    table.wait_for_rows()
    rows = table.all_row_values()
    if len(rows) < 2:
        pytest.skip(f"only {len(rows)} row(s) rendered -- not enough to check order")

    indices = [r["_data_index"] for r in rows]
    assert indices == sorted(indices, reverse=True), (
        f"expected rows top-to-bottom in descending _data_index order "
        f"(newest first, per the client-approved demo), got: {indices}")


def test_row_quality_is_one_of_the_documented_words(bolivia_monitoring_page):
    """docs/OF-140.txt / docs/ComponentesStatusMonitorign.md sec 8 (cross-
    confirmed): Quality is always Good, Uncertain, Stale, or Bad -- never a
    raw/blank value."""
    table = bolivia_monitoring_page.telemetry_data_table()
    table.wait_for_rows()
    if table.row_count() == 0:
        pytest.skip("no live rows right now to sample Quality from")

    sample_size = min(10, table.row_count())
    for i in range(sample_size):
        quality = table.row_values(i)["Quality"]
        assert quality in QUALITY_WORDS, f"row {i}: unexpected Quality value: {quality!r}"


def _latest_value_for(table, metric, device=None):
    """Re-reads the table fresh each call: searches from the bottom (CA-04,
    newest rows are there) upward for this metric (and device, if given) --
    confirmed 2026-09-09 the virtualized list's default bottom viewport
    doesn't always include every device's latest row for a given metric
    (rows interleave chronologically across ~3 devices x ~9 metrics each),
    so a plain scroll-to-bottom-and-read can miss a row that's genuinely
    there, just a few rows further up. Returns None if truly not found."""
    row = table.search_recent_row_for_metric(metric, device=device)
    return parse_first_number(row["Value"]) if row else None


def test_battery_bms_soc_row_matches_simulator(bolivia_monitoring_page):
    """True cross-layer ground truth for the Telemetry Data Table's own
    "SOC" row (Battery / BMS -- docs/OF-141.txt: Fractal EMU.system_soc_pct
    has no rack/string coordinate, so it's the site-level aggregate row,
    same value source as the Device Status Panel's "SoC range" line, just
    shown here as raw telemetry instead). Doesn't filter by Device: a
    Fractal site's Battery/BMS subsystem has exactly one real device (the
    site/gateway aggregate), and its Device column shows whatever
    DeviceCode that device is registered under -- not a stable, predictable
    label (confirmed 2026-09-09 it can be a data-quality placeholder like
    "00:00:00:00:00:00", same root cause as defect #13's phantom racks).

    KNOWN FLAKE (2026-09-09): passes reliably in isolation or short runs
    (confirmed repeatedly, including a manual side-by-side diagnostic
    showing the UI tracking the simulator within ~4-8s), but has failed a
    few times specifically when this file runs as part of a long (5+ min)
    combined session -- browser/DOM overhead from many prior tests in the
    same long-lived page apparently pushes this specific row's search
    latency past the window occasionally. Not treated as a product defect:
    the underlying behavior is proven correct when measured cleanly."""
    table = bolivia_monitoring_page.telemetry_data_table()
    table.wait_for_rows()
    table.select_subsystem("Battery / BMS")
    table.wait_for_rows()

    try:
        latency_s = _wait_for_row_to_match_simulator(
            read_simulator_value=lambda: read_fractal_emu_soc_pct(SITE_NAME),
            read_ui_value=lambda: _latest_value_for(table, "SOC"),
            tolerance=TOL_ABS_PCT,
            sleep_seconds=lambda seconds: table.page.wait_for_timeout(seconds * 1000),
        )
    except ConnectionError as e:
        pytest.skip(f"Fractal simulator for {SITE_NAME!r} not reachable: {e}")
    except KeyError as e:
        pytest.skip(str(e))
    print(f"\n[{SITE_NAME}] Telemetry Data Table SOC row latency: ~{latency_s:.1f}s")


@pytest.mark.parametrize("pcs_index, device", [(0, "PCS-1"), (1, "PCS-2"), (2, "PCS-3")])
def test_pcs_active_power_row_matches_simulator(bolivia_monitoring_page, pcs_index, device):
    """True cross-layer ground truth for one PCS's own "Active Power" row
    (docs/OF-141.txt: PcsModule.p_ac_kw -> "Active Power" / "PCS / Inverter",
    one row per PCS device) -- NOT the Device Status Panel's site-wide sum
    (read_fractal_site_total_kw); this checks each PCS individually. Unlike
    Battery/BMS's single aggregate device, PCS/Inverter has 3 real,
    individually-addressed devices, so filtering by `device` here is both
    possible and necessary to isolate one PCS's own reading."""
    table = bolivia_monitoring_page.telemetry_data_table()
    table.wait_for_rows()
    table.select_subsystem("PCS / Inverter")
    table.wait_for_rows()

    try:
        latency_s = _wait_for_row_to_match_simulator(
            read_simulator_value=lambda: read_fractal_pcs_active_power_kw(SITE_NAME, pcs_index),
            read_ui_value=lambda: _latest_value_for(table, "Active Power", device=device),
            tolerance=TOL_ABS_KW,
            sleep_seconds=lambda seconds: table.page.wait_for_timeout(seconds * 1000),
        )
    except ConnectionError as e:
        pytest.skip(f"Fractal simulator for {SITE_NAME!r} not reachable: {e}")
    except KeyError as e:
        pytest.skip(str(e))
    print(f"\n[{SITE_NAME}] Telemetry Data Table {device} Active Power row latency: ~{latency_s:.1f}s")


def _api_placeholder_row_value(api_client, site_id, metric):
    """The most recent PCS / Inverter row for `metric` under the
    null-MAC placeholder device, straight from the REAL API endpoint the
    UI's Telemetry Data Table itself calls (confirmed via network capture
    2026-09-11: GET /api/monitoring/telemetry/{siteId}?window=) -- not the
    UI's rendering of it. Returns None if no such row exists right now."""
    rows = MonitoringService(api_client).get_telemetry(site_id=site_id, window="24h")
    candidates = [r for r in rows if r["device"] == "00:00:00:00:00:00"
                  and r["subsystem"] == "PCS / Inverter" and r["metric"] == metric]
    if not candidates:
        return None
    candidates.sort(key=lambda r: r["timestamp"], reverse=True)
    return candidates[0]["value"]


def test_pcs_placeholder_device_row_is_a_real_backend_value_not_a_ui_artifact(
        require_omniops, api_client, bolivia_site_id):
    """3-layer cross-check for the PCS/Inverter MAC-placeholder-device
    defect below: API + Simulator (no UI/browser needed -- this proves the
    NUMBER is legitimate site-level data, independent of how the frontend
    renders it).

    1) API: GET /api/monitoring/telemetry/{siteId} returns 'device':
       '00:00:00:00:00:00' for this Active Power row too (tagId
       '00:00:00:00:00:00:PcsPower') -- confirming the UI isn't inventing
       the placeholder itself, it's just passing through what the backend
       already sends.
    2) Simulator: that row's VALUE genuinely tracks read_fractal_site_total_kw
       (the sum of all 3 real PCS blocks), confirmed live (2026-09-11):
       API value 7331.8 kW vs simulator site total 7633.6 kW at the same
       moment -- close enough (~4%, expected from the read/ingest latency
       already established elsewhere in this file) to confirm this is the
       legitimate EMU-sourced site-wide aggregate documented in
       docs/OF-141.txt ('EMU -> active_power_kw -> PCS / sitio'), not
       garbage data. So the VALUE is correct; only the 'device' identity
       (tested separately below, and already reproduced in the API layer
       here) is the actual defect."""
    try:
        latency_s = _wait_for_row_to_match_simulator(
            read_simulator_value=lambda: read_fractal_site_total_kw(SITE_NAME),
            read_ui_value=lambda: _api_placeholder_row_value(api_client, bolivia_site_id, "Active Power"),
            tolerance=TOL_ABS_KW * 3,  # site total ~= sum of 3 PCS units -- widen vs a single PCS's own tolerance
            sleep_seconds=time.sleep,
        )
    except ConnectionError as e:
        pytest.skip(f"Fractal simulator for {SITE_NAME!r} not reachable: {e}")
    print(f"\n[{SITE_NAME}] API placeholder-device Active Power row latency vs simulator site total: ~{latency_s:.1f}s")


@pytest.mark.xfail(
    strict=True,
    reason="CONFIRMED DEFECT (2026-09-11), root cause pinned down via "
           "docs/omniops_data_intake_BOLIVIA.xlsx's own 'Intake Fields' "
           "sheet, confirmed by the user (this site's own config author): "
           "the site's Data Intake config has TWO separate gateway fields -- "
           "'gateway_mac_id' = '00:00:00:00:00:00', itself annotated "
           "'Default placeholder - replace with actual MAC' (i.e. still the "
           "template default, never replaced), and 'gateway_system_name' = "
           "'EMS Gateway 1', annotated 'Default gateway name' -- the field "
           "specifically meant to be this gateway's human-readable label. "
           "Confirmed directly in emsdevices.\"Device\": this site's "
           "GATEWAY-level, IsAggregator=true device row has DeviceCode AND "
           "DeviceName BOTH synced as the still-placeholder MAC "
           "('00:00:00:00:00:00'), not as 'EMS Gateway 1' -- so the Data "
           "Intake -> Device sync picked the wrong intake field for "
           "DeviceName. This device is the source for the "
           "PCS/Inverter-subsystem site-level aggregate reading (docs/"
           "OF-141.txt: 'EMU -> active_power_kw -> PCS / sitio') AND for "
           "Battery/BMS's site-level SOC/SOH ('defect #13's phantom racks') "
           "-- one wrong DeviceName reaching multiple subsystems' rows. "
           "Confirmed live: polling the PCS / Inverter filter repeatedly "
           "over 24s showed this device's rows (DC Bus Voltage / Reactive "
           "Power / Active Power, Quality=Bad) consistently under the "
           "placeholder, alongside PCS-1/2/3's own correctly-named "
           "PcsModule rows for the same metric names. Confirmed 3-layer "
           "(see test_pcs_placeholder_device_row_is_a_real_backend_value_not_a_ui_artifact "
           "above): the API itself returns 'device': '00:00:00:00:00:00' "
           "for this row (not a UI rendering bug -- the DB record itself "
           "has the wrong name), and the row's VALUE genuinely tracks the "
           "Fractal simulator's real site-total power -- so only the "
           "DeviceName is wrong, not the underlying telemetry.")
def test_pcs_inverter_rows_never_show_mac_placeholder_device(bolivia_monitoring_page):
    table = bolivia_monitoring_page.telemetry_data_table()
    table.wait_for_rows()
    table.select_subsystem("PCS / Inverter")
    table.wait_for_rows()

    placeholder_rows = []
    for _ in range(6):
        rows = table.all_row_values()
        placeholder_rows = [r for r in rows if r.get("Device") == "00:00:00:00:00:00"]
        if placeholder_rows:
            break
        table.page.wait_for_timeout(4000)

    assert not placeholder_rows, (
        f"expected every PCS / Inverter row to show a resolved device id "
        f"(PCS-1/PCS-2/PCS-3), found {len(placeholder_rows)} row(s) with the "
        f"MAC-placeholder device instead: {placeholder_rows[:3]}")


def test_global_time_range_does_not_affect_live_window(bolivia_monitoring_page):
    """CA-09 (docs/OF-141.txt): "Ventana fija de 24 horas. El filtro global
    7d/30d no la cambia." Confirmed live 2026-09-09: the subsystem dropdown
    still lists the same 3 subsystems before and after switching the page's
    global time-range selector to "Last 30 days" -- the Live table's 24h
    window is genuinely independent of that filter, not just visually
    unaffected. Compares labels only (not the live row-count suffix, e.g.
    "PCS / Inverter (1706)"): that count keeps incrementing every ~2-3s as
    real live data arrives regardless of this filter, so comparing the raw
    option text would occasionally fail from data arriving during the
    wait_for_timeout below -- a false failure unrelated to the actual CA,
    which is about which subsystems are offered, not their live counts."""
    table = bolivia_monitoring_page.telemetry_data_table()
    table.wait_for_rows()
    before = {_subsystem_label(opt) for opt in table.subsystem_options()}

    bolivia_monitoring_page.select_time_range("Last 30 days")
    table.page.wait_for_timeout(3000)
    after = {_subsystem_label(opt) for opt in table.subsystem_options()}

    assert before == after, (
        f"Telemetry's subsystem options changed after switching the "
        f"global time range -- expected them to stay fixed to the 24h Live "
        f"window regardless. Before: {before}, after: {after}")


def test_pcs_event_bitfield_is_hex_text(bolivia_monitoring_page):
    """CA-07 (docs/OF-141.txt): "Eventos -> texto hex." Confirmed live
    2026-09-09: "PCS Event Bitfield" values look like "00000082" -- an
    8-digit hex string, Unit "-" (not a number with a made-up unit)."""
    table = bolivia_monitoring_page.telemetry_data_table()
    table.wait_for_rows()
    table.select_subsystem("PCS / Inverter")
    table.wait_for_rows()

    row = table.search_recent_row_for_metric("PCS Event Bitfield")
    if row is None:
        pytest.skip("no 'PCS Event Bitfield' row currently rendered")

    assert re.fullmatch(r"[0-9A-Fa-f]+", row["Value"]), f"not a hex string: {row['Value']!r}"
    assert row["Unit"] == "-", f"expected no unit ('-') for a bitfield, got: {row['Unit']!r}"


def test_timestamp_column_is_valid_local_time_converted_from_utc(bolivia_monitoring_page):
    """Qase #124 [TDT-01] and docs/OmniOps_Phase1_Demo10_V09.html's own
    example rows literally show an ISO-ish 'YYYY-MM-DD HH:MM:SS UTC'
    format. RETRACTED as a defect (2026-09-09, per the user): the real
    app shows a local-time timestamp (no explicit UTC label) -- because
    it converts each reading's real UTC timestamp to the BROWSER's own
    local time, same as this suite already confirmed for the "Browse
    snapshots" modal (see _parse_modal_timestamp_to_utc's own docstring:
    "9 sept 2026, 15:05:00" local lined up with a real "19:05:00 UTC").
    Showing local time without re-stating the timezone on every row is
    standard, intentional UX, applied consistently in both Live and the
    historical modal -- not a formatting bug. This test confirms that
    intended behavior instead of the literal Qase/demo string: a valid
    date+time is shown, and it's genuinely close to the browser's own
    current local time (proving it's a real converted timestamp, not a
    raw UTC value silently mislabeled as local).

    Format corrected 2026-09-11: originally confirmed (2026-09-09) as
    MM/DD/YYYY, but a live re-check now shows DD/MM/YYYY (e.g.
    '11/09/2026, 11:25:33' lines up with the browser's own local time on
    September 11th, not November 9th) -- same day-first format already
    confirmed for Event Log/Alarm History/Site Power Telemetry, so this
    is the column becoming consistent with the rest of the platform, not
    a regression to chase further."""
    import datetime

    table = bolivia_monitoring_page.telemetry_data_table()
    table.wait_for_rows()
    if table.row_count() == 0:
        pytest.skip("no live rows right now to sample a timestamp from")

    table.scroll_to_bottom()  # CA-04: newest rows are at the bottom
    table.page.wait_for_timeout(500)
    rows = table.all_row_values()
    if not rows:
        pytest.skip("no live rows right now to sample a timestamp from")
    sample = rows[-1]["Timestamp"]
    match = re.match(r"(\d{2})/(\d{2})/(\d{4}),\s+(\d{2}):(\d{2}):(\d{2})", sample)
    assert match, f"expected a 'DD/MM/YYYY, HH:MM:SS' local timestamp, got: {sample!r}"

    day, month, year, hour, minute, second = (int(g) for g in match.groups())
    row_local_time = datetime.datetime(year, month, day, hour, minute, second)
    browser_local_time = datetime.datetime.fromisoformat(
        table.page.evaluate("() => new Date().toLocaleString('sv-SE')"))

    age_seconds = (browser_local_time - row_local_time).total_seconds()
    assert -5 <= age_seconds <= 600, (
        f"row timestamp {sample!r} parsed as local time {row_local_time} is "
        f"{age_seconds:.0f}s from the browser's own local now "
        f"({browser_local_time}) -- too far off to be a genuine recent "
        f"UTC-to-local conversion")


def test_balancing_status_is_enumerated_value(bolivia_monitoring_page):
    """Qase #129 [TDT-06] + CA-07 (docs/OF-141.txt line 588): 'Balanceo ->
    Active / Inactive / Fault' -- balancestatus is a raw numeric/boolean
    field translated to one of these 3 words, not shown as a raw 0/1.

    Expected to skip on a Fractal site: confirmed 2026-09-09 (searched up
    to 9000px back with no match) that 'Balancing Status' never renders
    for BOLIVIA at all -- per docs/OF-141.txt line 652 ('Balanceo -> solo
    racks'), this metric only applies at rack level, and a Fractal site
    has 0 real racks (same root cause as the already-documented "phantom
    racks" gap). Kept here (rather than deleted) so this assertion runs
    for real for any manufacturer/site that DOES report real racks."""
    table = bolivia_monitoring_page.telemetry_data_table()
    table.wait_for_rows()
    table.select_subsystem("Battery / BMS")
    table.wait_for_rows()

    row = table.search_recent_row_for_metric("Balancing Status")
    if row is None:
        pytest.skip("no 'Balancing Status' row for this site -- expected for "
                     "a Fractal site (see docstring), since it has 0 real racks")

    assert row["Value"] in {"Active", "Inactive", "Fault"}, (
        f"expected Balancing Status to be one of Active/Inactive/Fault "
        f"per Qase #129 [TDT-06], got: {row['Value']!r}")


_QUALITY_SEVERITY = {"Good": 0, "Uncertain": 1, "Stale": 2, "Bad": 3}


def _age_seconds(row, utc_now):
    """Parses the Live table's ACTUAL rendered format ("09/09/2026,
    21:23:02" -- MM/DD/YYYY, no UTC label, see the real-format defect
    documented in test_timestamp_column_matches_qase_tdt01_format), not
    the Qase-documented one -- this helper only needs to measure real
    elapsed time, not assert on the format itself."""
    import datetime
    ts = datetime.datetime.strptime(row["Timestamp"], "%m/%d/%Y, %H:%M:%S")
    return (utc_now.replace(tzinfo=None) - ts).total_seconds()


def test_quality_transitions_correctly_for_a_single_metric_over_time(bolivia_monitoring_page):
    """Qase #131/#132/#133 [TDT-08/09/10]'s freshness formula, tested the
    only way that's actually valid: watch ONE (subsystem, metric, device)
    row across repeated polls and confirm its OWN Quality only gets more
    severe as its OWN timestamp ages (or resets to less severe when a
    fresh update arrives) -- never the other way around (a Bad row can't
    become Good while getting older, and a Good row can't become Bad
    while its timestamp is getting FRESHER).

    Comparing 2 DIFFERENT metrics' ages against each other doesn't work:
    the formula is relative to EACH metric's own configured sampling
    interval, and confirmed live 2026-09-09 those intervals genuinely
    differ enough to flip a naive comparison -- a Battery/BMS "SOH" row
    at ~4h9m old showed merely "Uncertain", while a PCS "AC Voltage (BC)"
    row only ~4h old was already "Bad" (SOH's own interval is evidently
    much longer than PCS voltage's). So this only ever compares a metric
    against ITS OWN earlier reading.

    A skip here (no Quality transition seen) is an expected, common
    outcome, not a sign of a broken test: fast-updating rows (Battery/PCS,
    ~2-3s cadence) rarely sit still long enough to visibly age between
    Quality tiers within one short poll window, and slow-updating ones
    (docs/OF-140.txt: 'ambient temperature... up to 15-60 min') don't
    transition inside it either. Verifying the EXACT 2x/5x multiplier
    would need the backend's real per-metric interval configuration,
    which isn't exposed anywhere in this UI."""
    import datetime

    table = bolivia_monitoring_page.telemetry_data_table()
    table.wait_for_rows()
    table.select_subsystem("Battery / BMS")
    table.wait_for_rows()

    samples = []
    for _ in range(12):
        row = table.search_recent_row_for_metric("SOC")
        if row is not None:
            utc_now = datetime.datetime.fromisoformat(
                table.page.evaluate("() => new Date().toISOString()").replace("Z", "+00:00"))
            samples.append((_age_seconds(row, utc_now), row["Quality"]))
        table.page.wait_for_timeout(3000)

    transitions = [(a, b) for a, b in zip(samples, samples[1:]) if a[1] != b[1]]
    if not transitions:
        pytest.skip(f"SOC's Quality never changed across {len(samples)} samples "
                     f"over ~36s -- no transition to verify: {samples}")

    for (age_before, quality_before), (age_after, quality_after) in transitions:
        if age_after > age_before:
            assert _QUALITY_SEVERITY[quality_after] >= _QUALITY_SEVERITY[quality_before], (
                f"row got older ({age_before:.1f}s -> {age_after:.1f}s) but "
                f"Quality got LESS severe ({quality_before!r} -> {quality_after!r})")
        else:
            assert _QUALITY_SEVERITY[quality_after] <= _QUALITY_SEVERITY[quality_before], (
                f"row got fresher ({age_before:.1f}s -> {age_after:.1f}s, a new "
                f"reading arrived) but Quality got MORE severe "
                f"({quality_before!r} -> {quality_after!r})")


def test_subsystem_filter_shows_only_that_subsystems_rows(bolivia_monitoring_page):
    """Qase #135 [TDT-12]: 'Select "Battery/BMS" -> only rows with that
    subsystem.' Confirms the filter doesn't just narrow the dropdown's own
    label/count but actually restricts what's rendered."""
    table = bolivia_monitoring_page.telemetry_data_table()
    table.wait_for_rows()
    table.select_subsystem("Battery / BMS")
    table.wait_for_rows()
    if table.row_count() == 0:
        pytest.skip("no rows rendered for Battery / BMS right now")

    subsystems_shown = {r["Subsystem"] for r in table.all_row_values()}
    assert subsystems_shown == {"Battery / BMS"}, (
        f"expected only 'Battery / BMS' rows after filtering, also saw: "
        f"{subsystems_shown - {'Battery / BMS'}}")


# ---------------------------------------------------------------------------
# "Browse snapshots" modal (docs/OF-141.txt CA-21..28) -- a DIFFERENT data
# source (DB 5-min buckets, monitoring.MonitoringStat) than the Live table
# above, frozen at the moment it's opened (no live updates).
# ---------------------------------------------------------------------------

def test_snapshots_modal_opens_with_documented_title_and_note(bolivia_monitoring_page):
    table = bolivia_monitoring_page.telemetry_data_table()
    table.wait_for_rows()
    modal = table.browse_snapshots()
    assert modal.is_open()
    assert "Historical snapshot" in modal.title()
    assert "no live updates" in modal.snapshot_note().lower() or "does not update" in modal.subtitle().lower()


def test_snapshots_modal_column_headers_match_live_table(bolivia_monitoring_page):
    """Same 7 columns as CA-03 -- one shared table shape for both views."""
    table = bolivia_monitoring_page.telemetry_data_table()
    table.wait_for_rows()
    modal = table.browse_snapshots()
    modal.wait_for_rows()
    assert modal.column_headers() == EXPECTED_COLUMN_HEADERS


def test_snapshots_modal_window_buttons_match_ca22(bolivia_monitoring_page):
    """CA-22 (docs/OF-141.txt): "Ventanas: ultimos 5 / 15 / 60 minutos,"
    and "5 minutes" is the default active one on open."""
    table = bolivia_monitoring_page.telemetry_data_table()
    table.wait_for_rows()
    modal = table.browse_snapshots()
    assert modal.window_labels() == ["Last 5 minutes", "Last 15 minutes", "Last 60 minutes"]
    assert modal.active_window_label() == "Last 5 minutes"


def test_snapshots_modal_shows_newest_records_first(bolivia_monitoring_page):
    """CA-25 (docs/OF-141.txt): "En el modal: mas reciente arriba (al reves
    que Live)." Confirmed live 2026-09-09: the pagination area's own label
    literally says "Newest records first" -- and unlike the Live table
    (defect: test_live_table_shows_newest_rows_first), this one is
    genuinely correct, no xfail needed."""
    table = bolivia_monitoring_page.telemetry_data_table()
    table.wait_for_rows()
    modal = table.browse_snapshots()
    modal.wait_for_rows()
    if modal.row_count() == 0:
        pytest.skip("no snapshot rows in the default 'Last 5 minutes' window right now -- "
                     "the pagination/chronology area doesn't render without rows")
    assert modal.chronology_label() == "Newest records first"


def test_snapshots_modal_page_size_options_match_ca24(bolivia_monitoring_page):
    """CA-24 (docs/OF-141.txt): "Paginas de 25 / 50 / 100 filas; se ve
    total de filas y paginas.\""""
    table = bolivia_monitoring_page.telemetry_data_table()
    table.wait_for_rows()
    modal = table.browse_snapshots()
    modal.wait_for_rows()
    assert modal.page_size_options() == ["25", "50", "100"]
    assert re.search(r"Rows\s+[\d,]+.\d+\s+of\s+[\d,]+", modal.pagination_info()), (
        f"unexpected pagination info format: {modal.pagination_info()!r}")


@pytest.mark.xfail(
    strict=True,
    reason="Lead-approved expected behavior (confirmed 2026-09-09, overrides "
           "docs/OF-140.txt / docs/ComponentesStatusMonitorign.md's literal "
           "text describing historical Quality as a bucket-interpolation-"
           "only Good/Uncertain scheme): per the same raw-data correction as "
           "test_snapshots_modal_shows_raw_readings_not_bucket_summaries, "
           "each snapshot row's Quality should use the SAME Good/Uncertain/"
           "Stale/Bad formula as Live -- based on that specific reading's "
           "own real freshness/latency -- not a bucket-interpolation flag. "
           "Confirmed live 2026-09-09: every sampled snapshot row shows "
           "only 'Uncertain', including PCS rows, even though the Live "
           "table's own PCS rows are consistently 'Bad' right now due to a "
           "real, ongoing PCS communication latency issue -- the same "
           "underlying PCS readings that should carry that same 'Bad' into "
           "the snapshot, but don't, because the snapshot's Quality isn't "
           "derived from per-reading freshness at all.")
def test_snapshots_modal_quality_reflects_per_reading_freshness_like_live(bolivia_monitoring_page):
    """If the modal used Live's own Quality formula on real per-reading
    freshness, a subsystem that Live currently shows as "Bad" (PCS /
    Inverter, due to a known real communication latency issue -- see
    test_pcs_active_power_row_matches_simulator's own device coverage)
    should show at least some "Bad" rows in the snapshot too, not just
    "Good"/"Uncertain". This doesn't assert an exact Quality value: it
    only asserts that the historical view is even CAPABLE of showing the
    same distribution Live shows for the same underlying devices."""
    table = bolivia_monitoring_page.telemetry_data_table()
    table.wait_for_rows()
    table.select_subsystem("PCS / Inverter")
    table.wait_for_rows()
    live_pcs_qualities = {r["Quality"] for r in table.all_row_values()}
    if "Bad" not in live_pcs_qualities:
        pytest.skip(f"Live PCS rows aren't showing 'Bad' right now to compare "
                     f"against (got: {live_pcs_qualities}) -- this depends on "
                     f"the real, ongoing PCS latency issue currently being "
                     f"reproducible")

    modal = table.browse_snapshots()
    modal.select_window("Last 60 minutes")
    modal.page.wait_for_timeout(1000)
    modal.wait_for_rows()
    if modal.row_count() == 0:
        pytest.skip("no snapshot rows in 'Last 60 minutes' right now")

    snapshot_pcs_qualities = {
        r["Quality"] for r in modal.all_row_values() if r["Subsystem"] == "PCS / Inverter"
    }
    assert "Bad" in snapshot_pcs_qualities, (
        f"Live shows 'Bad' for PCS / Inverter right now ({live_pcs_qualities}), "
        f"but the snapshot never does for the same subsystem/window "
        f"({snapshot_pcs_qualities}) -- expected the same per-reading "
        f"freshness formula in both views")


def test_snapshots_modal_subsystem_dropdown_matches_live_table(bolivia_monitoring_page):
    """The modal's own subsystem filter should offer the same real
    subsystems as the Live table's (docs/OF-141.txt line 317's Fractal
    gaps apply here too -- it's the same underlying data, just a different
    time slice/source)."""
    table = bolivia_monitoring_page.telemetry_data_table()
    table.wait_for_rows()
    live_labels = {_subsystem_label(opt) for opt in table.subsystem_options()}

    modal = table.browse_snapshots()
    modal.wait_for_rows()
    modal_labels = {_subsystem_label(opt) for opt in modal.subsystem_options()}

    assert modal_labels == live_labels, (
        f"expected the same subsystem options as the Live table, "
        f"live={live_labels}, modal={modal_labels}")


def _snapshot_total_rows(modal):
    """Parses "Rows 1-27 of 27" -> 27 (the total, not the on-page count)."""
    match = re.search(r"of\s+([\d,]+)", modal.pagination_info())
    assert match, f"couldn't parse a total from: {modal.pagination_info()!r}"
    return int(match.group(1).replace(",", ""))


def test_snapshots_modal_window_row_total_grows_with_window_size(bolivia_monitoring_page):
    """CA-22 (docs/OF-141.txt): confirms switching 5/15/60 min genuinely
    fetches more real data, not just changing which button looks active.
    Doesn't assert an exact row count against monitoring.MonitoringStat:
    confirmed 2026-09-09 the rows-per-bucket count itself isn't constant
    (7 vs 9 seen for different buckets), and there's real lag (~5-8 min
    observed) between "now" and the latest computed bucket, so an exact
    DB-vs-UI count would need to reproduce the backend's precise windowing
    rule (confirmed NOT a strict "now() - N minutes" filter -- that
    undercounted vs the UI every time) rather than genuinely validate
    anything. A monotonic growth check is more robust and still proves the
    real claim: wider windows return more data, not a static/stuck result."""
    table = bolivia_monitoring_page.telemetry_data_table()
    table.wait_for_rows()
    modal = table.browse_snapshots()
    modal.wait_for_rows()
    totals = {}
    for window_label in ("Last 5 minutes", "Last 15 minutes", "Last 60 minutes"):
        modal.select_window(window_label)
        modal.page.wait_for_timeout(1000)
        modal.wait_for_rows()
        totals[window_label] = _snapshot_total_rows(modal) if modal.row_count() > 0 else 0

    assert totals["Last 5 minutes"] <= totals["Last 15 minutes"] <= totals["Last 60 minutes"], (
        f"expected row totals to grow (or stay equal) as the window widens, got: {totals}")


@pytest.mark.xfail(
    strict=True,
    reason="Backend bucket-consolidation defect, confirmed system-wide "
           "2026-09-09: monitoring.MonitoringStat.IsInterpolated is True "
           "for virtually every row (10,746 of 10,753 across ALL sites), "
           "including 100% of BOLIVIA's 1526 rows despite 5 days of "
           "genuinely continuous live telemetry -- making 'Good' Quality "
           "unreachable for any established site.")
def test_snapshots_modal_good_quality_is_effectively_unreachable_for_this_site(bolivia_site_id, db_conn):
    """Historical Quality is Good when a bucket is NOT interpolated,
    Uncertain when it is (docs/ComponentesStatusMonitorign.md sec 8).
    Confirmed via direct DB query 2026-09-09: EVERY monitoring.MonitoringStat
    row for BOLIVIA (1526 rows, spanning 5 full days of genuinely continuous
    live telemetry -- independently verified throughout this session) has
    IsInterpolated=True. Checked system-wide too: only 7 of 10,753 rows
    across ALL sites are non-interpolated, all 7 belonging to a single
    OTHER site's very first bucket ever computed (2026-09-08 08:00 UTC) --
    i.e. every bucket computed AFTER a site's first one falls back to
    "interpolated" regardless of real data continuity. This means "Good"
    is a state the UI can display in principle, but the backend
    consolidation logic makes it practically unreachable for any
    established site, masking whatever "Good" is supposed to mean (a
    cleanly-measured bucket) behind a permanent "Uncertain"."""
    counts = count_monitoring_stat_rows_by_interpolated(db_conn, bolivia_site_id)
    assert counts.get(False, 0) > 0, (
        f"expected at least some non-interpolated (Good-eligible) buckets for "
        f"a site with continuous real telemetry -- got {counts}, meaning "
        f"'Good' quality is unreachable for this site despite genuinely "
        f"uninterrupted data")


_SPANISH_MONTHS = {
    "ene": 1, "feb": 2, "mar": 3, "abr": 4, "may": 5, "jun": 6,
    "jul": 7, "ago": 8, "sept": 9, "sep": 9, "oct": 10, "nov": 11, "dic": 12,
}


def _parse_modal_timestamp_to_utc(text, browser_utc_offset_minutes):
    """"9 sept 2026, 15:05:00" (rendered in the BROWSER's local timezone,
    confirmed 2026-09-09: Bolivia is UTC-4, and a shown "15:05:00" lined up
    with a real "19:05:00 UTC") -> an aware UTC datetime, using the
    browser's own reported offset rather than hardcoding UTC-4."""
    import datetime
    match = re.match(r"(\d+)\s+(\w+)\.?\s+(\d+),\s+(\d+):(\d+):(\d+)", text)
    assert match, f"unexpected snapshot timestamp format: {text!r}"
    day, month_abbr, year, hour, minute, second = match.groups()
    month = _SPANISH_MONTHS[month_abbr.lower()]
    local_naive = datetime.datetime(int(year), month, int(day), int(hour), int(minute), int(second))
    return (local_naive - datetime.timedelta(minutes=browser_utc_offset_minutes)).replace(
        tzinfo=datetime.timezone.utc)


@pytest.mark.parametrize("window_label, minutes", [
    ("Last 5 minutes", 5), ("Last 15 minutes", 15),
])
def test_snapshots_modal_window_shows_genuinely_recent_data(bolivia_monitoring_page, window_label, minutes):
    """Confirms "Last N minutes" isn't just a label -- the OLDEST row it
    actually shows must be genuinely within (a small bucket-alignment
    tolerance past) N real minutes ago, not stale data mislabeled as
    recent. Confirmed live 2026-09-09 with the browser's true clock: "Last
    5 minutes" showed data ~5m45s old, "Last 15 minutes" showed data
    ~15m45s old -- both within the ~1 bucket-period (5 min) tolerance
    below, genuinely recent in both cases. Not tested for "Last 60
    minutes": its default first page (25 of 108 rows) doesn't necessarily
    include the oldest row without paging there first."""
    import datetime
    ALIGNMENT_TOLERANCE_MINUTES = 6  # ~1 bucket period of slack

    table = bolivia_monitoring_page.telemetry_data_table()
    table.wait_for_rows()
    modal = table.browse_snapshots()
    modal.select_window(window_label)
    modal.page.wait_for_timeout(1000)
    modal.wait_for_rows()
    if modal.row_count() == 0:
        pytest.skip(f"no snapshot rows in {window_label!r} right now")

    utc_now = datetime.datetime.fromisoformat(
        bolivia_monitoring_page.page.evaluate("() => new Date().toISOString()").replace("Z", "+00:00"))
    browser_utc_offset_minutes = -bolivia_monitoring_page.page.evaluate("() => new Date().getTimezoneOffset()")

    oldest = min(
        _parse_modal_timestamp_to_utc(r["Timestamp"], browser_utc_offset_minutes)
        for r in modal.all_row_values()
    )
    age_minutes = (utc_now - oldest).total_seconds() / 60
    assert age_minutes <= minutes + ALIGNMENT_TOLERANCE_MINUTES, (
        f"{window_label}: oldest row shown is {age_minutes:.1f} min old -- "
        f"that's stale data being shown under a 'last {minutes} minutes' label")


def test_snapshots_modal_stays_frozen_while_open(bolivia_monitoring_page):
    """CA-23 (docs/OF-141.txt): "El momento de referencia se congela al
    abrir el modal." Confirms the OTHER half of that promise, beyond just
    the reference moment being in the past when it opens: while the modal
    stays open, it must never silently fetch newer data out from under the
    user -- matching its own on-screen text ("Snapshot anchored when the
    modal opened -- no live updates in this view"). Confirmed live
    2026-09-09: identical rows and pagination totals before and 30s after
    opening, with real live telemetry continuing to arrive on the Live
    table the whole time (independently verified throughout this session)."""
    table = bolivia_monitoring_page.telemetry_data_table()
    table.wait_for_rows()
    modal = table.browse_snapshots()
    modal.wait_for_rows()
    if modal.row_count() == 0:
        pytest.skip("no snapshot rows right now to confirm staying frozen")

    before_rows = modal.all_row_values()
    before_info = modal.pagination_info()

    modal.page.wait_for_timeout(30000)

    assert modal.pagination_info() == before_info, (
        f"pagination total changed while the modal was open: "
        f"{before_info!r} -> {modal.pagination_info()!r}")
    assert modal.all_row_values() == before_rows, (
        "row contents changed while the modal was open -- it should stay "
        "frozen at the moment it was opened, per its own on-screen note")


@pytest.mark.xfail(
    strict=True,
    reason="Lead-approved expected behavior (confirmed 2026-09-09, overrides "
           "docs/OF-141.txt's literal text -- \"Fuente: Buckets consolidados "
           "cada 5 min en BD\" -- per the user: the lead never approved that "
           "bucket design; the modal should show RAW individual telemetry "
           "readings for the selected window, same granularity as Live, not "
           "one consolidated summary row per metric per 5-min bucket. "
           "Confirmed live 2026-09-09: in the default 'Last 5 minutes' "
           "window, EVERY (Subsystem, Device, Metric) tuple appears at most "
           "once (e.g. PCS-1's own 'Active Power', which Live ticks every "
           "~2-3s, shows only 1 row for the whole 5-minute window) -- the "
           "unambiguous signature of one summarized row per bucket, not raw "
           "per-reading data.")
def test_snapshots_modal_shows_raw_readings_not_bucket_summaries(bolivia_monitoring_page):
    """If this were raw telemetry (same source as Live), a frequently-
    updating metric like a PCS's own "Active Power" should appear MANY
    times within "Last 5 minutes" (Live ticks it every few seconds) --
    not once. This is a structural check for the data model itself, not a
    specific value: it doesn't matter what the readings say, only that
    there's more than one of them per metric+device inside a single
    5-minute window."""
    from collections import Counter

    table = bolivia_monitoring_page.telemetry_data_table()
    table.wait_for_rows()
    modal = table.browse_snapshots()
    modal.select_window("Last 5 minutes")
    modal.page.wait_for_timeout(1000)
    modal.wait_for_rows()
    if modal.row_count() == 0:
        pytest.skip("no snapshot rows in 'Last 5 minutes' right now")

    counts = Counter((r["Subsystem"], r["Device"], r["Metric"]) for r in modal.all_row_values())
    most_repeated_tuple, repeat_count = counts.most_common(1)[0]
    assert repeat_count > 1, (
        f"expected at least one (Subsystem, Device, Metric) to appear more "
        f"than once within 'Last 5 minutes' (raw readings arrive every few "
        f"seconds per docs/OF-141.txt's own Live cadence) -- got at most "
        f"{repeat_count} for every tuple, e.g. {most_repeated_tuple!r}. This "
        f"means the modal is showing one consolidated bucket summary per "
        f"metric, not raw readings.")


def _trend_focus_value_for(page, option_text_prefix):
    """Matches by prefix (e.g. "Meter / CT" instead of the full "Meter /
    CT·PT") so this doesn't depend on reproducing the exact middle-dot
    character the real app's option text uses."""
    trend_select = page.locator(
        ".card:has(.card-title:text-is('Site Power Telemetry')) .filters-group select.select")
    options = trend_select.locator("option")
    return next(
        opt.get_attribute("value") for opt in
        [options.nth(i) for i in range(options.count())]
        if opt.evaluate("el => el.textContent").strip().startswith(option_text_prefix))


@pytest.mark.parametrize("card_title, trend_focus_option", [
    ("Battery / BMS", "Battery / BMS"),
    ("PCS / Inverter", "PCS Power"),
    ("HVAC / Thermal", "HVAC & Aux"),
    ("EMS IPC & Gateway", "EMS & Network"),
    ("Meters / CT-PT", "Meter / CT"),
    ("Network / Tunnel", "EMS & Network"),
])
@pytest.mark.xfail(
    strict=True,
    reason="Confirmed against docs/OmniOps_Phase1_Demo10_V09.html:25539-"
           "25597 (handleDeviceStatusLink -- the client-approved demo's own "
           "JS): EVERY ONE of the 6 Device Status Panel card links calls "
           "BOTH setTrend(...) (updates this chart's Trend Focus) and "
           "setSubsystem(...) (updates Telemetry's subsystem filter) -- "
           "only the scrollIntoView target differs per card (2 scroll to "
           "Telemetry, 3 to this chart, 1 to Import/Export). An earlier, "
           "narrower version of this finding covered only "
           "Battery/BMS+PCS/Inverter; confirmed live 2026-09-09 (with the "
           "Trend Focus and Telemetry subsystem filters explicitly reset "
           "before each click, to rule out leftover state from a previous "
           "click) that the Site Power Telemetry chart's Trend Focus "
           "select NEVER changes for ANY of the 6 cards -- it's a general "
           "gap across all 6, not specific to PCS or to only 2 of them.")
def test_card_link_also_filters_site_power_telemetry_chart(bolivia_monitoring_page, card_title, trend_focus_option):
    """Per docs/OmniOps_Phase1_Demo10_V09.html's own handleDeviceStatusLink,
    every Device Status Panel card's filter link should also switch the
    Site Power Telemetry chart's Trend Focus to the matching option --
    regardless of which section the click actually scrolls to. Resets both
    Trend Focus AND Telemetry's own subsystem filter to a neutral baseline
    before each click (not just Trend Focus) so a leftover selection from
    an earlier click/test can't be mistaken for this click's own effect."""
    page = bolivia_monitoring_page.page
    trend_select = page.locator(
        ".card:has(.card-title:text-is('Site Power Telemetry')) .filters-group select.select")
    table = bolivia_monitoring_page.telemetry_data_table()
    table.wait_for_rows()

    starting_option = "Battery / BMS" if trend_focus_option != "Battery / BMS" else "PCS Power"
    trend_select.select_option(value=_trend_focus_value_for(page, starting_option))
    table.select_subsystem("All Subsystems")
    page.wait_for_timeout(500)

    panel = bolivia_monitoring_page.device_status_panel()
    panel.click_link(card_title)
    page.wait_for_timeout(1500)

    expected_value = _trend_focus_value_for(page, trend_focus_option)
    assert trend_select.input_value() == expected_value, (
        f"expected the Site Power Telemetry chart's Trend Focus to switch "
        f"to {trend_focus_option!r} ({expected_value!r}) after clicking the "
        f"{card_title!r} card's filter link, but it's still "
        f"{trend_select.input_value()!r}")


@pytest.mark.parametrize("card_title, target_card_title", [
    ("HVAC / Thermal", "Thermal Diagnostics"),
    ("EMS IPC & Gateway", "Dispatch Limits & Tracking"),
    ("Meters / CT-PT", "Site Import / Export Power"),
    ("Network / Tunnel", "Gateway Diagnostics"),
])
def test_other_4_card_links_have_no_cross_subsystem_filter_to_desync(
        bolivia_monitoring_page, card_title, target_card_title):
    """Confirms WHY test_card_link_also_filters_site_power_telemetry_chart's
    defect is scoped to only 2 of the 6 Device Status Panel cards (Battery /
    BMS, PCS / Inverter), not all 6: those other 2 cards' links happen to
    also correspond to a "Trend Focus" option on a DIFFERENT, shared,
    multi-subsystem chart (Site Power Telemetry) -- so there's a real
    filter elsewhere that can go out of sync. Confirmed live 2026-09-09
    these other 4 links each open their OWN dedicated, single-subsystem
    section with zero <select> filters of any kind -- there's no
    cross-subsystem selector there to fail to sync, so the same kind of
    defect structurally cannot apply to these 4."""
    page = bolivia_monitoring_page.page
    panel = bolivia_monitoring_page.device_status_panel()
    panel.click_link(card_title)
    page.wait_for_timeout(1000)

    target = page.locator(".card").filter(has=page.locator(".card-title", has_text=target_card_title))
    assert target.count() > 0, f"expected a {target_card_title!r} card to exist after clicking {card_title!r}'s link"
    assert target.locator("select").count() == 0, (
        f"{target_card_title!r} unexpectedly has a select filter -- this "
        f"card is no longer single-subsystem-only, so it may now need the "
        f"same cross-subsystem sync check as Site Power Telemetry")


@pytest.mark.parametrize("card_title, expected_subsystem", [
    ("Battery / BMS", "Battery / BMS"),
    ("PCS / Inverter", "PCS / Inverter"),
    ("EMS IPC & Gateway", "EMS IPC & Gateway"),
])
def test_card_link_filters_telemetry_subsystem_for_the_3_fractal_relevant_cards(
        bolivia_monitoring_page, card_title, expected_subsystem):
    """Broader than test_card_link_filters_telemetry_table_and_scrolls_to_it
    (which also checks scrollIntoView): confirms live 2026-09-09, with the
    subsystem filter explicitly reset to "All Subsystems" before each
    click (to rule out leftover state), that Telemetry's own subsystem
    filter correctly updates for all 3 of the Fractal-relevant cards --
    NOT just Battery/BMS and PCS/Inverter as an earlier, narrower version
    of this finding assumed. EMS IPC & Gateway's link ("Open control vs
    actual") scrolls to a DIFFERENT card (Dispatch Limits & Tracking, per
    docs/OmniOps_Phase1_Demo10_V09.html's own emsControl action, which
    scrolls to sitePowerCard) rather than to Telemetry -- that's a
    deliberate difference in scroll target, not a sign the subsystem
    filter itself is broken; the filter update happens regardless of
    where the click scrolls to.

    The other 3 cards (HVAC / Thermal, Meters / CT-PT, Network / Tunnel)
    aren't included here: per docs/OF-141.txt's "Gaps Fractal", those
    subsystems produce zero Telemetry rows for a Fractal site, so there's
    no valid filter option for them to switch to on THIS site -- not
    something this test can meaningfully verify."""
    table = bolivia_monitoring_page.telemetry_data_table()
    table.wait_for_rows()
    table.select_subsystem("All Subsystems")

    panel = bolivia_monitoring_page.device_status_panel()
    panel.click_link(card_title)
    table.page.wait_for_timeout(1500)

    assert table.selected_subsystem().startswith(expected_subsystem), (
        f"expected clicking {card_title!r}'s link to filter Telemetry to "
        f"{expected_subsystem!r}, got: {table.selected_subsystem()!r}")


@pytest.mark.parametrize("card_title, expected_chip_text", [
    ("Battery / BMS", "Device: Rack"),
    ("PCS / Inverter", "Device: PCS"),
])
def test_card_link_shows_device_chip_per_ca16(bolivia_monitoring_page, card_title, expected_chip_text):
    """CA-16 (docs/OF-141.txt): 'Clic desde el panel -> filtra ese grupo
    (si existe), chip "Device: ..." si aplica, y baja a la tabla.'

    RETRACTED an earlier, incorrect version of this finding (2026-09-09):
    that version assumed CA-16/17's mechanism was a free-text search/tag
    input (matching Qase case #136 [TDT-13]'s own description, 'search
    pre-filled with "rack"'), confirmed absent from the real app (zero
    <input> elements anywhere in the card) and treated as a missing
    feature. That assumption was wrong: OF-141.txt's own CA-16/CA-17 text
    describes a CHIP, not a search box, and confirmed live 2026-09-09 the
    real app DOES show one -- '<span class="chip">Device: Rack</span>'
    for Battery/BMS's link, '<span class="chip">Device: PCS</span>' for
    PCS/Inverter's -- so this part of CA-16 is correctly implemented."""
    table = bolivia_monitoring_page.telemetry_data_table()
    table.wait_for_rows()
    card = bolivia_monitoring_page.page.locator(
        ".card:has(.card-title:text-is('Telemetry Data Table'))")

    panel = bolivia_monitoring_page.device_status_panel()
    panel.click_link(card_title)
    bolivia_monitoring_page.page.wait_for_timeout(1500)

    chips = card.locator(".chip")
    chip_texts = [chips.nth(i).evaluate("el => el.textContent").strip() for i in range(chips.count())]
    assert expected_chip_text in chip_texts, (
        f"expected a {expected_chip_text!r} chip after clicking "
        f"{card_title!r}'s link, got chips: {chip_texts}")


def test_device_chip_can_be_cleared_per_ca17(bolivia_monitoring_page):
    """CA-17 (docs/OF-141.txt): "Clear en el chip -> quita el filtro de
    dispositivo; el de subsistema se mantiene." RETRACTED an earlier,
    incorrect version of this finding (2026-09-10) that claimed no clear
    control exists at all: that check only looked for a control NESTED
    INSIDE the "<span class="chip">Device: Rack</span>" element itself.
    Confirmed live 2026-09-10: the real markup is
    "<span class="chip">Device: Rack</span><button class="btn-outline">
    Clear</button>" -- a SIBLING button next to the chip, not a child of
    it. Clicking it does exactly what CA-17 describes: removes the chip
    and immediately restores real Live rows (confirmed row count went
    from 0 back to 18 in the same moment), while Battery / BMS stays
    selected in the subsystem dropdown."""
    table = bolivia_monitoring_page.telemetry_data_table()
    table.wait_for_rows()
    card = bolivia_monitoring_page.page.locator(
        ".card:has(.card-title:text-is('Telemetry Data Table'))")

    panel = bolivia_monitoring_page.device_status_panel()
    panel.click_link("Battery / BMS")
    bolivia_monitoring_page.page.wait_for_timeout(1500)

    clear_button = card.locator("button.btn-outline", has_text="Clear")
    assert clear_button.count() > 0, (
        "expected a 'Clear' button next to the 'Device: ...' chip, found none")

    clear_button.first.click()
    bolivia_monitoring_page.page.wait_for_timeout(1500)

    chips = card.locator(".chip")
    chip_texts = [chips.nth(i).evaluate("el => el.textContent") for i in range(chips.count())]
    assert not any("Device:" in t for t in chip_texts), (
        f"expected the 'Device: ...' chip to be gone after clicking Clear, still present: {chip_texts}")
    assert table.selected_subsystem().startswith("Battery / BMS"), (
        "expected the subsystem filter to remain 'Battery / BMS' after clearing only the device chip")


def test_battery_bms_subsystem_filter_shows_rows_in_live_table(bolivia_monitoring_page):
    """Selecting "Battery / BMS" in Telemetry Data Table's Live view
    should show its rows -- the same subsystem the Device Status Panel's
    own Battery/BMS card link targets (test_card_link_filters_telemetry_
    subsystem_for_the_3_fractal_relevant_cards already confirms the FILTER
    itself correctly switches to "Battery / BMS"; this test is specifically
    about whether any ROWS actually render under that filter, which is a
    separate question).

    Uses ONLY the dropdown, never the card link: confirmed 2026-09-09 that
    clicking Battery/BMS's own card link leaves behind a "Device: Rack"
    chip that permanently kills every Live row until a full page reload
    (see test_battery_bms_card_link_does_not_break_the_whole_live_table)
    -- earlier apparent flakiness on THIS test was actually contamination
    from an earlier test in the same file/session having clicked that
    link and left the table broken, not a real intermittent issue with
    plain dropdown filtering. The autouse `_reload_if_battery_rack_chip_
    is_stuck` fixture now resets that state after any test that triggers
    it, so this test's own dropdown-only path shouldn't need the ~30s
    polling below anymore -- kept as a safety margin, not because this
    specific path is expected to be flaky."""
    table = bolivia_monitoring_page.telemetry_data_table()
    table.wait_for_rows()
    table.select_subsystem("Battery / BMS")

    for _ in range(10):
        table.wait_for_rows(timeout=1)
        if table.row_count() > 0:
            return
        table.page.wait_for_timeout(3000)

    assert table.row_count() > 0, (
        "Telemetry Data Table shows no Live rows for 'Battery / BMS' after "
        "~30s of polling, even though other subsystems and the DB-backed "
        "Snapshots modal both have fresh data for this same site right now")


def test_battery_bms_card_link_device_filter_is_recoverable_via_clear_button(bolivia_monitoring_page):
    """RETRACTED an earlier, incorrect "CRITICAL/blocker" finding
    (2026-09-09) that claimed clicking the Battery/BMS card's "Filter
    racks in Telemetry Data Table" link permanently breaks the whole Live
    table with no recovery. That check only tried recovering by switching
    the SUBSYSTEM dropdown (to "All Subsystems" and back), which indeed
    never clears the device-level filter -- but that's not a bug: CA-17
    (docs/OF-141.txt) only prescribes a dedicated "Clear" button as the
    mechanism for removing a device-level chip, not switching subsystem.
    Confirmed live 2026-09-10 (see test_device_chip_can_be_cleared_per_
    ca17): the real app DOES have that Clear button (a sibling of the
    chip, not nested inside it -- the earlier check's real mistake), and
    clicking it immediately restores every subsystem's Live rows (18 real
    rows both before the card-link click and after Clear). This test
    confirms that same recovery specifically for "All Subsystems"."""
    page = bolivia_monitoring_page.page
    card = page.locator(".card:has(.card-title:text-is('Telemetry Data Table'))")
    table = bolivia_monitoring_page.telemetry_data_table()
    table.wait_for_rows()

    panel = bolivia_monitoring_page.device_status_panel()
    panel.click_link("Battery / BMS")
    page.wait_for_timeout(2000)

    card.locator("button.btn-outline", has_text="Clear").first.click()
    page.wait_for_timeout(1500)
    table.select_subsystem("All Subsystems")
    page.wait_for_timeout(1500)
    table.wait_for_rows()
    assert table.row_count() > 0, (
        "expected 'All Subsystems' to show real Live rows again after "
        "clicking Clear on the device chip left by Battery/BMS's card link")


@pytest.mark.xfail(
    strict=True,
    reason="Confirmed live 2026-09-10, across all 3 time windows (Last "
           "5/15/60 minutes): filtering the 'Browse snapshots' modal to "
           "'EMS IPC & Gateway' never shows any real row -- only the "
           "documented empty-state message ('No telemetry for the "
           "selected filters.'). This is despite the subsystem dropdown "
           "itself showing a nonzero historical count ('EMS IPC & Gateway "
           "(84)'), and EMS IPC & Gateway being one of the 3 subsystems "
           "confirmed to have real Live rows for this Fractal site (see "
           "test_card_link_filters_telemetry_subsystem_for_the_3_fractal_"
           "relevant_cards). Battery/BMS and PCS/Inverter both show real "
           "snapshot rows under the same conditions.")
def test_ems_gateway_shows_real_rows_in_snapshots_modal(bolivia_monitoring_page):
    """EMS IPC & Gateway has real, ongoing Live telemetry (confirmed
    elsewhere in this suite) and a nonzero historical count in the
    modal's own subsystem dropdown -- so at least one of its 3 time
    windows should show real historical rows, not just the empty state."""
    page = bolivia_monitoring_page.page
    table = bolivia_monitoring_page.telemetry_data_table()
    table.wait_for_rows()
    modal = table.browse_snapshots()
    modal.wait_for_rows()

    modal_select = page.locator(telemetry_snapshots_modal_locators.SUBSYSTEM_SELECT)
    options = modal_select.locator("option")
    ems_value = next(
        (opt.get_attribute("value") for opt in
         [options.nth(i) for i in range(options.count())]
         if "EMS" in opt.evaluate("el => el.textContent")),
        None)
    assert ems_value is not None, "expected an 'EMS IPC & Gateway' option in the modal's subsystem dropdown"

    found_real_row = False
    for window_label in ("Last 5 minutes", "Last 15 minutes", "Last 60 minutes"):
        modal.select_window(window_label)
        modal_select.select_option(value=ems_value)
        page.wait_for_timeout(1500)
        modal.wait_for_rows()
        rows = modal.all_row_values()
        if any(r.get("Subsystem") == "EMS IPC & Gateway" for r in rows):
            found_real_row = True
            break

    assert found_real_row, (
        "EMS IPC & Gateway shows no real rows in any of the 3 time windows "
        "in the Browse snapshots modal, despite having real Live data and "
        "a nonzero historical count in its own subsystem dropdown")




