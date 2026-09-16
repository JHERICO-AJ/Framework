"""Data & Monitoring - Dispatch Limits & Tracking (docs/OF-145.txt) -- a
6-block dispatch/setpoint/DC-bus summary next to Battery Diagnostics and
Gateway Diagnostics.

BOLIVIA (Fractal) specifically. CA-04 (visibility depends on a global
"All Telemetry" vs "Site Summary Only" view toggle) is not covered here:
confirmed live 2026-09-10 the app has no such view selector today (matches
docs/OF-145.txt's own note, "hoy no hay selector de esa vista") -- same
untestable-CA pattern already confirmed for Battery Diagnostics.

No DB cross-layer check for this module: docs/OF-145.txt's own "Origen de
los datos" section says "Historial en base de datos: No alimenta esta
tarjeta directamente" -- same in-memory-cache pattern already confirmed
for Battery Diagnostics.

There IS a real API layer, though (unlike Battery Diagnostics, which truly
has nothing exposed): GET /api/monitoring/summary/{site_id}'s
`dispatchDiagnostics` object (confirmed 2026-09-10 via a raw payload
capture for BOLIVIA -- chargeLimitA/dischargeLimitA/pcsSetpoint/
actualPcsPower/dcBusVoltage/dcBusCurrent/timestamp) is the same in-memory
site state the UI reads, one hop earlier. Modeled as
DispatchDiagnostics in framework_api/models/monitoring_summary.py.

Real, deep ground truth IS available for "Actual PCS Power" specifically:
docs/OF-145.txt's own Calculo rule ("suma de todos los inversores
individuales del sitio") is identical to Device Status Panel's PCS/Inverter
"Actual" rule (docs/OF-140.txt), and read_fractal_site_total_kw
(shared/datasource/fractal_modbus_source.py) already implements exactly
that sum -- reused here via the same convergence-window technique as
test_pcs_actual_power_matches_simulator_pcs_sum
(tests/ui/monitoring/test_device_status_panel.py), since a single
point-in-time snapshot comparison against continuously-changing Live
telemetry is known to be unreliable (confirmed noisy on this exact value
during initial exploration -- a ~764 kW single-snapshot gap that this
window technique is what actually resolves, one way or another).

DC Bus Voltage/Current (dc_voltage_v/dc_current_a, EmuStatus fields 17/18
per docs/GUIA_CONSUMO_PROTO_FRACTAL.md) DO have real ground-truth checks
below: their Modbus register offsets (33 and 35 off EMU_BASE, confirmed
2026-09-10 directly against omniops-bess-edge's real
modbus_common/fractal_addressing_map.py EMU_FIELDS -- not guessed) are now
implemented as read_fractal_emu_dc_current_a/read_fractal_emu_dc_voltage_v
in shared/datasource/fractal_modbus_source.py. Both correspond to
docs/OF-145.txt's Calculo preference order #1 for these two blocks
("Voltaje y corriente del banco/sitio, mensaje del gateway") -- the
EMU-level site aggregate this simulator reads directly.
"""
import time

import pytest

from shared.config.settings import TOL_ABS_KW
from shared.datasource.db_source import get_site_ids
from shared.datasource.fractal_modbus_source import (
    read_fractal_site_total_kw, read_fractal_emu_dc_current_a, read_fractal_emu_dc_voltage_v,
)

pytestmark = pytest.mark.ui

SITE_NAME = "BOLIVIA"

# CA-03: exactly these 6 blocks, in this order.
EXPECTED_BLOCK_LABELS = [
    "Charge Limit", "Discharge Limit", "PCS Setpoint",
    "Actual PCS Power", "DC Bus Voltage", "DC Bus Current",
]

EM_DASH = "—"

# Same convergence-window constants as Device Status Panel's own PCS Actual
# power check (tests/ui/monitoring/test_device_status_panel.py) -- kept in
# sync deliberately, since both read the exact same simulator function.
POWER_HISTORY_DURATION_S = 120
POWER_HISTORY_INTERVAL_S = 3
POWER_HISTORY_MAX_LATENCY_S = 300

# DC Bus Voltage/Current tolerances: current can swing as fast/large as
# power (P = I x V), so it gets the same generous window as TOL_ABS_KW;
# voltage on a healthy DC bus is comparatively stable, so a tighter
# tolerance still won't mask a real bug.
TOL_ABS_A = 50.0
TOL_ABS_V = 5.0


@pytest.fixture
def bolivia_monitoring_page(require_omniops, monitoring_page):
    return monitoring_page.select_site(SITE_NAME)


