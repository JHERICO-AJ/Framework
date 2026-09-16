"""Data & Monitoring - Environmental Monitoring (docs/OF-151.txt): a
site-level, ALWAYS-LIVE 2-metric summary (Ambient Temp, Humidity), each
independently resolved On-site (SYS sensor) vs API (Intake external
weather fallback) -- explicitly NOT affected by the page's 24h/7d/30d
range selector (CA-05), same pattern as Site Load & Backup Context/Raw
Event Bit Viewer/Fault Localization.

Scalability note (per team direction): nothing here hardcodes a single
expected reading. The exact numeric value is only compared against a real
ground-truth source (the Intake config file, or the API) whenever the
CURRENT source flag says that ground truth applies -- if a site's source
ever flips from API to On-site (e.g. once real SYS ambient telemetry gets
mapped), the API-vs-Intake-config checks simply no longer apply (skipped,
not broken), while every structural/format check keeps holding regardless
of which source is active. This mirrors the same convergence-style,
source-driven approach already used for ATS/ Net power in
test_site_load_backup_context.py.

BOLIVIA (Fractal). The HU's own "Fuentes por protocolo" table documents a
real, deliberate gap: "Fractal (fase actual): -- (sin mapeo ambiental)" --
so both metrics always fall back to the Intake config's External/Environment
fields (docs/omniops_data_intake_BOLIVIA.xlsx: ambient_temperature=25,
relative_humidity=50), confirmed live 2026-09-13 AND via the real backend
source: FractalRawDataMapper.cs never assigns AmbientTemp/Humidity from any
Fractal field (only a comment noting the gap), so SiteState.AmbientTemp/
Humidity never receive a value for BOLIVIA, and
MonitoringComputedService.BuildEnvironmental's on-site branch never wins.

CONFIRMED DEFECT (2026-09-13): the "(API)" flag is misleading -- it does
NOT reflect a live external weather feed, contradicting the mapping's own
"Telemetry Source: Weather station / site sensor / EMS external feed" +
"Refresh Rate: 1-15 min". The backend genuinely HAS a live weather
integration (Modules/Weather: WeatherService + AzureMapsWeatherClient,
real per-site lat/lon calls to Azure Maps, refreshed hourly, persisted to
weather.WeatherData) -- and BOLIVIA already has real, recent rows there
(confirmed live 2026-09-13: current row Temperature=36.80°C,
Humidity=35.00%, Conditions='Sunny', timestamped 2026-09-12 22:53:40 UTC).
But MonitoringComputedService.BuildEnvironmental never calls that service
at all -- ExternalAmbientTemp/ExternalHumidity come solely from
MonitoringConfig, which just reads the Intake config's static
"ambient_temperature"/"relative_humidity" fields (whose own Reference
text literally says "Default nominal ambient temperature"/"...humidity"
-- a placeholder, not a live reading). So Environmental Monitoring shows
a frozen 25.0°C/50% "(API)" while the site's real, already-recorded live
weather is 36.80°C/35% -- the panel is fully disconnected from the real
external weather feed its own label implies.
"""
import re

import pytest

from framework_api.services.monitoring_service import MonitoringService

pytestmark = pytest.mark.ui

SITE_NAME = "BOLIVIA"
EXPECTED_BLOCK_TITLES = ["Ambient Temp", "Humidity"]
VALID_SOURCES = {"On-site", "API"}

# Ground truth for BOLIVIA's own Intake config (docs/omniops_data_intake_BOLIVIA.xlsx,
# "Intake Fields" sheet, section=external/group=env) -- only meaningful while the
# UI's own source flag says "API" (i.e. no on-site sensor is currently winning).
INTAKE_EXTERNAL_AMBIENT_TEMP_C = 25.0
INTAKE_EXTERNAL_HUMIDITY_PCT = 50.0

TEMP_FORMAT_RE = re.compile(r"^-?\d+\.\d°C(?: \((On-site|API)\))?$")
HUMIDITY_FORMAT_RE = re.compile(r"^\d+%(?: \((On-site|API)\))?$")


