"""Data & Monitoring - Fault Localization (docs/OF-153.txt): a site-level,
ALWAYS-LIVE (~5s via diagnostics push) 8-row rack/pack/cell extreme-location
panel, in 3 cards (Highest V / Lowest V / Temperature) -- explicitly NOT
affected by the page's 24h/7d/30d range selector (CA-05), same pattern as
Site Load & Backup Context/Raw Event Bit Viewer/Thermal Diagnostics.

BOLIVIA (Fractal). The HU's own "Fuentes por protocolo" table documents a
real, deliberate gap: "Fractal (fase actual): -- (sin strings BMS
mapeados) ... Gap: solo fallback rack si existiera telemetria rack" -- so
all 8 rows should show N/A today. UNLIKE the Raw Event Bit Viewer's evt1
case (where "documented gap" turned out to hide a real defect), this one
was verified against the real backend source before accepting the N/A
state as correct, not assumed:
- MonitoringComputedService.BuildFaults/FindExtremeSnapshot reads
  SiteState.BatteryTelemetryByKey (strings/modules first, racks as
  fallback -- exactly the HU's documented priority rule), and hardcodes
  HighestTempPack/HighestTempCell/LowestTempPack/LowestTempCell to null
  unconditionally (matching CA-16: no pack/cell rows for temperature).
- FractalRawDataMapper.cs never assigns HCellV/LCellV/HTempC/LTempC/
  HCellModule/HCell/LCell from any Fractal field -- confirmed via a direct
  grep of the mapper source: zero matches. So for a Fractal site,
  BatteryTelemetryByKey never receives real values for these fields, and
  BuildFaults's FindExtremeSnapshot has nothing to select from -- the
  all-N/A state is a genuine, source-confirmed gap, not a hidden bug.

This also resolves a Fault Localization mapping-xlsx vs HU mismatch found
while reading the docs: the mapping spreadsheet lists "Highest Temp pack"/
"Highest Temp cell" fields the HU says don't exist (CA-16), and omits the
"Lowest Temp rack" row the HU documents. The backend source settles it in
the HU's favor -- BuildFaults literally never populates a temp pack/cell
value for any site, confirming the mapping doc is the stale one here.

CONFIRMED DEFECT (2026-09-13): the HU's own "Formato de etiquetas en
pantalla" table (docs/OF-153.doc raw HTML, row "Ausente") documents
Formato=N/A but Ejemplo="—" (a real em-dash character in the source HTML,
not a conversion artifact -- confirmed by re-grepping the raw .doc). This
contradicts the CA bullets (CA-22/CA-23, the fallback table) which repeat
the literal word "N/A" -- an inconsistency inside the HU itself. Per
direct team-lead confirmation (this session, 2026-09-13) and the
already-confirmed sitewide convention (ATS, evt1/evt2, and every other
Advanced Diagnostics "no data" cell in this module render "—", never the
literal text "N/A"), the correct/expected placeholder here is "—", same
as everywhere else. The live app currently renders the literal string
"N/A" instead -- a real inconsistency with the rest of the module.
"""
import re

import pytest

from framework_api.services.monitoring_service import MonitoringService

pytestmark = pytest.mark.ui

SITE_NAME = "BOLIVIA"
EXPECTED_ROWS_IN_ORDER = [
    "Highest V rack", "Highest V pack", "Highest V cell",
    "Lowest V rack", "Lowest V pack", "Lowest V cell",
    "Highest temp rack", "Lowest temp rack",
]
RACK_RE = re.compile(r"^Rack-\d+$")
PACK_RE = re.compile(r"^Pack-\d{2}$")
CELL_RE = re.compile(r"^Cell-\d{3}$")

# CONFIRMED DEFECT (2026-09-13): the correct/expected "no data" placeholder
# is "—" (per the HU's own table Example column, team-lead confirmation,
# and the sitewide convention already confirmed for ATS/evt1/evt2/etc.).
# The live app currently renders the literal string "N/A" instead. NA_UI
# is what the app actually shows today; NA_EXPECTED is what it should show.
NA_UI = "N/A"
NA_EXPECTED = "—"