@pytest.fixture(scope="session")
def bolivia_site_id(db_conn):
    return get_site_ids(db_conn, [SITE_NAME])[SITE_NAME]


@pytest.fixture
def api_dispatch(monitoring_service, bolivia_site_id):
    return monitoring_service.get_monitoring_summary(site_id=bolivia_site_id).dispatch_diagnostics


def _wait_for_value_to_match_simulator(label, read_layer_value, unit_suffix, read_simulator_value,
                                        tolerance, sleep_fn, layer_name="UI",
                                        duration_s=POWER_HISTORY_DURATION_S,
                                        interval_s=POWER_HISTORY_INTERVAL_S,
                                        max_latency_s=POWER_HISTORY_MAX_LATENCY_S):
    """Same convergence-window technique as
    test_pcs_actual_power_matches_simulator_pcs_sum (test_device_status_panel.py):
    the other layer's value at test start reflects an earlier ingestion
    cycle than "right now", so build a growing history of simulator samples
    and re-read that layer each iteration until one matches within
    `tolerance`. `read_layer_value` returns a raw string ("-4009.9 kW") for
    the UI or a bare float for the API -- unit_suffix is only stripped when
    present, so both work through the same helper. `sleep_fn(seconds)` lets
    UI callers pump Playwright's event loop (page.wait_for_timeout) while
    API callers just time.sleep."""
    history = []  # [(wall_clock_time, value), ...]
    elapsed = 0
    while elapsed <= duration_s:
        try:
            sim_value = read_simulator_value()
        except ConnectionError as e:
            pytest.skip(f"Fractal simulator for {SITE_NAME!r} not reachable: {e}")
        except KeyError as e:
            pytest.skip(str(e))
        history.append((time.monotonic(), sim_value))

        raw = read_layer_value()
        assert raw not in (None, "N/A", EM_DASH), (
            f"expected a real numeric value for {label!r} on a Fractal site "
            f"(docs/OF-145.txt: Fractal DOES feed this block), got: {raw!r}")
        layer_value = float(raw.replace(unit_suffix, "").strip()) if isinstance(raw, str) else float(raw)

        match = next((t for t, v in history if abs(v - layer_value) <= tolerance), None)
        if match is not None:
            latency_s = time.monotonic() - match
            print(f"\n[{SITE_NAME}] Measured {layer_name}->simulator latency for "
                  f"{label!r}: ~{latency_s:.1f}s ({layer_name}={layer_value}{unit_suffix} "
                  f"matched a simulator sample from {latency_s:.1f}s ago)")
            assert latency_s <= max_latency_s, (
                f"matched, but {latency_s:.1f}s is beyond the sanity ceiling "
                f"of {max_latency_s}s -- likely a stale/stuck value")
            return

        sleep_fn(interval_s)
        elapsed += interval_s

    pytest.fail(
        f"[{SITE_NAME}] Dispatch Limits & Tracking's {label!r} ({layer_name}) never "
        f"matched any of the simulator's last {duration_s}s of samples "
        f"({len(history)} samples, within {tolerance}{unit_suffix}) -- either "
        f"latency exceeds that window, or the calculation is wrong. "
        f"Simulator samples: {[v for _, v in history]}")


def test_exactly_six_blocks_with_documented_labels(bolivia_monitoring_page):
    """CA-03 (docs/OF-145.txt): exactly 6 blocks, in this exact order."""
    card = bolivia_monitoring_page.dispatch_limits_tracking()
    labels = list(card.block_values().keys())
    assert labels == EXPECTED_BLOCK_LABELS, (
        f"expected exactly {EXPECTED_BLOCK_LABELS}, got: {labels}")


@pytest.mark.parametrize("label, pattern", [
    ("Charge Limit", r"^\d+\.\d A$"),
    ("Discharge Limit", r"^\d+\.\d A$"),
    ("PCS Setpoint", r"^-?\d+\.\d kW$"),
    ("Actual PCS Power", r"^-?\d+\.\d kW$"),
    ("DC Bus Voltage", r"^\d+\.\d V$"),
    ("DC Bus Current", r"^-?\d+\.\d A$"),
])
def test_numeric_block_format_or_documented_fallback(bolivia_monitoring_page, label, pattern):
    """CA-05 through CA-11 (docs/OF-145.txt): each block's value must be
    EITHER a real value in its documented 1-decimal unit format OR one of
    the two documented fallback placeholders (N/A -- literal spec text --
    or the dash, per the team lead's confirmed design standard for a field
    that structurally can never arrive; see
    test_structurally_absent_field_shows_dash_not_na in
    test_device_status_panel.py for that standard's precedent). Both
    fallbacks are accepted here since which one is "correct" per block is
    exercised separately below, by the dedicated defect test."""
    import re

    card = bolivia_monitoring_page.dispatch_limits_tracking()
    value = card.value_for(label)
    assert value in ("N/A", EM_DASH) or re.match(pattern, value), (
        f"expected {label!r} to be N/A, {EM_DASH!r}, or match {pattern!r}, got: {value!r}")