@pytest.fixture
def bolivia_monitoring_page(require_omniops, monitoring_page):
    return monitoring_page.select_site(SITE_NAME)


@pytest.fixture(scope="session")
def bolivia_site_id(db_conn):
    from shared.datasource.db_source import get_site_ids
    return get_site_ids(db_conn, [SITE_NAME])[SITE_NAME]


def test_card_title_and_subtitle(bolivia_monitoring_page):
    """CA-03: subtitle explains the site-sensor-first, weather-API-fallback
    priority and the ~5s live cadence."""
    env = bolivia_monitoring_page.environmental_monitoring()
    subtitle = env.subtitle().lower()
    assert "sys" in subtitle or "ambient" in subtitle, (
        f"expected the subtitle to mention the SYS sensor priority, got: {env.subtitle()!r}")


def test_no_time_range_badge_on_this_card(bolivia_monitoring_page):
    """CA-05: this panel is always live -- no 24h/7d/30d badge at all,
    same pattern already confirmed for the rest of Advanced Diagnostics."""
    env = bolivia_monitoring_page.environmental_monitoring()
    assert env.card().locator(".monitoring-time-range-badge").count() == 0, (
        "expected no time-range badge -- CA-05 says the range doesn't apply here")


def test_global_time_range_does_not_change_values(bolivia_monitoring_page):
    """CA-05: switching the page's global 24h/7d/30d selector must not
    change this card's values -- it's always the current live state."""
    env = bolivia_monitoring_page.environmental_monitoring()
    before = (env.raw_value_text("Ambient Temp"), env.raw_value_text("Humidity"))

    bolivia_monitoring_page.select_time_range("Last 7 days")
    bolivia_monitoring_page.page.wait_for_timeout(500)
    after = (env.raw_value_text("Ambient Temp"), env.raw_value_text("Humidity"))
    bolivia_monitoring_page.select_time_range("Last 24 hours")

    assert before == after, (
        f"expected values to stay identical across a range switch, before={before}, after={after}")


def test_two_blocks_in_documented_order(bolivia_monitoring_page):
    """CA-24-equivalent structural check: exactly Ambient Temp then
    Humidity, in that order."""
    env = bolivia_monitoring_page.environmental_monitoring()
    assert env.block_titles() == EXPECTED_BLOCK_TITLES


def test_ambient_temp_format(bolivia_monitoring_page):
    """CA-06/CA-20: "{n.d}°C" or "{n.d}°C (Source)", or "—" if absent --
    always exactly 1 decimal, never a raw/unrounded float, regardless of
    which source is currently active."""
    env = bolivia_monitoring_page.environmental_monitoring()
    raw = env.raw_value_text("Ambient Temp")
    if raw == "—":
        pytest.skip("Ambient Temp is currently absent (—) -- nothing to format-check")
    assert TEMP_FORMAT_RE.match(raw), f"Ambient Temp {raw!r} doesn't match the documented 1-decimal °C format"


def test_humidity_format(bolivia_monitoring_page):
    """CA-11/CA-21: "{n}%" or "{n}% (Source)", or "—" if absent -- always
    a whole integer percent, never a decimal, regardless of source."""
    env = bolivia_monitoring_page.environmental_monitoring()
    raw = env.raw_value_text("Humidity")
    if raw == "—":
        pytest.skip("Humidity is currently absent (—) -- nothing to format-check")
    assert HUMIDITY_FORMAT_RE.match(raw), f"Humidity {raw!r} doesn't match the documented integer % format"


def test_source_flag_only_appears_when_a_value_is_present(bolivia_monitoring_page):
    """CA-10: the "(On-site)"/"(API)" flag must never appear next to an
    absent ("—") value, and a present value must always carry one of the
    two documented source flags -- never a raw/untranslated source string."""
    env = bolivia_monitoring_page.environmental_monitoring()
    for title in EXPECTED_BLOCK_TITLES:
        value, source = env.value_and_source(title)
        if value is None:
            assert source is None, (
                f"{title}: expected no source flag when the value is absent, got source={source!r}")
        else:
            assert source in VALID_SOURCES, (
                f"{title}: expected source to be one of {VALID_SOURCES} when a value is present, "
                f"got {source!r}")


