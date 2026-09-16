"""Data & Monitoring - Thermal Diagnostics (docs/OF-149.txt): a 3-block,
site-level, ALWAYS-LIVE thermal summary (Cell Temperature Delta, Highest /
Lowest Temp, Average Cell Temp) built from per-string/rack battery
temperature snapshots held in RAM (SiteState / BatteryTelemetryByKey) --
explicitly NOT persisted/historical ("Not a trend; reflects the current
aggregated condition of fresh strings/racks"), and explicitly NOT affected by
the page's 24h/7d/30d range selector (CA-05).

BOLIVIA (Fractal). The HU's own "Sources per protocol" table documents a
real, deliberate gap for Fractal: "Fractal (current phase) -- (no strings or
BMS temps in the mapper) -- Gap: empty panel until string mapping
exists". Confirmed live 2026-09-11: all 3 blocks show "—" for BOLIVIA,
consistent with that documented gap, not a defect -- this suite's job is to
confirm the empty state is handled correctly (CA-09/CA-20: "—", never a
fabricated 0), not to fabricate ground-truth numbers Fractal genuinely
never sends.
"""
import pytest

from framework_api.services.monitoring_service import MonitoringService
from shared.datasource.db_source import get_site_ids

pytestmark = pytest.mark.ui

SITE_NAME = "BOLIVIA"
EXPECTED_BLOCK_TITLES = ["Cell Temperature Delta", "Highest / Lowest Temp", "Average Cell Temp"]
DASH = "—"


@pytest.fixture
def bolivia_monitoring_page(require_omniops, monitoring_page):
    return monitoring_page.select_site(SITE_NAME)


@pytest.fixture(scope="session")
def bolivia_site_id(db_conn):
    return get_site_ids(db_conn, [SITE_NAME])[SITE_NAME]


def test_card_title_and_subtitle(bolivia_monitoring_page):
    """CA-03: subtitle explains strings-for-delta/extremes, average's
    rack fallback, and the ~5s live cadence."""
    thermal = bolivia_monitoring_page.thermal_diagnostics()
    subtitle = thermal.subtitle().lower()
    for word in ("string", "rack", "average"):
        assert word in subtitle, f"expected {word!r} in the subtitle, got: {thermal.subtitle()!r}"


def test_exactly_3_blocks_in_documented_order(bolivia_monitoring_page):
    """CA-06/CA-10/CA-15: exactly these 3 blocks, in this order."""
    thermal = bolivia_monitoring_page.thermal_diagnostics()
    assert thermal.block_titles() == EXPECTED_BLOCK_TITLES


def test_no_time_range_badge_on_this_card(bolivia_monitoring_page):
    """CA-05: "The 24h/7d/30d range does not apply to this panel (always
    live, never historical)" -- unlike Site Power Telemetry/Event Log/Alarm
    History, this card doesn't even show a badge, since the very concept
    of a historical range doesn't apply."""
    thermal = bolivia_monitoring_page.thermal_diagnostics()
    assert thermal.card().locator(".monitoring-time-range-badge").count() == 0, (
        "expected no time-range badge on Thermal Diagnostics -- CA-05 says the range doesn't apply here")


def test_global_time_range_does_not_change_values(bolivia_monitoring_page):
    """CA-05: switching the page's global 24h/7d/30d selector must not
    change this card's values at all (not even visually) -- it's always
    the current live aggregate."""
    thermal = bolivia_monitoring_page.thermal_diagnostics()
    before = thermal.block_titles() and {t: thermal.single_value(t) if t != "Highest / Lowest Temp"
                                          else thermal.highest_lowest_values() for t in thermal.block_titles()}

    bolivia_monitoring_page.select_time_range("Last 7 days")
    bolivia_monitoring_page.page.wait_for_timeout(500)
    after = {t: thermal.single_value(t) if t != "Highest / Lowest Temp"
             else thermal.highest_lowest_values() for t in thermal.block_titles()}
    bolivia_monitoring_page.select_time_range("Last 24 hours")

    assert after == before, (
        f"expected Thermal Diagnostics to be unaffected by the global time range, "
        f"before={before}, after switching to 7D={after}")


def test_fractal_site_shows_dash_not_fabricated_zero(bolivia_monitoring_page):
    """CA-09/CA-20 + the HU's own documented Fractal gap ("no strings or
    BMS temps in the mapper" -- empty panel until string mapping
    exists"): for a Fractal site like BOLIVIA, all 3 blocks must show
    "—", never a fabricated "0.0" -- a real 0.0°C reading would be a
    dangerously wrong signal (implying an impossible battery temperature),
    not just a missing one."""
    thermal = bolivia_monitoring_page.thermal_diagnostics()

    delta_number, delta_unit = thermal.single_value("Cell Temperature Delta")
    assert delta_number == DASH, f"expected Cell Temperature Delta = {DASH!r} for a Fractal site, got {delta_number!r}"
    assert delta_unit == "°C"

    highest_n, highest_u, lowest_n, lowest_u = thermal.highest_lowest_values()
    assert highest_n == DASH and lowest_n == DASH, (
        f"expected Highest/Lowest Temp = {DASH!r}/{DASH!r} for a Fractal site, got {highest_n!r}/{lowest_n!r}")
    assert highest_u == "°C" and lowest_u == "°C"

    avg_number, avg_unit = thermal.single_value("Average Cell Temp")
    assert avg_number == DASH, f"expected Average Cell Temp = {DASH!r} for a Fractal site, got {avg_number!r}"
    assert avg_unit == "°C"