# ---------------------------------------------------------------------------
# Same root cause, same confirmed design standard as Device Status Panel's
# already-open defect (test_structurally_absent_field_shows_dash_not_na in
# test_device_status_panel.py): Charge Limit, Discharge Limit and PCS
# Setpoint structurally never arrive for a Fractal site (ccl_a/dcl_a/no
# setpoint-equivalent field anywhere in docs/GUIA_CONSUMO_PROTO_FRACTAL.md
# or docs/PlanFractal_RM.md's real field-mapping tables), so per the lead's
# standard they should show "-", not "N/A" -- same bug, new card.
# ---------------------------------------------------------------------------

FIELDS_THAT_NEVER_ARRIVE_BUT_CURRENTLY_SHOW_NA = [
    "Charge Limit", "Discharge Limit", "PCS Setpoint",
]


@pytest.mark.xfail(
    strict=True,
    reason="Design standard confirmed by the team lead: a field that "
           "structurally never arrives for a manufacturer must show '-', "
           "not 'N/A'. Same confirmed root cause as Device Status Panel's "
           "PCS Setpoint / Charge-Discharge limit defect (ccl_a/dcl_a/"
           "setpoint absent from Fractal's wire protocol) -- these 3 "
           "blocks on Dispatch Limits & Tracking read the same underlying "
           "site state and are expected to still show 'N/A'.")
@pytest.mark.parametrize("label", FIELDS_THAT_NEVER_ARRIVE_BUT_CURRENTLY_SHOW_NA)
def test_structurally_absent_field_shows_dash_not_na(bolivia_monitoring_page, label):
    card = bolivia_monitoring_page.dispatch_limits_tracking()
    value = card.value_for(label)
    assert value != "N/A", (
        f"{label}: this field can never arrive for a Fractal site, so it "
        f"should show '-', not 'N/A' -- got: {value!r}")


def test_actual_pcs_power_matches_simulator_pcs_sum(bolivia_monitoring_page):
    """True cross-layer ground truth, bypassing the API entirely: per
    docs/OF-145.txt's Calculo rule for Actual PCS Power -- "Suma de todos
    los inversores individuales del sitio" -- identical to Device Status
    Panel's own PCS/Inverter "Actual" rule (docs/OF-140.txt), and CA-16
    ("Setpoint, potencia real y limites deben ser coherentes con la
    tarjeta PCS del Device Status Panel -- misma fuente") confirms both
    cards are expected to read the exact same underlying value.
    read_fractal_site_total_kw() already implements that sum (see
    test_pcs_actual_power_matches_simulator_pcs_sum in
    test_device_status_panel.py) -- reused here rather than duplicated.

    Same convergence-window technique as that test: the UI's value at test
    start reflects an earlier ingestion cycle than "right now", so build a
    growing history of simulator samples and re-read the UI each iteration
    until one matches within TOL_ABS_KW."""
    card = bolivia_monitoring_page.dispatch_limits_tracking()
    _wait_for_value_to_match_simulator(
        "Actual PCS Power", lambda: card.value_for("Actual PCS Power"), " kW",
        read_simulator_value=lambda: read_fractal_site_total_kw(SITE_NAME),
        tolerance=TOL_ABS_KW, sleep_fn=lambda s: card.page.wait_for_timeout(s * 1000),
        layer_name="UI")


def test_dc_bus_current_matches_simulator(bolivia_monitoring_page):
    """True cross-layer ground truth: docs/OF-145.txt's Calculo rule for DC
    Bus Current, preference order #1, is "Corriente del banco/sitio
    (mensaje del gateway)" -- exactly EmuStatus.dc_current_a, read here via
    read_fractal_emu_dc_current_a (offset 33 off EMU_BASE, confirmed
    2026-09-10 directly against omniops-bess-edge's real
    fractal_addressing_map.py, not guessed)."""
    card = bolivia_monitoring_page.dispatch_limits_tracking()
    _wait_for_value_to_match_simulator(
        "DC Bus Current", lambda: card.value_for("DC Bus Current"), " A",
        read_simulator_value=lambda: read_fractal_emu_dc_current_a(SITE_NAME),
        tolerance=TOL_ABS_A, sleep_fn=lambda s: card.page.wait_for_timeout(s * 1000),
        layer_name="UI")