def test_ambient_temp_and_humidity_can_have_independent_sources(bolivia_monitoring_page):
    """CA-14: temp and humidity are resolved independently -- this test
    doesn't assert they DIFFER (that would be just as brittle as assuming
    they match), only that reading each source doesn't crash and each is
    independently one of the valid documented sources whenever present."""
    env = bolivia_monitoring_page.environmental_monitoring()
    _, temp_source = env.ambient_temp_value_and_source()
    _, humidity_source = env.humidity_value_and_source()
    for source in (temp_source, humidity_source):
        if source is not None:
            assert source in VALID_SOURCES


def test_ambient_temp_matches_intake_config_when_source_is_api(bolivia_monitoring_page):
    """Documents the CURRENT implementation (Intake config file, not a
    fabricated number): whenever the UI's own source flag says "API" (no
    on-site sensor winning), the displayed value matches BOLIVIA's
    configured external ambient_temperature -- confirmed against
    docs/omniops_data_intake_BOLIVIA.xlsx. If the source is ever "On-site"
    instead (a real SYS sensor mapped), this check no longer applies and
    is skipped rather than failing.

    CAVEAT (2026-09-13, Qase #683/Defect #48): this is itself the
    confirmed defect, not the intended design -- "(API)" should reflect
    the site's real live weather feed (already working elsewhere via
    WeatherService/AzureMapsWeatherClient -- see
    test_ambient_temp_reflects_the_sites_real_live_weather_feed), not this
    static Intake default. This test exists to catch regressions in
    today's actual behavior; once Defect #48 is fixed, its expected value
    should change to the real weather feed instead."""
    env = bolivia_monitoring_page.environmental_monitoring()
    value, source = env.ambient_temp_value_and_source()
    if source != "API":
        pytest.skip(f"Ambient Temp's source is {source!r}, not 'API' -- the Intake-config "
                    f"ground truth only applies to the API fallback path")
    assert value == pytest.approx(INTAKE_EXTERNAL_AMBIENT_TEMP_C, abs=0.1), (
        f"expected Ambient Temp ({value}) to match the configured Intake fallback "
        f"({INTAKE_EXTERNAL_AMBIENT_TEMP_C})")


def test_humidity_matches_intake_config_when_source_is_api(bolivia_monitoring_page):
    """Same CURRENT-implementation check as Ambient Temp, for Humidity --
    see the same Defect #48 caveat above: this documents today's actual
    (buggy) behavior, not the intended design."""
    env = bolivia_monitoring_page.environmental_monitoring()
    value, source = env.humidity_value_and_source()
    if source != "API":
        pytest.skip(f"Humidity's source is {source!r}, not 'API' -- the Intake-config "
                    f"ground truth only applies to the API fallback path")
    assert value == pytest.approx(INTAKE_EXTERNAL_HUMIDITY_PCT, abs=1), (
        f"expected Humidity ({value}) to match the configured Intake fallback "
        f"({INTAKE_EXTERNAL_HUMIDITY_PCT})")


@pytest.mark.xfail(
    strict=True,
    reason="CONFIRMED DEFECT (2026-09-13): the '(API)' flag is misleading -- "
           "it implies a live external weather feed (matching the mapping's "
           "own 'Telemetry Source: Weather station / site sensor / EMS "
           "external feed' + 'Refresh Rate: 1-15 min'), but "
           "MonitoringComputedService.BuildEnvironmental never calls the "
           "backend's real, working weather integration (Modules/Weather: "
           "WeatherService + AzureMapsWeatherClient, real per-site lat/lon "
           "Azure Maps calls, refreshed hourly, persisted to "
           "weather.WeatherData). BOLIVIA already has real, recent rows "
           "there. Instead, ExternalAmbientTemp/ExternalHumidity come "
           "solely from a static Intake config default (whose own "
           "Reference text says 'Default nominal ambient temperature/"
           "humidity' -- a placeholder). So the panel shows a frozen "
           "25.0°C/50% while the site's real live weather (already "
           "recorded in the same DB) is a completely different, "
           "constantly-changing value.")
