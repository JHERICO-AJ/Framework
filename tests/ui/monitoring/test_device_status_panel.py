"""Data & Monitoring - Device Status Panel (6 cards: Battery/BMS, PCS/Inverter,
HVAC/Thermal, EMS IPC & Gateway, Meters/CT-PT, Network/Tunnel).

Cross-layer against GET /api/monitoring/summary/{site_id}'s `statusPanel`
array (framework_api/models/monitoring_summary.py) -- confirmed via network
capture 2026-09-04 this is the exact JSON the panel renders from (title,
status, info[] map almost 1:1 to the DOM).

BOLIVIA specifically (not the default SITE_ID) -- Data & Monitoring is
per-site, unlike Fleet Overview's fleet-wide view, so the site selector must
be switched explicitly.
"""
import time

import pytest

import re

from shared.config.settings import TOL_ABS_KW
from shared.datasource.db_source import (
    count_devices_by_level_code, get_configured_gateway_ip, get_gateway_mac_ids,
    get_recent_event_timestamps, get_site_ids,
)
from shared.datasource.fractal_modbus_source import (
    PCS_BASES, PCS_STATUS_WORD_1_BENIGN_BITS,
    read_fractal_emu_soc_pct, read_fractal_emu_soh_pct, read_fractal_site_total_kw,
    read_fractal_emu_station_state, read_fractal_pcs_status_word_1, read_fractal_pcs_alarm_words,
    read_fractal_emu_pcs_comm_connected, read_fractal_meter_total_active_power_kw,
)
from shared.utils.parsing import parse_first_number, parse_kw

pytestmark = pytest.mark.ui

SITE_NAME = "BOLIVIA"

CARD_TITLES = [
    "Battery / BMS", "PCS / Inverter", "HVAC / Thermal",
    "EMS IPC & Gateway", "Meters / CT-PT", "Network / Tunnel",
]

# Same convergence-window constants/technique as Fleet Overview's
# test_power_matches_recent_simulator_history (tests/ui/fleet_overview/
# test_fleet_overview_sites_list_values.py) -- kept in sync deliberately.
POWER_HISTORY_DURATION_S = 120
POWER_HISTORY_INTERVAL_S = 3
POWER_HISTORY_MAX_LATENCY_S = 300

# SOC/SOH change far slower than Power, but still tick live -- a generous
# percentage-point tolerance covers a read a few seconds apart without
# masking a real calculation bug (a real bug would be off by much more
# than a fraction of a percentage point).
TOL_ABS_PCT = 0.5


def _wait_for_ui_value_to_match_simulator(read_simulator_value, read_ui_value, tolerance,
                                           sleep_seconds,
                                           duration_s=POWER_HISTORY_DURATION_S,
                                           interval_s=POWER_HISTORY_INTERVAL_S,
                                           max_latency_s=POWER_HISTORY_MAX_LATENCY_S):
    """Shared convergence-window technique (see
    test_pcs_actual_power_matches_simulator_pcs_sum's docstring for why a
    single snapshot comparison isn't reliable): builds a growing history of
    simulator samples and re-reads the UI each iteration until one matches
    within `tolerance`. Returns the measured UI-to-simulator latency in
    seconds, or raises AssertionError with full history for debugging.
    `sleep_seconds(seconds)` waits between iterations -- callers pass a
    Playwright-aware wait (e.g. `lambda s: page.wait_for_timeout(s * 1000)`)
    so the browser's own event loop keeps pumping while we wait."""
    history = []  # [(wall_clock_time, value), ...]
    elapsed = 0
    while elapsed <= duration_s:
        sim_value = read_simulator_value()
        history.append((time.monotonic(), sim_value))

        ui_value = read_ui_value()
        match = next((sample_time for sample_time, value in history
                      if abs(value - ui_value) <= tolerance), None)
        if match is not None:
            latency_s = time.monotonic() - match
            assert latency_s <= max_latency_s, (
                f"matched, but {latency_s:.1f}s is beyond the sanity ceiling "
                f"of {max_latency_s}s -- likely a stale/stuck value")
            return latency_s

        sleep_seconds(interval_s)
        elapsed += interval_s

    raise AssertionError(
        f"UI value never matched any of the simulator's last {duration_s}s of "
        f"ticks ({len(history)} samples, within {tolerance}) -- either latency "
        f"exceeds that window, or the UI isn't showing real simulator data. "
        f"Simulator samples: {[v for _, v in history]}")


@pytest.fixture(scope="session")
def bolivia_site_id(db_conn):
    return get_site_ids(db_conn, [SITE_NAME])[SITE_NAME]


@pytest.fixture
def bolivia_monitoring_page(require_omniops, monitoring_page):
    return monitoring_page.select_site(SITE_NAME)


@pytest.fixture
def api_summary(monitoring_service, bolivia_site_id):
    return monitoring_service.get_monitoring_summary(site_id=bolivia_site_id)


def test_all_six_device_cards_present_in_fixed_order(bolivia_monitoring_page):
    """CA-02 (docs/OF-140.txt): the 6 cards always render in this exact
    order, not just "all present" -- the order itself is a documented
    requirement, not an implementation detail."""
    panel = bolivia_monitoring_page.device_status_panel()
    assert panel.card_titles() == CARD_TITLES


@pytest.mark.parametrize("title", CARD_TITLES)
def test_card_status_matches_api(bolivia_monitoring_page, api_summary, title):
    """The pill text is lowercase in the UI ("warning") regardless of the
    API's Title-Case status string ("Warning") -- compare case-insensitively."""
    panel = bolivia_monitoring_page.device_status_panel()
    expected = api_summary.card(title)
    assert expected is not None, f"API summary has no statusPanel entry for {title!r}"
    assert panel.status(title).lower() == expected.status.lower()


def _drop_volatile_lines(title, lines):
    """Some info lines carry a live-changing number that can land on
    either side of a UI-vs-API snapshot race even across retries (seen:
    PCS/Inverter's "Actual N kW" swinging -1672 to -3276 kW within 3
    tries ~6s apart; Battery/BMS's "SoC range" oscillating 49.0/49.1
    across 3 tries -- confirmed 2026-09-07). Both already have a proper
    tolerance-based ground-truth test against the simulator directly
    (test_pcs_actual_power_matches_simulator_pcs_sum,
    test_battery_soc_matches_simulator), so they're excluded here rather
    than making this generic exact-match test flaky-by-design for values
    it's the wrong tool to check anyway."""
    if title == "PCS / Inverter":
        return [line for line in lines if not line.startswith("Actual")]
    if title == "Battery / BMS":
        return [line for line in lines if not line.startswith("SoC range")]
    return lines


@pytest.mark.parametrize("title", CARD_TITLES)
def test_card_info_lines_match_api(bolivia_monitoring_page, monitoring_service, bolivia_site_id, title):
    """Retries a few times, re-reading BOTH the UI and the API fresh each
    time (not the cached `api_summary` fixture value) -- some info lines
    carry a live-changing number (e.g. Battery/BMS's "SoC range"), so a
    single snapshot of each side can legitimately land a tick apart and
    differ by a small amount without either side being wrong. Confirmed
    2026-09-07: exactly this happened (SoC 49.1 vs 49.0) and passed clean
    on the very next read a couple seconds later."""
    panel = bolivia_monitoring_page.device_status_panel()
    attempts = 3
    actual, expected_info = None, None
    for attempt in range(attempts):
        expected_card = monitoring_service.get_monitoring_summary(site_id=bolivia_site_id).card(title)
        assert expected_card is not None, f"API summary has no statusPanel entry for {title!r}"
        expected_info = _drop_volatile_lines(title, expected_card.info)
        actual = _drop_volatile_lines(title, panel.info_lines(title))
        if actual == expected_info:
            return
        if attempt < attempts - 1:
            panel.page.wait_for_timeout(2000)
    assert actual == expected_info, (
        f"info lines for {title!r} never matched across {attempts} tries "
        f"(~2s apart) -- if only a live-changing field (e.g. SoC range) "
        f"differs, this is a UI/API read-timing race, not necessarily a "
        f"real bug; a stable-field mismatch would be a real bug")