def test_dc_bus_voltage_matches_simulator(bolivia_monitoring_page):
    """True cross-layer ground truth: docs/OF-145.txt's Calculo rule for DC
    Bus Voltage, preference order #1, is "Voltaje del banco/sitio (mensaje
    del gateway)" -- exactly EmuStatus.dc_voltage_v, read here via
    read_fractal_emu_dc_voltage_v (offset 35 off EMU_BASE, UINT32, confirmed
    2026-09-10 directly against omniops-bess-edge's real
    fractal_addressing_map.py, not guessed)."""
    card = bolivia_monitoring_page.dispatch_limits_tracking()
    _wait_for_value_to_match_simulator(
        "DC Bus Voltage", lambda: card.value_for("DC Bus Voltage"), " V",
        read_simulator_value=lambda: read_fractal_emu_dc_voltage_v(SITE_NAME),
        tolerance=TOL_ABS_V, sleep_fn=lambda s: card.page.wait_for_timeout(s * 1000),
        layer_name="UI")


# ---------------------------------------------------------------------------
# API layer (GET /api/monitoring/summary/{site_id}'s dispatchDiagnostics) --
# confirmed 2026-09-10 this card DOES have a real API path, unlike Battery
# Diagnostics. Same convergence-window technique, reading the API instead
# of the UI, to confirm the API itself (not just what's painted on screen)
# is computing these 3 values correctly.
# ---------------------------------------------------------------------------

def test_api_actual_pcs_power_matches_simulator(require_omniops, monitoring_service, bolivia_site_id):
    """Same ground truth as test_actual_pcs_power_matches_simulator_pcs_sum,
    one layer earlier: confirms dispatchDiagnostics.actualPcsPower itself
    (not the UI's rendering of it) matches the simulator's PCS-sum."""
    _wait_for_value_to_match_simulator(
        "Actual PCS Power",
        lambda: monitoring_service.get_monitoring_summary(site_id=bolivia_site_id)
            .dispatch_diagnostics.actual_pcs_power,
        "",
        read_simulator_value=lambda: read_fractal_site_total_kw(SITE_NAME),
        tolerance=TOL_ABS_KW, sleep_fn=time.sleep, layer_name="API")


def test_api_dc_bus_current_matches_simulator(require_omniops, monitoring_service, bolivia_site_id):
    _wait_for_value_to_match_simulator(
        "DC Bus Current",
        lambda: monitoring_service.get_monitoring_summary(site_id=bolivia_site_id)
            .dispatch_diagnostics.dc_bus_current,
        "",
        read_simulator_value=lambda: read_fractal_emu_dc_current_a(SITE_NAME),
        tolerance=TOL_ABS_A, sleep_fn=time.sleep, layer_name="API")


def test_api_dc_bus_voltage_matches_simulator(require_omniops, monitoring_service, bolivia_site_id):
    _wait_for_value_to_match_simulator(
        "DC Bus Voltage",
        lambda: monitoring_service.get_monitoring_summary(site_id=bolivia_site_id)
            .dispatch_diagnostics.dc_bus_voltage,
        "",
        read_simulator_value=lambda: read_fractal_emu_dc_voltage_v(SITE_NAME),
        tolerance=TOL_ABS_V, sleep_fn=time.sleep, layer_name="API")


@pytest.mark.parametrize("label, unit_suffix, api_field", [
    ("Actual PCS Power", " kW", "actual_pcs_power"),
    ("DC Bus Current", " A", "dc_bus_current"),
    ("DC Bus Voltage", " V", "dc_bus_voltage"),
])
def test_ui_matches_api(bolivia_monitoring_page, api_dispatch, label, unit_suffix, api_field):
    """UI and API read the exact same in-memory site state one hop apart,
    so -- unlike the simulator comparisons above, which need a convergence
    window to absorb ingestion latency -- these two should already agree
    at any single instant, within a small tolerance for the UI's own
    ~5s render cycle vs. the API request landing a beat later."""
    card = bolivia_monitoring_page.dispatch_limits_tracking()
    ui_text = card.value_for(label)
    assert ui_text not in (None, "N/A", EM_DASH), f"expected a real value for {label!r}, got: {ui_text!r}"
    ui_value = float(ui_text.replace(unit_suffix, "").strip())

    api_value = getattr(api_dispatch, api_field)
    assert api_value is not None, (
        f"expected a real value for dispatchDiagnostics.{api_field}, got None -- "
        f"UI shows {ui_text!r}")

    tolerance = {"kW": TOL_ABS_KW, "A": TOL_ABS_A, "V": TOL_ABS_V}[unit_suffix.strip()]
    assert abs(ui_value - api_value) <= tolerance, (
        f"{label}: UI={ui_value}{unit_suffix} disagrees with API "
        f"dispatchDiagnostics.{api_field}={api_value} by more than {tolerance}")


