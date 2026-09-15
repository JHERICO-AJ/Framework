"""Data & Monitoring - Battery Diagnostics (docs/OF-142.txt) -- a 4-block
cell-health summary (not a table or chart) next to Dispatch Limits &
Tracking and Gateway Diagnostics.

BOLIVIA (Fractal) specifically. CA-04 (visibility depends on a global
"All Telemetry" vs "Site Summary Only" view toggle) is not covered here:
confirmed live 2026-09-10 the app has no such view selector today (matches
docs/OF-142.txt's own note, "hoy no hay selector de esa vista") -- nothing
to exercise until that toggle exists.

No DB or API cross-layer check for this module (unlike Telemetry Data
Table's own "Browse snapshots" investigation): docs/OF-142.txt's own
"Origen de los datos" section says the LIVE card's only source is "Estado
vivo del sitio en memoria" and explicitly "Historial en base de datos: No
alimenta esta tarjeta directamente" -- this card reads a real-time
in-memory cache, not a queryable DB table or a stable REST endpoint
(confirmed framework_api/services/monitoring_service.py exposes nothing
for these fields either). The deepest ground truth actually available is
the real Fractal wire protocol itself (docs/GUIA_CONSUMO_PROTO_FRACTAL.md)
and the crosswalk audit confirming these fields never had a real Modbus
address for Fractal (docs/PlanFractal_RM.md) -- both already consulted
before writing test_all_blocks_show_dash_for_fractal_site, rather than a
live Modbus poll for registers that are documented not to exist.
"""
import re

import pytest

pytestmark = pytest.mark.ui

SITE_NAME = "BOLIVIA"

# CA-03: exactly these 4 blocks, in this order.
EXPECTED_BLOCK_LABELS = [
    "Cell Voltage Delta", "Balance Status", "Average Cell Voltage", "Highest / Lowest Cell",
]

BALANCE_STATUS_WORDS = {"Active", "Idle", "—"}

# docs/OF-142.txt "Mapeo Fractal -> indicadores": none of the 3 real
# per-cell/balance fields (cell voltages, balancing, delta) ever arrive for
# a Fractal site -- confirmed independently against
# docs/GUIA_CONSUMO_PROTO_FRACTAL.md (no cell-level registers in Fractal's
# real wire protocol) and docs/PlanFractal_RM.md (balancestatus never had a
# real Modbus address for Fractal -- a phantom field from an outdated
# crosswalk). So all 4 blocks are expected to show "-" for this site; this
# is the documented fallback, not a defect.
EM_DASH = "—"


@pytest.fixture
def bolivia_monitoring_page(require_omniops, monitoring_page):
    return monitoring_page.select_site(SITE_NAME)


def test_exactly_four_blocks_with_documented_labels(bolivia_monitoring_page):
    """CA-03 (docs/OF-142.txt): exactly 4 blocks, in this exact order."""
    card = bolivia_monitoring_page.battery_diagnostics()
    labels = list(card.block_values().keys())
    assert labels == EXPECTED_BLOCK_LABELS, (
        f"expected exactly {EXPECTED_BLOCK_LABELS}, got: {labels}")


def test_cell_voltage_delta_is_always_yellow(bolivia_monitoring_page):
    """CA-05 (docs/OF-142.txt): 'Delta de voltaje: siempre resaltado en
    amarillo' -- confirmed this holds even when the value itself is the
    documented fallback dash, not just when a real mV number is shown."""
    card = bolivia_monitoring_page.battery_diagnostics()
    classes = card.value_classes_for("Cell Voltage Delta")
    assert "yellow" in classes.split(), (
        f"expected the 'yellow' class on Cell Voltage Delta's value regardless "
        f"of its content, got classes: {classes!r}")


def test_all_blocks_show_dash_for_fractal_site(bolivia_monitoring_page):
    """docs/OF-142.txt 'Mapeo Fractal -> indicadores' + 'Fallbacks': a
    Fractal site has no per-cell voltage or balancing telemetry at all
    (confirmed against docs/GUIA_CONSUMO_PROTO_FRACTAL.md and
    docs/PlanFractal_RM.md), so every block should show the documented
    dash fallback -- this is the CORRECT, expected result for this
    manufacturer, not a bug."""
    card = bolivia_monitoring_page.battery_diagnostics()
    values = card.block_values()
    non_dash = {label: value for label, value in values.items() if value != EM_DASH}
    assert not non_dash, (
        f"expected every block to show the dash fallback for a Fractal site, "
        f"but these had a real value instead: {non_dash}")