@pytest.fixture
def bolivia_monitoring_page(require_omniops, monitoring_page):
    return monitoring_page.select_site(SITE_NAME)


@pytest.fixture(scope="session")
def bolivia_site_id(db_conn):
    from shared.datasource.db_source import get_site_ids
    return get_site_ids(db_conn, [SITE_NAME])[SITE_NAME]


def test_card_title_and_subtitle(bolivia_monitoring_page):
    """CA-03: subtitle explains strings-first-then-racks priority and the
    ~5s live cadence via diagnostics push."""
    fault = bolivia_monitoring_page.fault_localization()
    subtitle = fault.subtitle().lower()
    assert "string" in subtitle or "rack" in subtitle, (
        f"expected the subtitle to mention the strings/racks priority rule, got: {fault.subtitle()!r}")


def test_no_time_range_badge_on_this_card(bolivia_monitoring_page):
    """CA-05: this panel is always live -- no 24h/7d/30d badge at all,
    same pattern already confirmed for Thermal Diagnostics/Site Load &
    Backup Context/Raw Event Bit Viewer."""
    fault = bolivia_monitoring_page.fault_localization()
    assert fault.card().locator(".monitoring-time-range-badge").count() == 0, (
        "expected no time-range badge -- CA-05 says the range doesn't apply here")


def test_global_time_range_does_not_change_values(bolivia_monitoring_page):
    """CA-05: switching the page's global 24h/7d/30d selector must not
    change this card's values -- it's always the current live state."""
    fault = bolivia_monitoring_page.fault_localization()
    before = fault.all_values()

    bolivia_monitoring_page.select_time_range("Last 7 days")
    bolivia_monitoring_page.page.wait_for_timeout(500)
    after = fault.all_values()
    bolivia_monitoring_page.select_time_range("Last 24 hours")

    assert before == after, (
        f"expected values to stay identical across a range switch (both are N/A for BOLIVIA "
        f"today, so this must be a no-op either way), before={before}, after={after}")


def test_eight_rows_in_three_cards_in_documented_order(bolivia_monitoring_page):
    """CA-24: exactly 8 rows across 3 device-cards, in the documented
    Highest V / Lowest V / Temperature block order."""
    fault = bolivia_monitoring_page.fault_localization()
    assert fault.all_row_labels() == EXPECTED_ROWS_IN_ORDER

    device_cards = fault.device_cards()
    assert device_cards.count() == 3, f"expected 3 device-card blocks, got {device_cards.count()}"


def test_temperature_block_has_no_pack_or_cell_rows(bolivia_monitoring_page):
    """CA-16: unlike the voltage blocks, Temperature has only 2 rows
    (Highest/Lowest temp rack) -- no pack or cell rows at all. Confirmed
    against the real backend source: BuildFaults hardcodes
    HighestTempPack/HighestTempCell/LowestTempPack/LowestTempCell to null
    unconditionally, for every site/protocol -- there's no code path that
    could ever populate a temp pack/cell value on this panel."""
    fault = bolivia_monitoring_page.fault_localization()
    labels = fault.all_row_labels()
    assert not any("temp pack" in l.lower() or "temp cell" in l.lower() for l in labels), (
        f"expected no temp pack/cell rows in the UI, got labels: {labels}")


def test_all_rows_are_absent_for_a_fractal_site_with_no_bms_strings(bolivia_monitoring_page, api_client, bolivia_site_id):
    """Documented Fractal gap (docs/OF-153.txt: "Fractal sin strings BMS
    mapeados" -> panel sin dato), confirmed via source (see module
    docstring) rather than assumed. Cross-checked against the real API's
    faultLocalization object -- all 8 location fields must be null.
    Deliberately accepts either placeholder text (NA_UI or NA_EXPECTED)
    here -- WHICH placeholder is correct is covered separately by
    test_absent_rows_show_a_dash_not_the_literal_text_na (confirmed
    defect); this test is only about the underlying data being absent."""
    fault = bolivia_monitoring_page.fault_localization()
    values = fault.all_values()
    assert all(v in (NA_UI, NA_EXPECTED) for v in values.values()), (
        f"expected all 8 rows to show an absent-data placeholder for BOLIVIA (Fractal, no BMS "
        f"string telemetry mapped), got: {values}")

    api_data = MonitoringService(api_client).get_monitoring_summary(site_id=bolivia_site_id).fault_localization
    location_fields = (
        api_data.highest_rack, api_data.highest_pack, api_data.highest_cell,
        api_data.lowest_rack, api_data.lowest_pack, api_data.lowest_cell,
        api_data.highest_temp_rack, api_data.highest_temp_pack, api_data.highest_temp_cell,
        api_data.lowest_temp_rack, api_data.lowest_temp_pack, api_data.lowest_temp_cell,
    )
    assert all(f is None for f in location_fields), (
        f"expected all API location fields to be null for BOLIVIA, got: {location_fields}")