def test_network_tunnel_communication_status_is_stable_or_unstable(bolivia_monitoring_page):
    """CA-25 (docs/OF-140.txt): the Network/Tunnel card's "Communication
    Status" line is its OWN freshness/gap-based diagnostic (< 3x interval
    and no gaps = Stable, else Unstable) -- a DIFFERENT rule from Gateway
    Diagnostics' heartbeat-based Communication Status (Connected/Watch/
    Disconnected).

    CORRECTION 2026-09-07: an earlier version of this test asserted these
    two values must match, treating a mismatch as a self-contradicting bug.
    That was wrong -- confirmed against the real user story (OF-146 CA-26:
    "misma logica de edad 2x/5x... la ausencia de latido se trata mas
    estricta aqui"; CA-29: a Fractal site with no heartbeat is Disconnected
    in Gateway Diagnostics by design). BOLIVIA is Fractal and never sends a
    heartbeat, so Gateway Diagnostics legitimately shows Disconnected while
    Network/Tunnel's own Stable/Unstable can independently reflect data
    freshness. They are two different measurements, not required to agree."""
    panel = bolivia_monitoring_page.device_status_panel()
    info_lines = panel.info_lines("Network / Tunnel")
    comm_status_line = next((line for line in info_lines if line.startswith("Communication Status:")), None)
    assert comm_status_line is not None, f"no 'Communication Status:' line found in: {info_lines}"
    value = comm_status_line.split(":", 1)[1].strip()
    assert value in ("Stable", "Unstable"), f"unexpected Communication Status word: {value!r}"


def test_network_tunnel_last_communication_word_is_valid(bolivia_monitoring_page):
    """CA-25 (docs/OF-140.txt line 779): "Comunicacion Stable o Unstable;
    ultima comunicacion normal / watch / stale" -- these are the SAME line
    in the CA text but 2 independently-computed values (gap/freshness-based
    Stable/Unstable vs SLA/latency-based normal/watch/stale), confirmed by
    docs/OmniOps_Parameter_Mapping_V03 row 29 using a DIFFERENT threshold
    basis (sampling interval + latency) than row 27's Stable/Unstable rule.
    Seeing "Stable" and "stale" together on the same card (as BOLIVIA does)
    is NOT a contradiction -- same lesson already learned twice this
    session (Heartbeat vs Gateway Diagnostics; this card's own
    Communication Status vs Gateway Diagnostics), just a third instance of
    it with two lines living on the SAME card this time."""
    panel = bolivia_monitoring_page.device_status_panel()
    info_lines = panel.info_lines("Network / Tunnel")
    last_comm_line = next((line for line in info_lines if line.lower().startswith("last communication")), None)
    assert last_comm_line is not None, f"no 'Last communication' line found in: {info_lines}"
    word = last_comm_line.split(" ")[-1].strip().lower()
    assert word in ("normal", "watch", "stale"), f"unexpected Last communication word: {word!r}"


def test_network_tunnel_status_pill_is_not_online_when_pcs_comm_is_really_lost(bolivia_monitoring_page):
    """CA-26 (docs/OF-140.txt line 781): "0 avisos -> '0 communication
    warnings'. 1 aviso -> Warning. 2 o mas -> Fault." We can't read the
    exact warning count from a durable source (it lives in a ~5s in-memory
    cache, docs/OF-140.txt's "Origen en pantalla" table -- confirmed
    2026-09-08 it doesn't match either events."Alert" or events."Event"
    directly), but we CAN confirm independently, from the same real
    simulator bit already used for EMS IPC & Gateway, that a genuine
    PCS-comm-lost condition exists right now -- which per CA-26 guarantees
    AT LEAST 1 real warning, so the pill must not claim Online. This is
    expected to PASS."""
    try:
        any_disconnected = _any_pcs_comm_disconnected()
    except ConnectionError as e:
        pytest.skip(f"Fractal simulator for {SITE_NAME!r} not reachable: {e}")
    except KeyError as e:
        pytest.skip(str(e))
    if not any_disconnected:
        pytest.skip("all 3 PCS RS485 links Connected on the simulator right now -- "
                     "outside this claim's scope")

    panel = bolivia_monitoring_page.device_status_panel()
    status = panel.status("Network / Tunnel").lower()
    assert status != "online", (
        f"a real PCS-comm-lost condition exists (confirmed on the "
        f"simulator), so per CA-26 there must be at least 1 real "
        f"communication warning -- the pill should not claim Online, got: {status!r}")


@pytest.mark.xfail(
    strict=True,
    reason="Discovered 2026-09-08 investigating the Network/Tunnel "
           "'communication warnings' count: raw PCS_COMM_LOST events for "
           "BOLIVIA fire roughly every ~1.7s (2145 in the last hour alone) "
           "-- far faster than the documented 5-10s sampling interval "
           "(docs/OmniOps_Parameter_Mapping_V03). docs/OF-140.txt's own "
           "fallback rule for this card ('Eventos + alarmas 24h') means "
           "warning counts are built from this same raw event stream, so "
           "an inflated generation rate likely inflates every "
           "'communication warnings' figure shown anywhere in the system, "
           "not just this card. This checks the upstream rate directly "
           "(durable, in events.\"Event\"), independent of the in-memory "
           "cache the UI itself reads from.")