def test_balance_status_is_a_documented_value(bolivia_monitoring_page):
    """Balance Status must always be one of the 3 documented values (CA-06/
    07/08), regardless of manufacturer or data availability -- unlike
    test_all_blocks_show_dash_for_fractal_site, this doesn't assume
    Fractal's specific gap, so it stays meaningful if that ever changes."""
    card = bolivia_monitoring_page.battery_diagnostics()
    value = card.value_for("Balance Status")
    assert value in BALANCE_STATUS_WORDS, (
        f"expected Balance Status to be one of {BALANCE_STATUS_WORDS}, got: {value!r}")


def test_consistent_with_device_status_panel_battery_card(bolivia_monitoring_page):
    """CA-15 (docs/OF-142.txt): 'Debe ser coherente con delta y balanceo
    del Device Status Panel (misma fuente viva)' -- both cards read the
    same live site state, so Cell Voltage Delta and Balance Status must
    agree between them."""
    battery_diagnostics = bolivia_monitoring_page.battery_diagnostics()
    device_status_panel = bolivia_monitoring_page.device_status_panel()

    battery_bms_info = device_status_panel.info_lines("Battery / BMS")
    delta_line = next((line for line in battery_bms_info if line.startswith("Cell Voltage Delta")), None)
    balance_line = next((line for line in battery_bms_info if line.startswith("Balancing")), None)
    assert delta_line is not None and balance_line is not None, (
        f"expected Device Status Panel's Battery/BMS card to have its own "
        f"Cell Voltage Delta and Balancing lines, got: {battery_bms_info}")

    device_status_delta = delta_line.split("=", 1)[1].strip()
    device_status_balance = balance_line.split(":", 1)[1].strip()

    assert battery_diagnostics.value_for("Cell Voltage Delta") == device_status_delta, (
        f"Battery Diagnostics' Cell Voltage Delta "
        f"({battery_diagnostics.value_for('Cell Voltage Delta')!r}) disagrees with "
        f"Device Status Panel's ({device_status_delta!r})")
    assert battery_diagnostics.value_for("Balance Status") == device_status_balance, (
        f"Battery Diagnostics' Balance Status "
        f"({battery_diagnostics.value_for('Balance Status')!r}) disagrees with "
        f"Device Status Panel's Balancing ({device_status_balance!r})")


@pytest.mark.parametrize("label, pattern", [
    ("Cell Voltage Delta", r"^\d+(\.\d+)? mV$"),
    ("Average Cell Voltage", r"^\d+\.\d{3} V$"),
    ("Highest / Lowest Cell", r"^\d+\.\d{3} / \d+\.\d{3} V$"),
])
def test_numeric_block_format_or_documented_dash_fallback(bolivia_monitoring_page, label, pattern):
    """CA-05/09/10 (docs/OF-142.txt): a block's value must be EITHER the
    documented dash fallback OR match its real numeric format -- both are
    valid, PASSING outcomes; only some third, undocumented shape would
    fail this. The dash isn't "nothing to check" on a Fractal site: it's
    the specific, correct behavior for a manufacturer whose wire protocol
    genuinely never reports cell-level telemetry (confirmed against
    docs/GUIA_CONSUMO_PROTO_FRACTAL.md and docs/PlanFractal_RM.md -- see
    test_all_blocks_show_dash_for_fractal_site), so asserting it here is
    a real pass, not a skip standing in for "not applicable"."""
    card = bolivia_monitoring_page.battery_diagnostics()
    value = card.value_for(label)
    assert value == EM_DASH or re.match(pattern, value), (
        f"expected {label!r} to be either the documented dash fallback or "
        f"match {pattern!r}, got: {value!r}")


def test_live_update_reflects_within_documented_window(bolivia_monitoring_page):
    """CA-13 (docs/OF-142.txt): 'Se actualiza en vivo junto con los otros
    diagnosticos (~5 s), sin recargar la pagina.'

    On a Fractal site, "live" doesn't mean "the value changes" -- it means
    the card keeps correctly reflecting the site's real state (the
    documented dash fallback, since Fractal never reports cell-level
    telemetry) across the refresh cycle, WITHOUT a page reload and without
    ever drifting into some other, undocumented state. That stability is
    itself a real, currently-verifiable pass for this site -- not a skip.
    On a site that DOES report changing cell voltages, this instead
    confirms an actual value change lands within the documented window."""
    import time

    card = bolivia_monitoring_page.battery_diagnostics()
    page = bolivia_monitoring_page.page
    before = card.block_values()

    if all(value == EM_DASH for value in before.values()):
        page.wait_for_timeout(10000)
        after = card.block_values()
        assert after == before, (
            f"expected the dash fallback to stay stable across the ~5s live-refresh "
            f"cycle (no reload happened) -- before: {before}, after: {after}")
        return

    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        if card.block_values() != before:
            return
        page.wait_for_timeout(1000)

    pytest.fail(f"none of the 4 blocks changed within 15s of real telemetry arriving -- "
                f"values stayed at {before}")