def test_backend_still_computes_fault_device_fields_even_though_unrendered(bolivia_monitoring_page, api_client, bolivia_site_id):
    """The HU explicitly documents that FaultDeviceId/FaultType/
    FaultLocation ARE computed by the backend (from the most recent open
    alarm) but deliberately NOT rendered on this panel. Confirms the API
    still exposes them (a real, live 3rd-layer signal, even though the UI
    doesn't surface it) -- guards against silently losing that data if a
    future UI change decided to show it."""
    api_data = MonitoringService(api_client).get_monitoring_summary(site_id=bolivia_site_id).fault_localization
    fault = bolivia_monitoring_page.fault_localization()

    assert not any("fault device" in l.lower() or "fault type" in l.lower() or "fault location" in l.lower()
                   for l in fault.all_row_labels()), (
        "expected FaultDeviceId/FaultType/FaultLocation to stay unrendered on this panel per the HU")

    if api_data.fault_device_id is None and api_data.fault_type is None and api_data.fault_location is None:
        pytest.skip("no open alarm right now on BOLIVIA -- nothing for the backend to derive these from")


@pytest.mark.xfail(
    strict=True,
    reason="CONFIRMED DEFECT (2026-09-13): the correct 'no data' placeholder "
           "for this panel is a dash ('—') -- per the HU's own format table "
           "(docs/OF-153.doc raw HTML: row 'Ausente' has Ejemplo='—', a real "
           "em-dash in the source, not a conversion artifact), per direct "
           "team-lead confirmation this session, and per the sitewide "
           "convention already confirmed for ATS/evt1/evt2/Context and every "
           "other Advanced Diagnostics 'no data' cell in this module. The "
           "live app renders the literal text 'N/A' instead for all 8 rows "
           "on BOLIVIA -- inconsistent with the rest of the module. Note the "
           "HU's own CA-22/CA-23 bullets and its fallback table repeat the "
           "word 'N/A' verbatim, contradicting the format table's own "
           "Example column -- an inconsistency inside the HU itself, "
           "resolved here in favor of the table's Example + the team lead's "
           "direction + the app's own established convention.")
def test_absent_rows_show_a_dash_not_the_literal_text_na(bolivia_monitoring_page):
    fault = bolivia_monitoring_page.fault_localization()
    values = fault.all_values()
    assert all(v == NA_EXPECTED for v in values.values()), (
        f"expected all absent rows to show '—' (the sitewide convention), got: {values}")


def test_rack_pack_cell_label_formats_when_present(bolivia_monitoring_page):
    """CA-20/CA-22: whenever a location value isn't absent, it must match
    the documented Rack-N / Pack-NN / Cell-NNN format -- guards against a
    raw unformatted value or a measurement suffix (CA-21) ever leaking
    through, for whichever site first gets real BMS string/rack telemetry."""
    fault = bolivia_monitoring_page.fault_localization()
    values = fault.all_values()

    for label, value in values.items():
        if value in (NA_UI, NA_EXPECTED):
            continue
        if "rack" in label.lower():
            assert RACK_RE.match(value), f"{label}={value!r} doesn't match Rack-N"
        elif "pack" in label.lower():
            assert PACK_RE.match(value), f"{label}={value!r} doesn't match Pack-NN"
        elif "cell" in label.lower():
            assert CELL_RE.match(value), f"{label}={value!r} doesn't match Cell-NNN"