def test_ui_values_match_api_thermal_diagnostics(bolivia_monitoring_page, api_client, bolivia_site_id):
    """True cross-layer ground truth (UI vs API): GET /api/monitoring/summary/{siteId}
    exposes a real thermalDiagnostics object (tempDelta/highestTemp/
    lowestTemp/averageTemp) -- so the UI's "—" isn't just trusted at
    face value, it's checked against the same field the backend itself
    computed. Written to keep working with NO changes the day a site
    starts sending real string/BMS temperature data: null <-> "—" today,
    a real number <-> the same number (1 decimal) whenever the API starts
    returning one. There's no live Fractal simulator source for this data
    (Fractal's own wire protocol never sends per-string BMS temperatures --
    confirmed in docs/GUIA_CONSUMO_PROTO_FRACTAL.md), so a UI-vs-simulator
    leg isn't possible for BOLIVIA specifically -- but the moment a site
    with a real 3rd-layer source exists, adding it here is a single
    `read_..._temp_c(SITE_NAME)` call plugged into the same convergence-
    window helper already used elsewhere in this module (see
    test_telemetry_data_table.py's _wait_for_row_to_match_simulator)."""
    thermal_ui = bolivia_monitoring_page.thermal_diagnostics()
    thermal_api = MonitoringService(api_client).get_monitoring_summary(site_id=bolivia_site_id).thermal_diagnostics

    def _assert_matches(ui_number_str, api_value, label):
        if api_value is None:
            assert ui_number_str == DASH, (
                f"{label}: API has no value (null), expected UI to show {DASH!r}, got {ui_number_str!r}")
        else:
            assert ui_number_str == f"{api_value:.1f}", (
                f"{label}: API value {api_value} disagrees with UI's displayed {ui_number_str!r}")

    delta_number, _ = thermal_ui.single_value("Cell Temperature Delta")
    _assert_matches(delta_number, thermal_api.temp_delta, "Cell Temperature Delta")

    highest_n, _, lowest_n, _ = thermal_ui.highest_lowest_values()
    _assert_matches(highest_n, thermal_api.highest_temp, "Highest Temp")
    _assert_matches(lowest_n, thermal_api.lowest_temp, "Lowest Temp")

    avg_number, _ = thermal_ui.single_value("Average Cell Temp")
    _assert_matches(avg_number, thermal_api.average_temp, "Average Cell Temp")


def test_cell_temperature_delta_is_highlighted_yellow(bolivia_monitoring_page):
    """CA-07: Cell Temperature Delta's value is always shown in yellow,
    regardless of whether it currently has a real number or "—" --
    same "always-yellow" pattern already confirmed for Battery
    Diagnostics' Cell Voltage Delta."""
    thermal = bolivia_monitoring_page.thermal_diagnostics()
    css_class = thermal.value_class("Cell Temperature Delta")
    assert "yellow" in css_class, f"expected a 'yellow' class on Cell Temperature Delta's value, got: {css_class!r}"


def test_highest_lowest_and_average_are_not_highlighted_yellow(bolivia_monitoring_page):
    """Contrast check for the test above: only Cell Temperature Delta is
    documented as highlighted (CA-07) -- the other 2 blocks should NOT
    carry that same yellow class."""
    thermal = bolivia_monitoring_page.thermal_diagnostics()
    for title in ("Highest / Lowest Temp", "Average Cell Temp"):
        css_class = thermal.value_class(title)
        assert "yellow" not in css_class, f"did not expect a 'yellow' class on {title!r}, got: {css_class!r}"


def test_help_text_mentions_documented_calculation_per_block(bolivia_monitoring_page):
    """CA-08/CA-13/CA-16: each block's own help text should explain its
    calculation rule (strings-first, rack fallback for the average only)."""
    thermal = bolivia_monitoring_page.thermal_diagnostics()

    delta_help = thermal.help_text("Cell Temperature Delta").lower()
    assert "string" in delta_help or "tempcdelta" in delta_help or "htempc" in delta_help, (
        f"expected Cell Temperature Delta's help text to reference strings/tempcdelta, got: {delta_help!r}")

    hl_help = thermal.help_text("Highest / Lowest Temp").lower()
    assert "string" in hl_help, f"expected Highest/Lowest Temp's help text to mention strings only, got: {hl_help!r}"

    avg_help = thermal.help_text("Average Cell Temp").lower()
    assert "rack" in avg_help, f"expected Average Cell Temp's help text to mention the rack fallback, got: {avg_help!r}"


def test_highest_lowest_help_text_excludes_racks(bolivia_monitoring_page):
    """CA-11/CA-22: unlike Average Cell Temp, Highest/Lowest Temp's help
    text must NOT claim racks can fill in -- extremes are strings-only,
    with no rack fallback (racks never substitute for missing string
    extremes, per the HU's own "racks no sustituyen extremos ni delta")."""
    thermal = bolivia_monitoring_page.thermal_diagnostics()
    hl_help = thermal.help_text("Highest / Lowest Temp").lower()
    assert "rack" not in hl_help, (
        f"expected Highest/Lowest Temp's help text to say strings-only (no rack fallback), got: {hl_help!r}")