def test_pcs_comm_lost_events_fire_no_faster_than_sampling_interval(db_conn, bolivia_site_id):
    MIN_EXPECTED_INTERVAL_S = 4.0  # generous floor under the documented 5-10s

    timestamps = get_recent_event_timestamps(db_conn, bolivia_site_id, "PCS_COMM_LOST", limit=50)
    if len(timestamps) < 2:
        pytest.skip(f"only {len(timestamps)} PCS_COMM_LOST event(s) for {SITE_NAME} -- "
                     f"not enough to measure a rate")

    deltas_s = sorted(
        (timestamps[i] - timestamps[i + 1]).total_seconds()
        for i in range(len(timestamps) - 1)
    )
    median_delta_s = deltas_s[len(deltas_s) // 2]
    assert median_delta_s >= MIN_EXPECTED_INTERVAL_S, (
        f"median gap between consecutive PCS_COMM_LOST events is "
        f"{median_delta_s:.1f}s, faster than the documented 5-10s sampling "
        f"interval (floor {MIN_EXPECTED_INTERVAL_S}s) -- events appear to "
        f"fire every poll cycle instead of once per condition, inflating "
        f"any downstream 'communication warnings' count")


def test_pcs_actual_power_matches_simulator_pcs_sum(bolivia_monitoring_page):
    """True cross-layer ground truth, bypassing the API entirely: per
    docs/OF-140.txt's "Calculo" rule for the PCS/Inverter card --
    "Setpoint/actual: suma PCS individuales -> agregado SYS -> valor
    sitio" -- the site's Actual power must be the SUM of each PCS's own
    p_ac_kw, NOT a direct read of EmuStatus.active_power_kw (the EMU's own
    aggregate). Confirmed 2026-09-07 these two genuinely diverge by
    ~0.1 kW on the live BOLIVIA simulator (rounding: summing 3 already-
    rounded PCS values isn't bit-identical to the EMU's own internal sum)
    -- so which source is "correct" isn't moot, it's the documented rule,
    and read_fractal_site_total_kw() (shared/datasource/fractal_modbus_source.py)
    implements exactly that rule (sums the 3 PCS bases), not the EMU shortcut.

    Same convergence-window technique as Fleet Overview's
    test_power_matches_recent_simulator_history: the UI's current value at
    test start reflects an earlier ingestion cycle than "right now", so
    build a growing history of simulator samples and re-read the UI each
    iteration until one matches within TOL_ABS_KW."""
    panel = bolivia_monitoring_page.device_status_panel()

    history = []  # [(wall_clock_time, value), ...]
    elapsed = 0
    while elapsed <= POWER_HISTORY_DURATION_S:
        try:
            sim_value = read_fractal_site_total_kw(SITE_NAME)
        except ConnectionError as e:
            pytest.skip(f"Fractal simulator for {SITE_NAME!r} not reachable: {e}")
        except KeyError as e:
            pytest.skip(str(e))
        history.append((time.monotonic(), sim_value))

        info_lines = panel.info_lines("PCS / Inverter")
        actual_line = next((line for line in info_lines if line.startswith("Actual")), None)
        assert actual_line is not None, f"no 'Actual' line found in: {info_lines}"
        ui_value = parse_kw(actual_line)
        assert ui_value is not None, f"couldn't parse a kW value from: {actual_line!r}"

        match = next((t for t, v in history if abs(v - ui_value) <= TOL_ABS_KW), None)
        if match is not None:
            latency_s = time.monotonic() - match
            print(f"\n[{SITE_NAME}] Measured UI->simulator latency for PCS Actual power: "
                  f"~{latency_s:.1f}s (UI={ui_value} kW matched a simulator PCS-sum "
                  f"sample from {latency_s:.1f}s ago)")
            assert latency_s <= POWER_HISTORY_MAX_LATENCY_S, (
                f"matched, but {latency_s:.1f}s is beyond the sanity ceiling "
                f"of {POWER_HISTORY_MAX_LATENCY_S}s -- likely a stale/stuck value")
            return

        panel.page.wait_for_timeout(POWER_HISTORY_INTERVAL_S * 1000)
        elapsed += POWER_HISTORY_INTERVAL_S

    pytest.fail(
        f"[{SITE_NAME}] Device Status Panel's PCS 'Actual' power never matched any of "
        f"the simulator's last {POWER_HISTORY_DURATION_S}s of PCS-sum ticks "
        f"({len(history)} samples, within {TOL_ABS_KW} kW) -- either latency exceeds "
        f"that window, or the panel isn't summing the 3 PCS values per the documented "
        f"rule. Simulator samples: {[v for _, v in history]}")


def _soc_range_value(panel):
    """Battery/BMS's "SoC range" line renders as e.g. "SoC range:
    49.1-49.1%" (min-max, equal when there's no per-rack detail -- BOLIVIA
    is Fractal, no racks) -- parse_first_number reads the first (min)
    figure, sufficient since min==max here."""
    info_lines = panel.info_lines("Battery / BMS")
    soc_line = next((line for line in info_lines if line.startswith("SoC range")), None)
    assert soc_line is not None, f"no 'SoC range' line found in: {info_lines}"
    value = parse_first_number(soc_line)
    assert value is not None, f"couldn't parse a percentage from: {soc_line!r}"
    return value


def _soh_value(panel):
    info_lines = panel.info_lines("Battery / BMS")
    soh_line = next((line for line in info_lines if line.startswith("SoH")), None)
    assert soh_line is not None, f"no 'SoH' line found in: {info_lines}"
    value = parse_first_number(soh_line)
    assert value is not None, f"couldn't parse a percentage from: {soh_line!r}"
    return value


def test_battery_soc_matches_simulator(bolivia_monitoring_page):
    """True cross-layer ground truth for Battery/BMS's "SoC range" line:
    docs/OF-140.txt maps it to Fractal EMU.system_soc_pct ("Fractal --
    EMU / SystemSocPct / SOC del sitio"). Same convergence-window
    technique as the PCS Actual power test -- SOC moves slower than Power
    but still ticks live, so a single snapshot on each side can miss by a
    fraction of a percentage point without either side being wrong."""
    panel = bolivia_monitoring_page.device_status_panel()
    try:
        latency_s = _wait_for_ui_value_to_match_simulator(
            read_simulator_value=lambda: read_fractal_emu_soc_pct(SITE_NAME),
            read_ui_value=lambda: _soc_range_value(panel),
            tolerance=TOL_ABS_PCT,
            sleep_seconds=lambda seconds: panel.page.wait_for_timeout(seconds * 1000),
        )
    except ConnectionError as e:
        pytest.skip(f"Fractal simulator for {SITE_NAME!r} not reachable: {e}")
    except KeyError as e:
        pytest.skip(str(e))
    print(f"\n[{SITE_NAME}] Measured UI->simulator latency for SoC: ~{latency_s:.1f}s")


def test_battery_soh_matches_simulator(bolivia_monitoring_page):
    """True cross-layer ground truth for Battery/BMS's "SoH" line:
    docs/OF-140.txt maps it to Fractal EMU.system_soh_pct, a straight
    passthrough (no aggregation/fallback) per the "Calculo" table ("SOH:
    SiteSOH -> SOH banco"). Confirmed 2026-09-07 by hand this matches
    exactly (raw=990 -> 99.0%, UI shows "SoH 99.0%") -- this makes that
    check a permanent, repeatable test instead of a one-off script."""
    panel = bolivia_monitoring_page.device_status_panel()
    try:
        latency_s = _wait_for_ui_value_to_match_simulator(
            read_simulator_value=lambda: read_fractal_emu_soh_pct(SITE_NAME),
            read_ui_value=lambda: _soh_value(panel),
            tolerance=TOL_ABS_PCT,
            sleep_seconds=lambda seconds: panel.page.wait_for_timeout(seconds * 1000),
        )
    except ConnectionError as e:
        pytest.skip(f"Fractal simulator for {SITE_NAME!r} not reachable: {e}")
    except KeyError as e:
        pytest.skip(str(e))
    print(f"\n[{SITE_NAME}] Measured UI->simulator latency for SoH: ~{latency_s:.1f}s")


# ---------------------------------------------------------------------------
# Deterministic "always this placeholder" checks for fields Fractal's wire
# protocol structurally cannot supply -- confirmed against
# docs/GUIA_CONSUMO_PROTO_FRACTAL.md's EMU_FIELDS/PCS_FIELDS (no cell
# voltage, no balancing, no setpoint/CCL/DCL fields anywhere), so these
# aren't "usually" a placeholder, they're a hard fact for any Fractal site,
# and docs/OF-140.txt's "Si no hay nada" fallback column gives the exact
# expected text -- no live/simulator read needed to know the answer.
# ---------------------------------------------------------------------------

def test_cell_voltage_delta_is_always_dash_for_fractal_site(bolivia_monitoring_page):
    """docs/OF-140.txt fallback table (Battery/BMS): "Delta celular" with
    nothing to compute it from -> "Cell Voltage Delta = -". Fractal has no
    per-string/per-cell voltage field anywhere in EMU_FIELDS/PCS_FIELDS
    (confirmed 2026-09-07 against the real register map), so this is
    guaranteed, not merely typical, for any Fractal site."""
    panel = bolivia_monitoring_page.device_status_panel()
    info_lines = panel.info_lines("Battery / BMS")
    assert "Cell Voltage Delta = —" in info_lines, (
        f"expected the documented dash fallback, got: {info_lines}")


def test_balancing_is_always_dash_for_fractal_site(bolivia_monitoring_page):
    """docs/OF-140.txt fallback table (Battery/BMS): "Balanceo" comes only
    from racks ("Solo racks") -> "-" when there's nothing. Fractal has no
    CellsBalancing-equivalent field (that's an EPC-only source per OF-140's
    own mapping table), so this is guaranteed for any Fractal site."""
    panel = bolivia_monitoring_page.device_status_panel()
    info_lines = panel.info_lines("Battery / BMS")
    assert "Balancing: —" in info_lines, (
        f"expected the documented dash fallback, got: {info_lines}")


def test_pcs_setpoint_is_always_na_for_fractal_site(bolivia_monitoring_page):
    """docs/OF-140.txt fallback table (PCS/Inverter): "Setpoint" with
    nothing to compute it from -> "PCS Setpoint N/A". Fractal's wire
    protocol has no setpoint field (OF-140 sec 5.2: "Setpoint, CCL_A,
    DCL_A -- JSON legacy; no en snapshot EPC/Fractal actual"), so this is
    guaranteed for any Fractal site."""
    panel = bolivia_monitoring_page.device_status_panel()
    info_lines = panel.info_lines("PCS / Inverter")
    assert "PCS Setpoint N/A" in info_lines, (
        f"expected the documented N/A fallback, got: {info_lines}")


def test_charge_discharge_limit_is_always_unavailable_for_fractal_site(bolivia_monitoring_page):
    """docs/OF-140.txt fallback table (PCS/Inverter): "Limite C/D" needs
    fresh CCL+DCL -> "Unavailable" / "N/A A" when absent. Same root cause
    as the Setpoint check above (CCL_A/DCL_A don't exist in Fractal's
    wire protocol), so this is guaranteed for any Fractal site."""
    panel = bolivia_monitoring_page.device_status_panel()
    info_lines = panel.info_lines("PCS / Inverter")
    limit_line = next((line for line in info_lines if line.startswith("Charge/Discharge limit")), None)
    assert limit_line is not None, f"no 'Charge/Discharge limit' line found in: {info_lines}"
    assert "Unavailable" in limit_line and "N/A" in limit_line, (
        f"expected the documented Unavailable/N/A fallback, got: {limit_line!r}")


def test_hvac_fields_are_always_na_for_fractal_site(bolivia_monitoring_page):
    """docs/OF-140.txt fallback table (HVAC/Thermal): all 3 lines fall back
    to N/A / "No hot-spot indices" when there's nothing to compute them
    from. Confirmed in docs/Informacion MOnitoring.md: NEITHER manufacturer
    sends HVAC data through this channel today ("Ninguno de los dos llena
    hoy HVAC... por este canal"), so this is guaranteed for any site right
    now, not just Fractal -- kept in this Fractal-specific test file since
    that's this module's current scope."""
    panel = bolivia_monitoring_page.device_status_panel()
    info_lines = panel.info_lines("HVAC / Thermal")
    assert "Temperature Delta = N/A" in info_lines, f"got: {info_lines}"
    assert "Highest Temp = N/A" in info_lines, f"got: {info_lines}"
    assert "No hot-spot indices" in info_lines, f"got: {info_lines}"


def test_hvac_status_pill_is_always_online_for_fractal_site(bolivia_monitoring_page):
    """docs/OF-140.txt Calculo rule for HVAC/Thermal: "Estado: HvacStatus ->
    alarmas termicas -> frescura al final", fallback table: "Online base".
    HvacStatus never arrives (confirmed test_hvac_fields_are_always_na_...
    above), so the only way this card could escalate past "Online" is via
    a real thermal alarm. Confirmed 2026-09-07 against
    docs/fractal-alarms-coverage-open-by-id 1.md: the ENTIRE "HVAC / Safety
    / Environment" alarm category (#61-#65, #67) is NO CUBIERTO for
    Fractal -- including explicit confirmation that the one bit that
    exists in the wire (PCS alarm word 18 bit0 "ambient_temp_too_high")
    is NOT wired to any active alarm rule ("usarlo seria un proxy
    inventado -> no se puede activar"). With nothing able to escalate it,
    and BOLIVIA's telemetry fresh, this card's status is a guaranteed
    "Online" -- unlike the other 5 cards, which DO have real, active alarm
    paths (e.g. EMS IPC & Gateway's Fault correlates with alarm #52
    EMS-PCS Comm Lost, confirmed CUBIERTO and observed firing on BOLIVIA),
    so those are intentionally NOT tested as deterministic facts here."""
    panel = bolivia_monitoring_page.device_status_panel()
    assert panel.status("HVAC / Thermal").lower() == "online"


@pytest.mark.xfail(
    strict=True,
    reason="Design gap, confirmed by the developer as not accounted for: "
           "when NEITHER the direct field (HvacStatus) NOR its alarm "
           "fallback (#61-70, 0% coverage for Fractal) can ever produce a "
           "real signal, defaulting to 'Online' misrepresents 'we never "
           "had visibility' as 'confirmed healthy'. A distinct 'No Data' "
           "state is needed for a subsystem that can never be monitored "
           "through this channel, for any manufacturer.")
def test_hvac_status_pill_should_show_no_data_not_online_for_fractal_site(bolivia_monitoring_page):
    """Companion to test_hvac_status_pill_is_always_online_for_fractal_site
    (kept, still passing -- documents that "Online" DOES match today's
    literal spec/fallback text). This test instead captures what the pill
    SHOULD say: HVAC is the only one of the 6 cards where BOTH of its
    documented data sources (HvacStatus directly, or HVAC alarms as
    fallback) are 100% unreachable for Fractal -- confirmed via
    docs/fractal-alarms-coverage-open-by-id 1.md, the entire #61-70
    category is NO CUBIERTO. Unlike the other 5 cards (which each have at
    least one real, active alarm path -- e.g. #51/#52/#53 Comm Lost, #34-49
    PCS faults), HVAC has zero way to ever confirm health, so "Online"
    here is a default masking total blindness, not a checked-and-healthy
    result. It should show a distinct "No Data" state instead."""
    panel = bolivia_monitoring_page.device_status_panel()
    assert panel.status("HVAC / Thermal").lower() == "no data", (
        "HVAC has zero possible data source for Fractal (neither HvacStatus "
        "nor any HVAC alarm can ever arrive) -- the pill should honestly "
        "show 'No Data', not default to 'Online' as if health were verified")


@pytest.mark.skip(
    reason="Blocked on simulator telemetry-gap injection (deferred to the "
           "alarms-testing phase, per user decision 2026-09-08): "
           "docs/DeviceStatusPanel.md's freshness rule (>5x sampling "
           "interval -> Fault) applies to PCS/Inverter, HVAC, EMS IPC & "
           "Gateway, Meter/Grid, and Network/Comm Path -- if telemetry "
           "genuinely stops arriving (not 'never existed', like HVAC "
           "above, but 'was arriving, then stopped'), these cards escalate "
           "to Fault, which is the same design flaw as HVAC's default: "
           "assuming the worst (Fault) when the truth is just 'we lost "
           "visibility' is as dishonest as assuming the best (Online). "
           "The correct pill in that state is also 'No Data', not Fault. "
           "This can't be verified live without pausing/injecting the "
           "simulator's telemetry for one subsystem -- write this test for "
           "real once that control exists.")
def test_cards_show_no_data_not_fault_when_telemetry_goes_stale(bolivia_monitoring_page):
    pass


# ---------------------------------------------------------------------------
# Engineering ground-truth check for Battery/BMS -- NOT "does the pill match
# the documented SysStatus formula" (that formula IS the design gap), and not
# just "does it match while operating normally" either. The real root cause
# is deeper than a wrong mapping table:
#
# 1. Fractal's wire protocol has NO field anywhere that represents actual BMS
#    health -- no cell voltage, no per-rack telemetry, no BMS-specific fault
#    bit (confirmed against docs/GUIA_CONSUMO_PROTO_FRACTAL.md's full
#    EmuStatus field table and fractal_addressing_map.py). The only things
#    Fractal sends near this card are site-level aggregates (system_soc_pct,
#    system_soh_pct) and station_state -- which describes what the WHOLE
#    STATION is doing (standby/charging/discharging), not the battery bank's
#    health. It is the wrong signal to be driving this pill at all.
# 2. The 10 RACK-level `emsdevices.Device` rows configured for BOLIVIA (a
#    Fractal site) are DATA-configuration fakes, not live telemetry sources
#    -- confirmed via direct DB query 2026-09-07/08 -- since Fractal
#    structurally can never report rack-level data through this channel.
#    Whatever "count racks in Fault/Warning" fallback logic exists in
#    DeviceStatusPanelService.cs has 10 phantom candidates permanently
#    starved of telemetry to reason about, for a site that should have zero
#    rack devices configured in the first place.
# 3. Result: docs/DeviceStatusPanel.md's own Fractal StationState -> SysStatus
#    table maps EVERY StationState to SysStatus 2/3/4/null, which all render
#    as Warning (SysStatus=1 is the only value that renders Online, and no
#    Fractal state ever produces it) -- so a station that is
#    STANDBY/HOT_STANDBY/CHARGING/DISCHARGING (operating normally, not
#    starting up or deliberately off) always shows Warning, with zero
#    dependency on whether the battery has an actual problem.
#
# Confirmed 2026-09-07/08 this isn't offset by a real per-rack alarm hiding
# behind it either: BOLIVIA's 10 EMU status words and 10 EMU alarm words all
# read exactly 0x0000 (no real alarms anywhere).
#
# A real electrical engineer, knowing Fractal genuinely has no BMS-specific
# telemetry channel and that the configured racks are fake, would expect this
# card to honestly show "no BMS telemetry" or, at minimum, Online while the
# station operates normally with zero real alarms -- NOT a Warning fabricated
# from an unrelated operating-mode field plus phantom rack rows. This is the
# expected, correct engineering behavior -- marked xfail(strict=True) because
# it currently, genuinely fails: if it ever starts passing, that's a real fix
# landing (mapping corrected and/or fake racks removed) and this test should
# be promoted to a plain assertion (strict=True makes pytest flag that
# transition loudly instead of silently going green).
# ---------------------------------------------------------------------------

ENGINEERING_EXPECTED_ONLINE_STATION_STATES = {
    "STANDBY", "HOT_STANDBY", "CHARGING", "DISCHARGING",
}


@pytest.mark.xfail(
    strict=True,
    reason="Design gap (docs/DeviceStatusPanel.md) + data-configuration "
           "defect (10 phantom rack devices for a Fractal site that "
           "structurally can never report rack telemetry): Battery/BMS has "
           "no real BMS-health signal to base its pill on for Fractal, so "
           "it can never show Online while operating normally -- confirmed "
           "with zero real alarms present on BOLIVIA (see comment above).")
def test_battery_bms_status_pill_should_be_online_when_operating_normally(bolivia_monitoring_page):
    panel = bolivia_monitoring_page.device_status_panel()
    try:
        station_state = read_fractal_emu_station_state(SITE_NAME)
    except ConnectionError as e:
        pytest.skip(f"Fractal simulator for {SITE_NAME!r} not reachable: {e}")
    except KeyError as e:
        pytest.skip(str(e))

    if station_state not in ENGINEERING_EXPECTED_ONLINE_STATION_STATES:
        pytest.skip(
            f"station_state={station_state!r} is a startup/shutdown state, "
            f"not one of {ENGINEERING_EXPECTED_ONLINE_STATION_STATES} -- "
            f"outside the scope of this specific claim")

    assert panel.status("Battery / BMS").lower() == "online", (
        f"station_state={station_state!r} (normal operation, zero real "
        f"BMS alarms confirmed on {SITE_NAME}, no genuine BMS telemetry "
        f"channel exists for Fractal, and its 10 configured rack devices "
        f"are phantom/never-reporting) should show Online, not a pill "
        f"fabricated from an unrelated operating-mode field")


@pytest.mark.xfail(
    strict=True,
    reason="CA-09 (docs/OF-140.txt, literal): 'Sitio Fractal puede tener "
           "menos detalle de racks; no se inventan racks' -- BOLIVIA is "
           "Fractal and has 10 RACK-level emsdevices.Device rows configured "
           "(confirmed via direct DB query 2026-09-08), which the user "
           "story explicitly says must not happen.")
def test_fractal_site_has_no_invented_rack_devices(db_conn, bolivia_site_id):
    """Ground truth straight from the DB (not UI/API, which only show the
    DOWNSTREAM symptom of this -- Battery/BMS's "0 racks OK - 11 fault"
    summary line and a "SoC range" missing CA-07's "(site)" suffix). This
    checks the root cause directly: for a Fractal site, no RACK device
    should be registered at all, since Fractal's wire protocol has no
    rack-level telemetry to ever back one with real data."""
    rack_count = count_devices_by_level_code(db_conn, bolivia_site_id, "RACK")
    assert rack_count == 0, (
        f"{SITE_NAME} (Fractal) has {rack_count} RACK device(s) registered "
        f"-- CA-09 says Fractal sites must not have invented racks; these "
        f"can never receive real telemetry through Fractal's wire protocol")


# ---------------------------------------------------------------------------
# Downstream display consequences of the same CA-09 violation above --
# independent of the pill-color bug (that one comes from the SysStatus
# mapping and would persist even with 0 racks, since SysStatus always
# exists for Fractal and never falls through to the racks-based fallback
# -- confirmed against docs/OF-140.txt line 557: "SysStatus -> racks -> 0
# racks = Fault", where the racks branch only applies when SysStatus is
# ABSENT, not merely null-mapped). These two checks are about the RACKS
# SUMMARY TEXT and SOC RANGE FORMAT specifically, both broken by the same
# 10 phantom rack rows, both with an exact literal expected string in
# docs/OF-140.txt's own fallback table (lines 560-566).
# ---------------------------------------------------------------------------

@pytest.mark.xfail(
    strict=True,
    reason="Downstream of CA-09's phantom racks (see "
           "test_fractal_site_has_no_invented_rack_devices), reassessed "
           "against the team lead's confirmed dash-vs-N/A design standard "
           "(see test_structurally_absent_field_shows_dash_not_na): "
           "docs/OF-140.txt's literal fallback text '0 racks OK' has the "
           "same problem as 'N/A' -- it reads as a passed check ('OK') for "
           "a concept (racks) that doesn't apply to Fractal at all, rather "
           "than honestly saying so. With 0 real racks, this line should "
           "read '- (racks not applicable for this manufacturer)', not "
           "'0 racks OK' -- and BOLIVIA's 10 phantom racks currently make "
           "it read '0 racks OK - 11 fault', even further from either.")
def test_battery_bms_racks_summary_shows_dash_for_fractal_site(bolivia_monitoring_page):
    panel = bolivia_monitoring_page.device_status_panel()
    info_lines = panel.info_lines("Battery / BMS")
    racks_summary_line = next((line for line in info_lines if "racks" in line.lower()), None)
    assert racks_summary_line is not None, f"no racks summary line found in: {info_lines}"
    assert racks_summary_line == "- (racks not applicable for this manufacturer)", (
        f"Fractal has no rack-level telemetry at all, so this line should "
        f"honestly say so with a dash, not read like a passed check -- "
        f"got: {racks_summary_line!r}")


@pytest.mark.xfail(
    strict=True,
    reason="Downstream of CA-09's phantom racks (see "
           "test_fractal_site_has_no_invented_rack_devices): CA-07 says "
           "'Si no hay racks pero hay SOC de sitio -> SoC range: X% (site)' "
           "-- BOLIVIA's 10 phantom racks make the panel take the "
           "racks-derived range branch instead ('49.1-49.1%', no "
           "'(site)' suffix).")
def test_battery_bms_soc_range_shows_site_suffix_for_fractal_site(bolivia_monitoring_page):
    panel = bolivia_monitoring_page.device_status_panel()
    info_lines = panel.info_lines("Battery / BMS")
    soc_line = next((line for line in info_lines if line.startswith("SoC range")), None)
    assert soc_line is not None, f"no 'SoC range' line found in: {info_lines}"
    assert "(site)" in soc_line, (
        f"CA-07 (docs/OF-140.txt): a Fractal site with 0 real racks but a "
        f"site-level SOC must show '(site)' in the SoC range line, got: "
        f"{soc_line!r}")


# ---------------------------------------------------------------------------
# Engineering ground-truth check for PCS/Inverter -- same style as
# Battery/BMS above: not "does the pill match the documented PcsEvt1
# formula" (that formula IS the bug), but "does the pill match what an
# electrical engineer would expect given the PCS's real bits".
#
# docs/DeviceStatusPanel.md's PcsEvt1StatusHelper.MapCardStatus decodes the
# status/alarm word using an EPC-oriented bit catalog: bit0=Trip->Warning,
# bit2=Derating->Warning, bit4=IGBT/SCR->Fault, ANY OTHER BIT != 0 ->Fault.
# Fractal's real status_word_1 bit catalog (confirmed against
# omniops-bess-edge/modbus_common/fractal_addressing_map.py's
# PCS_STATUS_WORD_LABELS[1]) is completely different: bit1 ("pcs_run") is
# set whenever the PCS is simply running, and bit7/bit8 flag whether it's
# charging or discharging -- none of these are problems. Since none of
# bit0/bit2/bit4 line up with Fractal's real "running normally" bits, a
# healthy, actively-running PCS (bit1 always set, plus bit7 or bit8) falls
# straight into the generic decoder's "any other bit != 0 -> Fault"
# catch-all -- a false Fault on a perfectly healthy unit.
# ---------------------------------------------------------------------------

@pytest.mark.xfail(
    strict=True,
    reason="Design gap (docs/DeviceStatusPanel.md): PcsEvt1StatusHelper "
           "decodes status_word_1 with an EPC-oriented bit catalog that "
           "doesn't recognize Fractal's real 'running normally' bits "
           "(bit1 pcs_run, bit7/8 charge/discharge status), so they fall "
           "into its 'any other bit -> Fault' catch-all even with zero "
           "real alarms.")
def test_pcs_status_pill_should_be_online_when_running_with_no_real_alarms(bolivia_monitoring_page):
    panel = bolivia_monitoring_page.device_status_panel()
    try:
        for pcs_index in range(len(PCS_BASES)):
            status_word_1 = read_fractal_pcs_status_word_1(SITE_NAME, pcs_index)
            alarm_words = read_fractal_pcs_alarm_words(SITE_NAME, pcs_index)
            set_bits = {bit for bit in range(16) if status_word_1 & (1 << bit)}

            if not set_bits:
                pytest.skip(f"PCS index {pcs_index}: status_word_1=0 (not running) -- outside this claim's scope")
            if not set_bits <= PCS_STATUS_WORD_1_BENIGN_BITS:
                pytest.skip(
                    f"PCS index {pcs_index}: status_word_1={status_word_1:#06x} has "
                    f"bit(s) {set_bits - PCS_STATUS_WORD_1_BENIGN_BITS} outside the "
                    f"known-benign 'running normally' set -- outside this claim's scope")
            if any(alarm_words):
                pytest.skip(
                    f"PCS index {pcs_index}: real alarm word(s) nonzero {alarm_words} -- "
                    f"outside this claim's scope (a real alarm would legitimately justify "
                    f"a non-Online pill)")
    except ConnectionError as e:
        pytest.skip(f"Fractal simulator for {SITE_NAME!r} not reachable: {e}")
    except KeyError as e:
        pytest.skip(str(e))

    assert panel.status("PCS / Inverter").lower() == "online", (
        f"all 3 PCS are running normally (status_word_1 bits within the "
        f"known-benign set) with zero real alarm words set -- the pill "
        f"should show Online, not a false Fault from misreading Fractal's "
        f"'pcs_run'/'charge or discharge status' bits as a fault condition")


@pytest.mark.xfail(
    strict=True,
    reason="Same root cause as test_pcs_status_pill_should_be_online_when_running_with_no_real_alarms "
           "(PcsEvt1StatusHelper's EPC-oriented bit catalog misreads Fractal's real "
           "'running normally' bits as a fault) -- it also corrupts the PCS summary "
           "count, marking all 3 real, healthy PCS units as 'fault'.")
def test_pcs_summary_shows_all_pcs_ok_when_running_with_no_real_alarms(bolivia_monitoring_page):
    """docs/OF-140.txt fallback table (line 592): the PCS summary's "Si no
    hay nada" case is "0 PCS OK" -- but here all 3 PCS genuinely exist and
    have real telemetry (unlike Battery/BMS's phantom racks), so with all 3
    running normally and zero real alarms, the correct summary is "3 PCS
    OK", not "0 PCS OK - 3 fault"."""
    panel = bolivia_monitoring_page.device_status_panel()
    try:
        for pcs_index in range(len(PCS_BASES)):
            status_word_1 = read_fractal_pcs_status_word_1(SITE_NAME, pcs_index)
            alarm_words = read_fractal_pcs_alarm_words(SITE_NAME, pcs_index)
            set_bits = {bit for bit in range(16) if status_word_1 & (1 << bit)}

            if not set_bits or not set_bits <= PCS_STATUS_WORD_1_BENIGN_BITS or any(alarm_words):
                pytest.skip(f"PCS index {pcs_index} isn't in a plain 'running normally, "
                            f"zero alarms' state -- outside this claim's scope")
    except ConnectionError as e:
        pytest.skip(f"Fractal simulator for {SITE_NAME!r} not reachable: {e}")
    except KeyError as e:
        pytest.skip(str(e))

    info_lines = panel.info_lines("PCS / Inverter")
    summary_line = next((line for line in info_lines if "PCS OK" in line), None)
    assert summary_line is not None, f"no PCS summary line found in: {info_lines}"
    assert summary_line == "3 PCS OK", (
        f"all 3 real PCS units are running normally with zero real alarms -- "
        f"expected '3 PCS OK', got: {summary_line!r}")


# ---------------------------------------------------------------------------
# EMS IPC & Gateway
# ---------------------------------------------------------------------------

def test_ems_gateway_heartbeat_is_normal_for_fractal_site_with_fresh_data(bolivia_monitoring_page):
    """docs/OF-140.txt fallback table (line 642-644): Heartbeat = "Fresco y
    (sin latido o latido > 0)" -- fresh data AND (no heartbeat field OR a
    nonzero one) both count as "normal". Fractal's wire protocol has no
    heartbeat field anywhere (confirmed against
    docs/GUIA_CONSUMO_PROTO_FRACTAL.md), so with BOLIVIA's telemetry fresh,
    "normal" is the guaranteed, documented-correct result -- NOT a
    contradiction with Gateway Diagnostics' stricter "Disconnected" (see
    test_communication_status_is_disconnected_for_fractal_site_with_no_heartbeat
    in test_gateway_diagnostics.py): confirmed 2026-09-07 these are two
    deliberately different rules for the same absent field."""
    panel = bolivia_monitoring_page.device_status_panel()
    info_lines = panel.info_lines("EMS IPC & Gateway")
    assert "Heartbeat: normal" in info_lines, f"got: {info_lines}"


def _any_pcs_comm_disconnected():
    """Ground truth for alarm #52 "EMS-PCS Comm Lost" (CUBIERTO for
    Fractal, docs/fractal-alarms-coverage-open-by-id 1.md): reads the EMU's
    real RS485-connected bit for each of the 3 PCS directly from the
    simulator. Shared by the Data path and status pill checks below --
    both are downstream of this SAME real signal, so both close the loop
    from the same simulator read rather than each re-deriving it."""
    return any(
        not read_fractal_emu_pcs_comm_connected(SITE_NAME, pcs_index)
        for pcs_index in range(len(PCS_BASES))
    )


def test_ems_gateway_data_path_matches_simulator_pcs_comm_status(bolivia_monitoring_page):
    """Unlike the other findings in this file, this is expected to PASS --
    confirming "Data path: Fault" is a real, correctly-computed alarm, not
    a bug (the developer's own docs already flag this as the legitimate
    signal for this card, independent of the SysStatus mapping gap the
    pill otherwise shares with Battery/BMS)."""
    try:
        any_disconnected = _any_pcs_comm_disconnected()
    except ConnectionError as e:
        pytest.skip(f"Fractal simulator for {SITE_NAME!r} not reachable: {e}")
    except KeyError as e:
        pytest.skip(str(e))

    panel = bolivia_monitoring_page.device_status_panel()
    info_lines = panel.info_lines("EMS IPC & Gateway")
    data_path_line = next((line for line in info_lines if line.startswith("Data path")), None)
    assert data_path_line is not None, f"no 'Data path' line found in: {info_lines}"

    if any_disconnected:
        assert "Fault" in data_path_line, (
            f"simulator shows a PCS RS485 link Disconnected, but Data path "
            f"doesn't say Fault: {data_path_line!r}")
    else:
        assert "Fault" not in data_path_line, (
            f"simulator shows all 3 PCS RS485 links Connected, but Data "
            f"path still says Fault: {data_path_line!r}")


def test_ems_gateway_status_pill_matches_simulator_pcs_comm_status(bolivia_monitoring_page):
    """Closes the loop simulator -> pill directly (not just simulator ->
    Data path, and separately Data path/pill -> API): docs/OF-140.txt line
    639-640 and docs/OmniOps_Parameter_Mapping_V03 row 20 both say the pill
    must be Fault whenever the data path is Fault. Expected to PASS, same
    real-alarm evidence as test_ems_gateway_data_path_matches_simulator_pcs_comm_status."""
    try:
        any_disconnected = _any_pcs_comm_disconnected()
    except ConnectionError as e:
        pytest.skip(f"Fractal simulator for {SITE_NAME!r} not reachable: {e}")
    except KeyError as e:
        pytest.skip(str(e))

    panel = bolivia_monitoring_page.device_status_panel()
    status = panel.status("EMS IPC & Gateway").lower()
    if any_disconnected:
        assert status == "fault", (
            f"simulator shows a PCS RS485 link Disconnected -- the pill "
            f"should be Fault, got: {status!r}")
    else:
        pytest.skip("all 3 PCS RS485 links Connected on the simulator right now -- "
                     "outside this claim's scope (nothing forces the pill to Fault)")


@pytest.mark.skip(
    reason="Known coverage gap, flagged 2026-09-08: docs/OF-140.txt line "
           "639 says the pill is 'SysStatus + camino -> heartbeat + camino', "
           "and test_ems_gateway_status_pill_matches_simulator_pcs_comm_status "
           "above only proves the Fault branch (comm lost) works, since "
           "that's the only real condition BOLIVIA has shown so far. The "
           "SysStatus component of this formula is the SAME field "
           "(station_state) that's already confirmed broken for Battery/BMS "
           "(defect #12, never reaches SysStatus=1/Online) -- if the PCS "
           "comm path were ever fully healthy (no #52 alarm), this card "
           "might reveal the identical masked bug: Online expected, "
           "Warning shown. Can't be tested live today because BOLIVIA's "
           "PCS comm state can't be forced to 'all connected' without "
           "simulator control -- write this test for real once that "
           "exists (same blocker as test_cards_show_no_data_not_fault_when_telemetry_goes_stale).")
def test_ems_gateway_status_pill_should_be_online_when_data_path_is_healthy(bolivia_monitoring_page):
    pass


def test_ems_gateway_ip_matches_configured_intake_value(bolivia_monitoring_page, db_conn, bolivia_site_id):
    """Ground truth for the "Gateway IP" line: docs/OF-140.txt line 646-648
    documents the fallback order as "Telemetria viva -> intake". Fractal's
    emscommunication."RawBaseData" is confirmed EMPTY for BOLIVIA (no live
    telemetry path populates LocalIp for Fractal), so the real source is
    sites."SiteConfiguration"."GatewayIp" (Intake config), not a fallback
    of last resort. Expected to PASS -- this is the same UI-vs-DB depth
    Gateway Diagnostics' Gateway ID/MAC ID tests don't yet have."""
    configured_ip = get_configured_gateway_ip(db_conn, bolivia_site_id)
    assert configured_ip is not None, f"no SiteConfiguration.GatewayIp row for {SITE_NAME}"

    panel = bolivia_monitoring_page.device_status_panel()
    info_lines = panel.info_lines("EMS IPC & Gateway")
    ip_line = next((line for line in info_lines if line.startswith("Gateway IP")), None)
    assert ip_line is not None, f"no 'Gateway IP' line found in: {info_lines}"
    assert configured_ip in ip_line, (
        f"expected the configured Intake IP {configured_ip!r} in the UI line, got: {ip_line!r}")


def test_ems_gateway_mac_matches_registered_asset_registry_value(bolivia_monitoring_page, db_conn, bolivia_site_id):
    """Ground truth for the "MAC" line: docs/OmniOps_Parameter_Mapping_V03
    says MAC should come from the "Gateway / IPC asset registry" (a real,
    configurable mechanism -- emsdevices."DeviceIdentity", IdentityType
    'MAC_ID' -- NOT a field Fractal's telemetry could ever carry, but also
    NOT structurally impossible to configure, unlike Cell Voltage Delta or
    HVAC). Confirmed 2026-09-08: BOLIVIA's registry entries are themselves
    bad seed data (every device's MAC_ID is a copy of its own DeviceCode,
    e.g. the gateway's MAC_ID is literally "00:00:00:00:00:00" because
    that's its DeviceCode) -- a data-quality problem for someone to fix by
    entering real MAC addresses, same category as the phantom rack devices
    (defect #13), NOT a code defect. This test only confirms the UI/API
    correctly displays whatever IS registered, garbage or not -- expected
    to PASS."""
    registered_macs = get_gateway_mac_ids(db_conn, bolivia_site_id)
    assert registered_macs, f"no GATEWAY MAC_ID identity registered for {SITE_NAME}"

    panel = bolivia_monitoring_page.device_status_panel()
    info_lines = panel.info_lines("EMS IPC & Gateway")
    mac_line = next((line for line in info_lines if line.startswith("MAC")), None)
    assert mac_line is not None, f"no 'MAC' line found in: {info_lines}"
    assert any(mac in mac_line for mac in registered_macs), (
        f"UI's MAC line {mac_line!r} doesn't match any registered value "
        f"{registered_macs} -- the display should pass through whatever "
        f"is registered, correct or not")


# ---------------------------------------------------------------------------
# Meters / CT-PT
#
# Key fact, confirmed against docs/OF-140.txt line 322-325: "Carga real
# (RealLoad)" is NOT in either manufacturer's current snapshot -- "No en
# snapshot EPC/Fractal actual". This is NOT a Fractal-only gap like Cell
# Voltage Delta or HVAC -- "Valid" Tags requires demand + load + freshness
# (docs/OmniOps_Parameter_Mapping_V03 row 25: "'Valid' means the required
# meter points exist and are updating"), and since Load never arrives for
# ANY site, "Valid" is a permanently unreachable target system-wide, not a
# manufacturer-specific defect. Given that, "Partial" (demand + freshness
# present, load absent) is the CORRECT result for Fractal today, not a bug
# -- these tests confirm that, and confirm demand telemetry is genuinely
# real (not the reason Tags falls short).
# ---------------------------------------------------------------------------

def test_meters_demand_telemetry_is_real_on_the_simulator():
    """Ground truth: proves Fractal's meter demand is real, live telemetry
    (not itself missing) -- so "Import / export tags partial" is explained
    entirely by the permanently-absent "carga real" input, not by a second,
    Fractal-specific gap in demand. No UI comparison here: this card shows
    no raw demand number, only the qualitative Tags/Consistency lines."""
    try:
        demand_kw = read_fractal_meter_total_active_power_kw(SITE_NAME)
    except ConnectionError as e:
        pytest.skip(f"Fractal simulator for {SITE_NAME!r} not reachable: {e}")
    except KeyError as e:
        pytest.skip(str(e))
    assert isinstance(demand_kw, float), f"expected a real reading, got: {demand_kw!r}"


def test_meters_import_export_tags_is_always_partial_for_fractal_site(bolivia_monitoring_page):
    """docs/OF-140.txt fallback table (line 660-662): Tags = "Demanda +
    carga + frescura" -- Fractal has demand (real telemetry, see above) and
    freshness, but "carga real" never arrives for ANY site (confirmed
    system-wide, not Fractal-specific). With 2 of 3 required inputs
    present, "Partial" is the correct, expected result -- not "Missing"
    (would imply demand is also absent, which it isn't) and not "Valid"
    (impossible for any site while carga real is unimplemented)."""
    panel = bolivia_monitoring_page.device_status_panel()
    info_lines = panel.info_lines("Meters / CT-PT")
    assert "Import / export tags partial" in info_lines, f"got: {info_lines}"


def test_meters_consistency_requires_review_for_fractal_site(bolivia_monitoring_page):
    """docs/OF-140.txt's fallback table has no explicit row for "carga
    ausente pero PCS/BESS presente" (Fractal's real situation) -- only
    "Sin PCS" and "Sin demanda ni carga" are documented, a genuine spec
    gap, not a code defect. Given that gap, "requires review" (Excel row
    26's "Review" outcome) is a reasonable, honest result: it doesn't
    claim "Aligned" without being able to verify one of the 3 required
    values, unlike Battery/BMS's or PCS/Inverter's false-positive/negative
    bugs. Documented as a passing fact, not a finding to act on."""
    panel = bolivia_monitoring_page.device_status_panel()
    info_lines = panel.info_lines("Meters / CT-PT")
    assert "Demand, load, and BESS throughput requires review" in info_lines, f"got: {info_lines}"


def test_meters_status_pill_is_warning_given_partial_tags_and_review_consistency(bolivia_monitoring_page):
    """docs/DeviceStatusPanel.md: Meter/Grid's status is defined "Solo
    OmniOps (frescura + demanda/carga + tags)" -- no dedicated mode field,
    it's derived from exactly the two inputs already confirmed correct
    above (Tags=Partial, Consistency=Review). Neither input signals a
    confirmed real problem (Fault-worthy) nor a fully healthy state
    (Online-worthy) -- "some data is unverifiable" is the textbook
    definition of Warning, not a miscalculation. Since "carga real" is
    permanently absent system-wide (not just for Fractal), this is a
    guaranteed, structural result for ANY site today, not tied to
    BOLIVIA's current live values."""
    panel = bolivia_monitoring_page.device_status_panel()
    assert panel.status("Meters / CT-PT").lower() == "warning"


# ---------------------------------------------------------------------------
# Design standard (confirmed by the team lead): "N/A" and "-" are not
# interchangeable placeholders.
#   "N/A"  -> the field COULD exist, just isn't available right now
#             (stale, not yet received, temporarily missing).
#   "-"    -> the field structurally can NEVER exist for this manufacturer
#             (not in Fractal's wire protocol at all -- confirmed against
#             docs/GUIA_CONSUMO_PROTO_FRACTAL.md, not just "missing today").
#
# Every field below is confirmed structurally absent from Fractal (same
# evidence already used by this file's other "always dash"/"always N/A"
# tests), so per the lead's standard they should ALL show "-", not "N/A".
# This is ONE scalable, parametrized test rather than one test per field --
# to flag a new field found in a future card (PCS/HVAC/whatever), just add
# a (card_title, field_label) tuple to the list below; no new test function
# needed. `field_label` only needs to be a substring that uniquely
# identifies the line (matches this file's existing `.startswith(...)`
# line-finding convention elsewhere, generalized to `in` since some labels
# aren't at the start of the line).
# ---------------------------------------------------------------------------

FIELDS_THAT_NEVER_ARRIVE_BUT_CURRENTLY_SHOW_NA = [
    ("HVAC / Thermal", "Temperature Delta"),
    ("HVAC / Thermal", "Highest Temp"),
    ("PCS / Inverter", "PCS Setpoint"),
    ("PCS / Inverter", "Charge/Discharge limit"),
]


@pytest.mark.xfail(
    strict=True,
    reason="Design standard confirmed by the team lead: a field that "
           "structurally never arrives for a manufacturer must show '-', "
           "not 'N/A' ('N/A' is reserved for a field that could arrive but "
           "currently hasn't). These fields are confirmed structurally "
           "absent from Fractal's wire protocol but still show 'N/A'.")
@pytest.mark.parametrize("card_title, field_label", FIELDS_THAT_NEVER_ARRIVE_BUT_CURRENTLY_SHOW_NA)
def test_structurally_absent_field_shows_dash_not_na(bolivia_monitoring_page, card_title, field_label):
    panel = bolivia_monitoring_page.device_status_panel()
    info_lines = panel.info_lines(card_title)
    line = next((l for l in info_lines if field_label in l), None)
    assert line is not None, f"no line containing {field_label!r} found in {card_title!r}: {info_lines}"
    assert "N/A" not in line, (
        f"{card_title} / {field_label!r}: this field can never arrive for a "
        f"Fractal site, so it should show '-', not 'N/A' -- got: {line!r}")


def test_pcs_status_pill_shows_fault_when_a_real_critical_pcs_alarm_is_open(bolivia_monitoring_page, db_conn, bolivia_site_id):
    """[PCS-02] Worst-state rollup: when a real CRITICAL (Severity=5) alarm
    is currently open for the PCS/TRANSFORMER_PCS subsystem, the PCS card's
    status pill must show Fault -- the worst-severity rollup case, distinct
    from test_pcs_status_pill_should_be_online_when_running_with_no_real_alarms
    above (which only covers the zero-alarm/Online case). Skips gracefully
    if no CRITICAL PCS alarm happens to be open right now."""
    from shared.datasource.db_source import max_open_alarm_severity_for_subsystem

    worst_severity = max_open_alarm_severity_for_subsystem(db_conn, bolivia_site_id, "TRANSFORMER_PCS")
    if worst_severity != 5:
        pytest.skip(f"no open CRITICAL (Severity=5) PCS alarm right now (worst open severity: {worst_severity!r})")

    panel = bolivia_monitoring_page.device_status_panel()
    assert panel.status("PCS / Inverter").lower() == "fault", (
        f"expected the PCS card's status pill to show Fault given a real open CRITICAL "
        f"PCS alarm, got: {panel.status('PCS / Inverter')!r}")
