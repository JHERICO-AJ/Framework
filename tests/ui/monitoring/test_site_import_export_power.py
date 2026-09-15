"""Data & Monitoring - Site Import / Export Power (docs/OF-143.txt CA-22,
docs/GraficasMonitoring.md) -- the neighboring card to Site Power
Telemetry's Meter / CT-PT focus. Shares the EXACT same powerTrendData (no
separate endpoint, no Trend Focus selector -- always just Import (MW) +
Export (MW)).

CONFIRMED DEFECT (2026-09-14, Qase Defect #57 -- same root cause as Site
Power Telemetry's Meter / CT-PT focus, see
test_site_power_telemetry.test_import_and_export_power_match_monitoring_stat_history):
this card's Import Power and Export Power are ALSO swapped relative to the
real MonitoringStat MeterDemand value and the documented formula
(docs/OF-143.txt: "Import = max(demanda, 0); Export = abs(min(demanda, 0))").
Confirmed live for the same hour, both cards agree with EACH OTHER (CA-22 --
"misma fuente que la tarjeta Import / Export") but both disagree with the
real value -- proving the root cause is shared (backend or a shared
frontend transform), not isolated to one component.
"""
import re

import pytest

from shared.datasource.db_source import (
    get_site_ids,
    get_monitoring_stat_import_power_avg_kw, get_monitoring_stat_export_power_avg_kw,
)
from tests.ui.monitoring.test_site_power_telemetry import (
    SITE_NAME, TIME_RANGES, EXPECTED_BADGE_BY_RANGE, EXPECTED_PERIOD_BY_RANGE,
    TOL_ABS_MW, _utc_window_for_tooltip_label,
)

pytestmark = pytest.mark.ui

EXPECTED_LEGEND = {"Export (MW)", "Import (MW)"}


@pytest.fixture
def bolivia_monitoring_page(require_omniops, monitoring_page):
    return monitoring_page.select_site(SITE_NAME)


@pytest.fixture(scope="session")
def bolivia_site_id(db_conn):
    return get_site_ids(db_conn, [SITE_NAME])[SITE_NAME]


def _tooltip_values(tooltip_text):
    """This card's tooltip format has a trailing unit on the VALUE too
    (e.g. "Export (MW) : 2.88 MW"), unlike Site Power Telemetry's own
    tooltip ("Import Power (MW): 0.835") -- strip everything after the
    number instead of a plain float() cast."""
    values = {}
    for line in tooltip_text.splitlines()[1:]:
        if ":" not in line:
            continue
        label, raw_value = line.split(":", 1)
        match = re.search(r"-?\d+(?:\.\d+)?", raw_value)
        if match:
            values[label.strip()] = float(match.group())
    return values


def test_card_title_and_subtitle(bolivia_monitoring_page):
    """CA-22: card exists with its own title, independent of any Trend
    Focus selector (this card doesn't have one)."""
    card = bolivia_monitoring_page.site_import_export_power().card()
    assert card.locator(".card-title").inner_text().strip().upper() == "SITE IMPORT / EXPORT POWER"
    assert card.locator(".card-subtitle").count() > 0


@pytest.mark.parametrize("time_range", TIME_RANGES)
def test_badge_and_period_match_selected_time_range(bolivia_monitoring_page, time_range):
    """CA-04: this card follows the SAME global 24h/7d/30d selector as
    every other Data & Monitoring chart, including Site Power Telemetry."""
    bolivia_monitoring_page.select_time_range(time_range)
    bolivia_monitoring_page.page.wait_for_timeout(1000)
    card = bolivia_monitoring_page.site_import_export_power()
    assert card.time_range_badge() == EXPECTED_BADGE_BY_RANGE[time_range]
    assert card.time_range_period() == EXPECTED_PERIOD_BY_RANGE[time_range]


def test_legend_and_plotted_lines_match_documented_series(bolivia_monitoring_page):
    """CA-22: always exactly Import (MW) + Export (MW), no Trend Focus to
    change this -- and BOLIVIA has real meter telemetry, so both series
    actually plot (unlike Container/Rack or HVAC, which are omitted for
    this site)."""
    card = bolivia_monitoring_page.site_import_export_power()
    assert set(card.legend_series()) == EXPECTED_LEGEND
    assert set(card.line_names()) == EXPECTED_LEGEND