def test_ambient_temp_reflects_the_sites_real_live_weather_feed(bolivia_monitoring_page, db_conn, bolivia_site_id):
    """When the UI's source flag says (API), the value should come from
    the site's real live external weather feed (weather.WeatherData,
    IsCurrent=True) -- not a static, never-changing Intake default."""
    from shared.datasource.db_source import get_current_weather

    env = bolivia_monitoring_page.environmental_monitoring()
    value, source = env.ambient_temp_value_and_source()
    if source != "API":
        pytest.skip(f"Ambient Temp's source is {source!r}, not 'API' -- this check only applies "
                    f"to the external-feed fallback path")

    real_weather = get_current_weather(db_conn, bolivia_site_id)
    if real_weather is None or real_weather["temperature_c"] is None:
        pytest.skip("no current weather.WeatherData row for BOLIVIA to compare against")

    assert value == pytest.approx(real_weather["temperature_c"], abs=0.5), (
        f"expected the '(API)' Ambient Temp ({value}) to reflect the site's real live weather "
        f"feed ({real_weather['temperature_c']}°C, recorded {real_weather['timestamp']}), not a "
        f"static config default")


@pytest.mark.xfail(
    strict=True,
    reason="CONFIRMED DEFECT (2026-09-13): same root cause as the Ambient "
           "Temp version above -- Humidity's '(API)' fallback also never "
           "reads the real weather.WeatherData row; it's a static Intake "
           "config default instead.")
def test_humidity_reflects_the_sites_real_live_weather_feed(bolivia_monitoring_page, db_conn, bolivia_site_id):
    from shared.datasource.db_source import get_current_weather

    env = bolivia_monitoring_page.environmental_monitoring()
    value, source = env.humidity_value_and_source()
    if source != "API":
        pytest.skip(f"Humidity's source is {source!r}, not 'API' -- this check only applies to "
                    f"the external-feed fallback path")

    real_weather = get_current_weather(db_conn, bolivia_site_id)
    if real_weather is None or real_weather["humidity_pct"] is None:
        pytest.skip("no current weather.WeatherData humidity row for BOLIVIA to compare against")

    assert value == pytest.approx(real_weather["humidity_pct"], abs=1), (
        f"expected the '(API)' Humidity ({value}) to reflect the site's real live weather feed "
        f"({real_weather['humidity_pct']}%, recorded {real_weather['timestamp']}), not a static "
        f"config default")


def test_ui_values_and_sources_match_the_real_api(bolivia_monitoring_page, api_client, bolivia_site_id):
    """True cross-layer ground truth (UI vs the real monitoring summary
    API's environmentalMonitoring object) -- both the source flag and the
    rounded numeric value must match exactly, since both this test and the
    UI read the same already-computed backend DTO (no independent
    recomputation needed, unlike fast-changing power values)."""
    env = bolivia_monitoring_page.environmental_monitoring()
    api_data = MonitoringService(api_client).get_monitoring_summary(site_id=bolivia_site_id).environmental_monitoring

    ui_temp, ui_temp_source = env.ambient_temp_value_and_source()
    assert ui_temp_source == api_data.ambient_temp_source, (
        f"expected UI Ambient Temp source ({ui_temp_source!r}) to match the API "
        f"({api_data.ambient_temp_source!r})")
    if api_data.ambient_temp is not None:
        assert ui_temp == pytest.approx(float(api_data.ambient_temp), abs=0.05), (
            f"expected UI Ambient Temp ({ui_temp}) to match the API ({api_data.ambient_temp})")

    ui_humidity, ui_humidity_source = env.humidity_value_and_source()
    assert ui_humidity_source == api_data.humidity_source, (
        f"expected UI Humidity source ({ui_humidity_source!r}) to match the API "
        f"({api_data.humidity_source!r})")
    if api_data.humidity is not None:
        assert ui_humidity == pytest.approx(float(api_data.humidity), abs=0.5), (
            f"expected UI Humidity ({ui_humidity}) to match the API ({api_data.humidity})")