def test_consistent_with_device_status_panel_pcs_card(bolivia_monitoring_page):
    """CA-16 (docs/OF-145.txt): 'Setpoint, potencia real y limites deben
    ser coherentes con la tarjeta PCS del Device Status Panel (misma
    fuente)' -- both cards read the same live site state, so Actual PCS
    Power must agree between them. PCS Setpoint/limits are excluded from
    this direct-equality check: Device Status Panel's PCS/Inverter card
    renders them with its own Available/Limited/Unavailable framing
    (docs/OF-145.txt "Diferencias con otras pantallas"), not the same
    plain N/A-or-value text this card uses, so a literal string compare
    would conflate a real formatting difference with an actual data
    disagreement."""
    from shared.utils.parsing import parse_kw

    dispatch = bolivia_monitoring_page.dispatch_limits_tracking()
    device_status_panel = bolivia_monitoring_page.device_status_panel()

    pcs_lines = device_status_panel.info_lines("PCS / Inverter")
    actual_line = next((line for line in pcs_lines if line.startswith("Actual")), None)
    assert actual_line is not None, f"no 'Actual' line found in: {pcs_lines}"
    device_status_actual_kw = parse_kw(actual_line)
    assert device_status_actual_kw is not None, f"couldn't parse a kW value from: {actual_line!r}"

    dispatch_actual_text = dispatch.value_for("Actual PCS Power")
    assert dispatch_actual_text not in (None, "N/A", EM_DASH), (
        f"expected a real numeric value for Actual PCS Power, got: {dispatch_actual_text!r}")
    dispatch_actual_kw = float(dispatch_actual_text.replace(" kW", "").strip())

    assert abs(dispatch_actual_kw - device_status_actual_kw) <= TOL_ABS_KW, (
        f"Dispatch Limits & Tracking's Actual PCS Power ({dispatch_actual_kw} kW) "
        f"disagrees with Device Status Panel's PCS/Inverter Actual "
        f"({device_status_actual_kw} kW) by more than {TOL_ABS_KW} kW -- CA-16 "
        f"requires both to read the same source")


def test_live_update_reflects_within_documented_window(bolivia_monitoring_page):
    """CA-12/13 (docs/OF-145.txt): 'Se actualiza en vivo (~5 s) con el
    resto de diagnosticos, sin recargar' and 'Si un valor ya se vio y
    llega vacio -> se mantiene el ultimo bueno (no parpadea a N/A)'.

    Same technique already established for Battery Diagnostics: for a
    live-changing value (Actual PCS Power on a Fractal site always has
    one, per docs/OF-145.txt's own Fractal mapping table), confirm a
    change lands within the documented window. For any block still stuck
    on a fallback placeholder, confirm CA-13's "sticky, no flicker"
    behavior instead -- both are real, currently-verifiable outcomes, not
    a skip."""
    card = bolivia_monitoring_page.dispatch_limits_tracking()
    page = card.page
    before = card.block_values()

    live_labels = [label for label, value in before.items() if value not in ("N/A", EM_DASH)]
    sticky_labels = [label for label in before if label not in live_labels]

    if not live_labels:
        page.wait_for_timeout(10000)
        after = card.block_values()
        assert after == before, (
            f"expected the fallback placeholders to stay stable (sticky, no "
            f"flicker per CA-13) across the ~5s live-refresh cycle -- "
            f"before: {before}, after: {after}")
        return

    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        after = card.block_values()
        if any(after[label] != before[label] for label in live_labels):
            for label in sticky_labels:
                assert after[label] == before[label], (
                    f"CA-13: {label!r} should stay sticky on its last good "
                    f"value (or documented fallback) even while other blocks "
                    f"update -- before: {before[label]!r}, after: {after[label]!r}")
            return
        page.wait_for_timeout(1000)

    pytest.fail(f"none of {live_labels} changed within 15s of real telemetry "
                f"arriving -- values stayed at { {l: before[l] for l in live_labels} }")