@pytest.mark.xfail(
    strict=True,
    reason="CONFIRMED DEFECT (2026-09-14, Qase Defect #58 -- same root cause "
           "as Site Power Telemetry's Meter / CT-PT focus, Defect #57): "
           "Import Power and Export Power are swapped here too. Confirmed "
           "live for the hour [2026-09-14 06:00, 07:00) UTC: real "
           "MonitoringStat MeterDemand averages +2831.9 kW (positive), which "
           "per docs/OF-143.txt's formula should render as Import~2.83 MW / "
           "Export=0.00 MW -- this card instead shows Export=2.88 MW / "
           "Import=0.00 MW, the exact same swap already confirmed on the "
           "Meter / CT-PT focus. Both cards agree with EACH OTHER (CA-22) but "
           "neither matches the real value -- confirms one shared root cause, "
           "not two independent bugs.")
@pytest.mark.parametrize("time_range", TIME_RANGES)
def test_import_and_export_power_match_monitoring_stat_history(
        bolivia_monitoring_page, db_conn, bolivia_site_id, time_range):
    """Real value cross-check, same methodology as Site Power Telemetry's
    own Meter / CT-PT focus test -- CA-22 says this card must show the
    SAME values."""
    bolivia_monitoring_page.select_time_range(time_range)
    card = bolivia_monitoring_page.site_import_export_power()

    tooltip_text = card.hover_latest_point_tooltip_text()
    tooltip_lines = tooltip_text.splitlines()
    window_start, window_end = _utc_window_for_tooltip_label(bolivia_monitoring_page.page, tooltip_lines[0])

    hourly_only = time_range != "Last 24 hours"
    db_import_kw = get_monitoring_stat_import_power_avg_kw(
        db_conn, bolivia_site_id, window_start, window_end, hourly_samples_only=hourly_only)
    db_export_kw = get_monitoring_stat_export_power_avg_kw(
        db_conn, bolivia_site_id, window_start, window_end, hourly_samples_only=hourly_only)
    assert db_import_kw is not None and db_export_kw is not None, (
        f"no MonitoringStat MeterDemand rows for {SITE_NAME!r} in [{window_start}, {window_end})")

    values = _tooltip_values(tooltip_text)
    chart_import_mw = values["Import (MW)"]
    chart_export_mw = values["Export (MW)"]
    assert chart_import_mw == pytest.approx(db_import_kw / 1000.0, abs=TOL_ABS_MW), (
        f"[{time_range}] card's Import ({chart_import_mw} MW) for the point at "
        f"{tooltip_lines[0]!r} disagrees with the real MonitoringStat-derived value "
        f"({db_import_kw / 1000.0:.3f} MW) by more than {TOL_ABS_MW} MW")
    assert chart_export_mw == pytest.approx(db_export_kw / 1000.0, abs=TOL_ABS_MW), (
        f"[{time_range}] card's Export ({chart_export_mw} MW) for the point at "
        f"{tooltip_lines[0]!r} disagrees with the real MonitoringStat-derived value "
        f"({db_export_kw / 1000.0:.3f} MW) by more than {TOL_ABS_MW} MW")


def test_import_export_card_matches_meter_ct_pt_focus(bolivia_monitoring_page):
    """CA-22 word-for-word: 'Import/export del foco Medidor = misma fuente "
    que la tarjeta Import / Export (mismo sitio y rango)' -- this asserts
    the CONSISTENCY between the two surfaces, independent of whether the
    shared value is itself correct (see the xfail above for that). Both
    should always show the exact same two numbers."""
    bolivia_monitoring_page.select_time_range("Last 24 hours")
    chart = bolivia_monitoring_page.site_power_telemetry()
    chart.select_trend_focus("Meter / CT·PT")
    focus_tooltip = chart.hover_latest_point_tooltip_text()
    focus_values = {
        l.split(":")[0].strip(): float(l.split(":")[1].strip())
        for l in focus_tooltip.splitlines()[1:]
    }

    card = bolivia_monitoring_page.site_import_export_power()
    card_tooltip = card.hover_latest_point_tooltip_text()
    card_values = _tooltip_values(card_tooltip)

    assert card_values["Import (MW)"] == pytest.approx(focus_values["Import Power (MW)"], abs=TOL_ABS_MW), (
        "Site Import/Export Power's Import should match Meter/CT-PT focus's Import Power (CA-22)")
    assert card_values["Export (MW)"] == pytest.approx(focus_values["Export Power (MW)"], abs=TOL_ABS_MW), (
        "Site Import/Export Power's Export should match Meter/CT-PT focus's Export Power (CA-22)")


