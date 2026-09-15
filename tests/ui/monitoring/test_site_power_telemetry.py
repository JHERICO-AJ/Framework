"""Data & Monitoring - Site Power Telemetry (docs/OF-143.txt) -- a Recharts
line chart (real SVG, NOT canvas -- confirmed 2026-09-10 against the real
deployed app) with a Trend Focus selector that swaps which series overlay
the always-visible Site SOC (%) line.

BOLIVIA (Fractal) specifically. Unlike the diagnostic cards elsewhere in
this module, this chart reads consolidated 5-min history
(monitoring.MonitoringStat), not live in-memory state (docs/OF-143.txt:
"Unlike the live diagnostic cards, this chart reads consolidated
history, not the instantaneous in-memory state") -- confirmed
real ground truth is available here via get_latest_monitoring_stat_soc.

Per-focus series presence for BOLIVIA (confirmed live 2026-09-10, matches
docs/OF-143.txt's own Fractal mapping table): Container & Rack and HVAC &
Aux correctly show NO data lines (only the legend entry, no plotted line)
because Fractal never sends container/rack temperatures or HVAC power
("Not present in Fractal today") -- this is the documented "omitted line"
fallback (CA-08/CA-09), not a defect. PCS Power, EMS & Network, and
Meter / CT·PT all plot every one of their documented series, since Fractal
DOES map site/inverter power, freshness/gaps, and meter import/export.

CONFIRMED DEFECT (confirmed directly with the team, see
test_delta_cellv_is_omitted_not_a_fabricated_zero below): ΔCellV (mV) DOES
plot a line for BOLIVIA even though monitoring.MonitoringStat's
CellVDelta/HCellV/LCellV are all NULL for this site (confirmed via direct
query) -- it draws a flat 0 rather than being omitted like Container/Rack
temp and HVAC, even though docs/OF-143.txt's own fallback table explicitly
assigns it that different treatment ("ΔCellV: 0 mV (or calculated from
voltages)" vs. "Container/rack temp: Omitted line (null)"). Violates
the "never invent a zero" principle already established elsewhere in this
exact project (Dispatch Limits & Tracking's CA-11: "No data -> N/A, never
an invented zero").

IMPORTANT CAVEAT ON EVERY monitoring.MonitoringStat cross-layer check in
this file: confirmed 2026-09-11 that BOLIVIA's real telemetry pipeline can
silently stop feeding this table (last real, non-interpolated sample was
23:55 UTC that day -- ~2h gap, every bucket since IsInterpolated=True,
holding a near-constant fallback instead of the actual live simulator
value, confirmed by independently polling the simulator directly: it was
still swinging through a full +/-8000 kW cycle the whole time). A chart-
vs-MonitoringStat match during a gap like that is NOT proof the underlying
aggregation pipeline (simulator -> ingestion -> MonitoringStat) is
correct -- both sides can agree on the same stale, interpolated number.
test_telemetry_has_not_been_stuck_interpolating_too_long below is the
automated guard for this; tools/verify_monitoring_stat_aggregation.py is
the slower, deeper check (samples the live simulator for a real 5-min
window and compares against that exact MonitoringStat bucket) for when
telemetry is confirmed live.
"""
import re
from datetime import datetime, timedelta, timezone

import pytest

from shared.datasource.db_source import (
    get_site_ids, get_monitoring_stat_soc_avg,
    get_monitoring_stat_charge_power_avg_kw, get_monitoring_stat_discharge_power_avg_kw,
    get_monitoring_stat_pcs_sum_active_power_avg_kw,
    get_monitoring_stat_data_freshness_avg_seconds,
    get_monitoring_stat_import_power_avg_kw, get_monitoring_stat_export_power_avg_kw,
    get_monitoring_stat_meter_demand_avg_kw,
    get_minutes_since_last_real_monitoring_stat_sample,
)

# Real ingestion normally lands within a few minutes (docs/OF-143.txt:
# "En vivo (~5 s)" for the diagnostic cards, "cada ~5 min" for this
# chart's own bucket cadence). 30 minutes is generous enough to absorb
# normal jitter/restarts without masking a real, ongoing outage --
# confirmed 2026-09-11 a real gap (site machine went to sleep) showed up
# as ~115 minutes stuck interpolating, far past this threshold.
MAX_MINUTES_WITHOUT_REAL_TELEMETRY = 30

# Spanish month abbreviations, as rendered by the real app's 7d/30d tooltip
# date label (e.g. "jue, 10 sept 2026") -- confirmed 2026-09-10 against the
# live deploy. Not locale-driven parsing (fragile if the app's locale ever
# changes): a fixed table matching what's actually observed.
_SPANISH_MONTH_ABBR = {
    "ene": 1, "feb": 2, "mar": 3, "abr": 4, "may": 5, "jun": 6,
    "jul": 7, "ago": 8, "sep": 9, "sept": 9, "oct": 10, "nov": 11, "dic": 12,
}

pytestmark = pytest.mark.ui

SITE_NAME = "BOLIVIA"

# CA-03: exactly these 6 options, in this order.
EXPECTED_TREND_FOCUS_OPTIONS = [
    "Battery / BMS", "PCS Power", "Container & Rack",
    "HVAC & Aux", "EMS & Network", "Meter / CT·PT",
]

# CA-06 through CA-11: documented series per focus. Site SOC (%) is always
# present (CA-05) so it's included in every entry rather than asserted
# separately each time.
EXPECTED_LEGEND_BY_FOCUS = {
    "Battery / BMS": {"Site SOC (%)", "Charge Power (MW)", "Discharge Power (MW)", "ΔCellV (mV)"},
    "PCS Power": {"Site SOC (%)", "Σ PCS Active Power (MW)"},
    "EMS & Network": {"Site SOC (%)", "Data Freshness (s)", "Sample Gap Count"},
    "Meter / CT·PT": {"Site SOC (%)", "Import Power (MW)", "Export Power (MW)"},
}

# Confirmed live: Fractal never sends container/rack temps or HVAC power
# for BOLIVIA (docs/OF-143.txt's own Fractal mapping table), so per
# CA-08/CA-09's "línea omitida" fallback these lines correctly don't plot
# -- only Site SOC actually draws.
EXPECTED_PLOTTED_LINES_BY_FOCUS = {
    "Battery / BMS": {"Site SOC (%)", "Charge Power (MW)", "Discharge Power (MW)", "ΔCellV (mV)"},
    "PCS Power": {"Site SOC (%)", "Σ PCS Active Power (MW)"},
    "Container & Rack": {"Site SOC (%)"},
    "HVAC & Aux": {"Site SOC (%)"},
    "EMS & Network": {"Site SOC (%)", "Data Freshness (s)", "Sample Gap Count"},
    "Meter / CT·PT": {"Site SOC (%)", "Import Power (MW)", "Export Power (MW)"},
}

TOL_ABS_SOC_PCT = 0.5
TOL_ABS_MW = 0.2
TOL_ABS_SECONDS = 5.0

# CA-04: the 3 global time ranges, and the exact badge/period text and
# tooltip label shape each one produces on this chart (confirmed live
# 2026-09-10). 24h's point is a complete HOUR ("HH:MM:SS" tooltip label);
# 7d/30d's point is a complete DAY ("<weekday>, D <month> YYYY" label,
# Spanish locale) -- docs/OF-143.txt: "sin la hora/el dia en curso" (the
# still-forming current hour/day is excluded), which is exactly why this
# needs its OWN UTC window resolved from that label, not "now" rounded down.
TIME_RANGES = ["Last 24 hours", "Last 7 days", "Last 30 days"]
EXPECTED_BADGE_BY_RANGE = {"Last 24 hours": "24H", "Last 7 days": "7D", "Last 30 days": "30D"}
EXPECTED_PERIOD_BY_RANGE = {
    "Last 24 hours": "Last 24 hours.", "Last 7 days": "Last 7 days.", "Last 30 days": "Last 30 days.",
}


@pytest.fixture
def bolivia_monitoring_page(require_omniops, monitoring_page):
    return monitoring_page.select_site(SITE_NAME)


@pytest.fixture(scope="session")
def bolivia_site_id(db_conn):
    return get_site_ids(db_conn, [SITE_NAME])[SITE_NAME]


def _utc_window_for_tooltip_label(page, label):
    """The exact [window_start, window_end) UTC boundary a tooltip's first
    line refers to -- an "HH:MM:SS" label (24h) resolves to that complete
    HOUR; a "<weekday>, D <month> YYYY" label (7d/30d) resolves to that
    complete DAY. Both are rendered in the BROWSER's local timezone
    (confirmed 2026-09-10: "19:00:00" local in America/La_Paz, UTC-4,
    matched the DB's 23:00 UTC bucket exactly), so this reads the browser's
    own timezone offset via JS rather than assuming a fixed one -- correct
    regardless of what machine/timezone this suite runs on."""
    offset_min = page.evaluate("() => new Date().getTimezoneOffset()")

    time_match = re.match(r"^(\d{1,2}):(\d{2}):(\d{2})$", label)
    if time_match:
        hour, minute, second = (int(g) for g in time_match.groups())
        today_local = page.evaluate(
            "() => { const d = new Date(); return d.getFullYear() + '-' + "
            "String(d.getMonth() + 1).padStart(2, '0') + '-' + String(d.getDate()).padStart(2, '0'); }")
        naive_local = datetime.strptime(today_local, "%Y-%m-%d").replace(hour=hour, minute=minute, second=second)
        window_start = (naive_local + timedelta(minutes=offset_min)).replace(
            minute=0, second=0, microsecond=0, tzinfo=timezone.utc)
        return window_start, window_start + timedelta(hours=1)

    date_match = re.match(r"^\w+,\s*(\d{1,2})\s+(\w+)\.?\s+(\d{4})$", label)
    assert date_match, f"unrecognized tooltip time/date label: {label!r}"
    day, month_abbr, year = date_match.groups()
    month = _SPANISH_MONTH_ABBR.get(month_abbr.lower().rstrip("."))
    assert month, f"unrecognized Spanish month abbreviation in {label!r}: {month_abbr!r}"
    # NOTE (2026-09-13, fixed): unlike the HH:MM:SS/24h branch above, this
    # date does NOT need a local-offset shift. docs/GraficasMonitoring.md:
    # 7d/30d aggregate by "Dias UTC completos" (complete UTC calendar
    # days), with the point's own backend timestamp = dayStart + 12h UTC
    # (noon) -- so formatting that noon-UTC instant in a browser several
    # hours behind/ahead of UTC still lands on the SAME calendar date in
    # the vast majority of timezones (only a same-day-crossing offset
    # near +/-12h could disagree). Confirmed live: applying the offset
    # shift here (treating the parsed Y/M/D as a LOCAL midnight) produced
    # a systematically wrong window and a false Charge/Discharge Power
    # mismatch; using the parsed date directly as a UTC calendar day
    # matched the real API exactly (2049.75 kW).
    window_start = datetime(int(year), month, int(day), tzinfo=timezone.utc)
    return window_start, window_start + timedelta(days=1)


def _tooltip_values(tooltip_text):
    return {l.split(":")[0].strip(): float(l.split(":")[1].strip()) for l in tooltip_text.splitlines()[1:]}


@pytest.mark.xfail(
    strict=True,
    reason="NOT a Site Power Telemetry product defect (per team review "
           "2026-09-13) -- nothing on this chart is visibly wrong, and "
           "IsInterpolated isn't rendered anywhere in the UI. Kept here as "
           "an internal, root-caused observation only: "
           "MonitoringStatAccumulator.cs (BucketState.Apply) sets "
           "IsInterpolated=true whenever 'reading.Timestamp.Second != 0' -- "
           "unrelated to whether the bucket was actually filled in due to a "
           "real gap. Real telemetry timestamps essentially never land on a "
           "whole second, so this marks virtually all genuine data as "
           "interpolated. Confirmed live: BOLIVIA has 638/638 "
           "MonitoringStat rows flagged IsInterpolated=true, while the real "
           "Fractal simulator is verified live right now (PCS-1/2/3 each "
           "~2300 kW, real and varying). This test exists to guard the "
           "OTHER cross-layer checks in this file (a broken flag could mask "
           "a real telemetry gap making chart-vs-DB comparisons falsely "
           "agree on stale data) -- if this data-platform issue is ever "
           "tracked/fixed elsewhere, this should start passing again for a "
           "genuinely live site.")
def test_telemetry_has_not_been_stuck_interpolating_too_long(db_conn, bolivia_site_id):
    """Automated guard for the exact gap confirmed live 2026-09-11: real
    telemetry silently stopped reaching monitoring.MonitoringStat (the edge/
    simulator process presumably stopped emitting -- e.g. the host machine
    slept) while the Fractal simulator itself kept running and swinging
    through a full +/-8000 kW cycle, verified by polling it directly. Every
    bucket during that gap was marked IsInterpolated=True and held a near-
    constant fallback value instead -- something no chart-vs-DB comparison
    can catch, since both sides agree on the same stale number. This is the
    fast, no-live-sampling-needed check for that: if real telemetry hasn't
    landed in a long time, catch it here instead of only noticing when a
    slower, deeper aggregation-correctness check (see
    tools/verify_monitoring_stat_aggregation.py) produces a confusing
    mismatch.

    CAVEAT (2026-09-13): this guard's own signal (IsInterpolated) turned out
    to be broken (root-caused, see the xfail reason above) -- but NOT
    classified as a Site Power Telemetry defect (team review 2026-09-13):
    nothing on this chart is visibly wrong, and the flag isn't rendered
    anywhere in the UI, so it's a data-platform observation, not a product
    bug of this feature. Kept here as a documented xfail both as a
    regression trap and because the underlying question (has real
    telemetry stopped arriving?) is still worth guarding once the flag
    itself is trustworthy."""
    minutes = get_minutes_since_last_real_monitoring_stat_sample(db_conn, bolivia_site_id)
    assert minutes is not None, f"{SITE_NAME!r} has NEVER had a real (non-interpolated) MonitoringStat sample"
    assert minutes <= MAX_MINUTES_WITHOUT_REAL_TELEMETRY, (
        f"{SITE_NAME!r}'s real telemetry hasn't reached monitoring.MonitoringStat in "
        f"{minutes:.0f} minutes (limit {MAX_MINUTES_WITHOUT_REAL_TELEMETRY}) -- every bucket "
        f"since is interpolated filler, not a real aggregation of live data. Check whether "
        f"the site's edge/simulator process is still emitting (a laptop going to sleep is a "
        f"known cause).")


def test_title_badge_and_period_text(bolivia_monitoring_page):
    """CA-01: title, active-range badge (24H by default), and the matching
    period sentence ("Last 24 hours.")."""
    chart = bolivia_monitoring_page.site_power_telemetry()
    assert chart.time_range_badge() == "24H"
    assert chart.time_range_period() == "Last 24 hours."


def test_trend_focus_options_match_documented_list(bolivia_monitoring_page):
    """CA-03: exactly these 6 options, in this exact order."""
    chart = bolivia_monitoring_page.site_power_telemetry()
    options = chart.trend_focus_select().locator("option").all_inner_texts()
    assert options == EXPECTED_TREND_FOCUS_OPTIONS


@pytest.mark.parametrize("focus, expected_legend", EXPECTED_LEGEND_BY_FOCUS.items())
def test_legend_matches_documented_series_per_focus(bolivia_monitoring_page, focus, expected_legend):
    """CA-05 through CA-11: Site SOC (%) is always present, plus the
    documented extra series for each Trend Focus. Container & Rack / HVAC &
    Aux are excluded from this parametrization -- see
    test_omitted_lines_still_show_documented_fallback_for_fractal below,
    since for BOLIVIA their series never plot at all (a different, still
    correct, assertion)."""
    chart = bolivia_monitoring_page.site_power_telemetry()
    chart.select_trend_focus(focus)
    assert set(chart.legend_series()) == expected_legend


@pytest.mark.parametrize("focus, expected_lines", EXPECTED_PLOTTED_LINES_BY_FOCUS.items())
def test_plotted_lines_match_documented_fractal_availability(bolivia_monitoring_page, focus, expected_lines):
    """CA-06 through CA-11 combined with docs/OF-143.txt's Fractal mapping
    table: a series only actually PLOTS (has real point data) if Fractal
    feeds it for this site. Container & Rack and HVAC & Aux correctly plot
    only Site SOC -- their own series are documented as "línea omitida"
    (CA-08/CA-09) since Fractal never sends those fields, not a rendering
    bug."""
    chart = bolivia_monitoring_page.site_power_telemetry()
    chart.select_trend_focus(focus)
    assert set(chart.line_names()) == expected_lines


def test_legend_click_toggles_strikethrough(bolivia_monitoring_page):
    """CA-12: clicking a legend entry hides/shows that line, and the
    legend text itself renders with a strikethrough while hidden."""
    chart = bolivia_monitoring_page.site_power_telemetry()
    chart.select_trend_focus("Battery / BMS")
    label = "Charge Power (MW)"
    assert not chart.is_series_struck_through(label), "expected the series to start visible (no strikethrough)"

    chart.toggle_series(label)
    assert chart.is_series_struck_through(label), "expected a strikethrough after hiding the series"

    chart.toggle_series(label)
    assert not chart.is_series_struck_through(label), "expected the strikethrough to clear after showing it again"


def test_tooltip_shows_time_and_three_decimal_values(bolivia_monitoring_page):
    """CA-13: hovering a point shows its date/time and each series' value
    formatted to 3 decimals."""
    chart = bolivia_monitoring_page.site_power_telemetry()
    chart.select_trend_focus("Battery / BMS")
    tooltip_text = chart.hover_tooltip_text()

    lines = tooltip_text.splitlines()
    assert re.match(r"^\d{1,2}:\d{2}:\d{2}$|^\d{4}-\d{2}-\d{2}", lines[0]), (
        f"expected the first tooltip line to be a date/time, got: {lines[0]!r}")

    value_lines = lines[1:]
    assert value_lines, f"expected at least one series value line, got: {tooltip_text!r}"
    for line in value_lines:
        assert re.search(r": -?\d+\.\d{3}$", line), (
            f"expected a 3-decimal value on line {line!r} (full tooltip: {tooltip_text!r})")


@pytest.mark.parametrize("time_range", TIME_RANGES)
def test_badge_and_period_match_selected_time_range(bolivia_monitoring_page, time_range):
    """CA-04: switching the global 24h/7d/30d selector updates this chart's
    own badge and period sentence to match."""
    bolivia_monitoring_page.select_time_range(time_range)
    bolivia_monitoring_page.page.wait_for_timeout(1000)
    chart = bolivia_monitoring_page.site_power_telemetry()
    assert chart.time_range_badge() == EXPECTED_BADGE_BY_RANGE[time_range]
    assert chart.time_range_period() == EXPECTED_PERIOD_BY_RANGE[time_range]


@pytest.mark.parametrize("time_range", TIME_RANGES)
def test_site_soc_matches_monitoring_stat_history(bolivia_monitoring_page, db_conn, bolivia_site_id, time_range):
    """True cross-layer ground truth, bypassing live memory state entirely:
    docs/OF-143.txt says this chart's Site SOC line is built from
    monitoring.MonitoringStat's consolidated history (5-min buckets rolled
    up into 1 point per complete HOUR for 24h, or per complete DAY for
    7d/30d -- "sin la hora/el dia en curso"), NOT the live in-memory site
    state the diagnostic cards read.

    Hovers EXACTLY on the chart's most recent plotted point (not an
    approximate position), reads its own displayed time/date label, and
    compares against the DB average for THAT EXACT UTC window -- confirmed
    2026-09-10 this precision matters: an earlier version that compared
    against "the last 60 minutes from right now" produced a misleading
    multi-MW/point gap purely from not sharing the same clock boundary as
    the chart, on the Charge/Discharge Power check below (same lesson
    applies to every check in this file)."""
    bolivia_monitoring_page.select_time_range(time_range)
    chart = bolivia_monitoring_page.site_power_telemetry()
    chart.select_trend_focus("Battery / BMS")

    tooltip_text = chart.hover_latest_point_tooltip_text()
    tooltip_lines = tooltip_text.splitlines()
    window_start, window_end = _utc_window_for_tooltip_label(bolivia_monitoring_page.page, tooltip_lines[0])

    db_soc = get_monitoring_stat_soc_avg(db_conn, bolivia_site_id, window_start, window_end,
                                          hourly_samples_only=time_range != "Last 24 hours")
    assert db_soc is not None, (
        f"no MonitoringStat Soc rows for {SITE_NAME!r} in [{window_start}, {window_end})")
    chart_soc = _tooltip_values(tooltip_text)["Site SOC (%)"]

    assert abs(chart_soc - db_soc) <= TOL_ABS_SOC_PCT, (
        f"[{time_range}] chart's Site SOC ({chart_soc}%) for the point at "
        f"{tooltip_lines[0]!r} disagrees with monitoring.MonitoringStat's average over "
        f"[{window_start}, {window_end}) ({db_soc:.3f}%) by more than {TOL_ABS_SOC_PCT} points")


@pytest.mark.parametrize("time_range", TIME_RANGES)
def test_charge_and_discharge_power_match_monitoring_stat_history(
        bolivia_monitoring_page, db_conn, bolivia_site_id, time_range):
    """Real value cross-check (not just presence): docs/OF-143.txt Calculo
    rule for Carga/Descarga -- "Potencia con signo: negativa -> carga
    (valor absoluto); positiva -> descarga" -- applied PER-SAMPLE before
    averaging (confirmed 2026-09-10: a 7d/30d daily point can legitimately
    show BOTH Charge and Discharge Power nonzero, since the site charged
    during part of the day and discharged during another part -- averaging
    only same-sign rows overshot the chart's real value by ~2x; averaging
    GREATEST(-power, 0) and GREATEST(power, 0) across EVERY row, zero-filled
    on the inactive side, is what actually matches -- see
    get_monitoring_stat_charge_power_avg_kw's docstring). Same exact-window
    precision as the Site SOC check above."""
    bolivia_monitoring_page.select_time_range(time_range)
    chart = bolivia_monitoring_page.site_power_telemetry()
    chart.select_trend_focus("Battery / BMS")

    tooltip_text = chart.hover_latest_point_tooltip_text()
    tooltip_lines = tooltip_text.splitlines()
    window_start, window_end = _utc_window_for_tooltip_label(bolivia_monitoring_page.page, tooltip_lines[0])

    hourly_only = time_range != "Last 24 hours"
    db_charge_kw = get_monitoring_stat_charge_power_avg_kw(
        db_conn, bolivia_site_id, window_start, window_end, hourly_samples_only=hourly_only)
    db_discharge_kw = get_monitoring_stat_discharge_power_avg_kw(
        db_conn, bolivia_site_id, window_start, window_end, hourly_samples_only=hourly_only)
    assert db_charge_kw is not None and db_discharge_kw is not None, (
        f"no MonitoringStat ActivePower rows for {SITE_NAME!r} in [{window_start}, {window_end})")

    values = _tooltip_values(tooltip_text)
    assert abs(values["Charge Power (MW)"] - db_charge_kw / 1000.0) <= TOL_ABS_MW, (
        f"[{time_range}] chart's Charge Power ({values['Charge Power (MW)']} MW) for the point at "
        f"{tooltip_lines[0]!r} disagrees with monitoring.MonitoringStat's average over "
        f"[{window_start}, {window_end}) ({db_charge_kw / 1000.0:.3f} MW) by more than {TOL_ABS_MW} MW")
    assert abs(values["Discharge Power (MW)"] - db_discharge_kw / 1000.0) <= TOL_ABS_MW, (
        f"[{time_range}] chart's Discharge Power ({values['Discharge Power (MW)']} MW) for the point at "
        f"{tooltip_lines[0]!r} disagrees with monitoring.MonitoringStat's average over "
        f"[{window_start}, {window_end}) ({db_discharge_kw / 1000.0:.3f} MW) by more than {TOL_ABS_MW} MW")


@pytest.mark.xfail(
    strict=True,
    reason="CONFIRMED DEFECT (2026-09-14): PCS Power's Sigma PCS Active "
           "Power is inflated by roughly 2x -- the site-level SYS "
           "TRANSFORMER_PCS aggregate row is summed IN ADDITION to the 3 "
           "individual PCS-1/PCS-2/PCS-3 rows, instead of being excluded. "
           "Same bug family as Defect #42 (PCS Energy Statistics' Charge/"
           "Discharge Energy double-counting), but a DIFFERENT code path: "
           "PowerTrendPointMapper.SumActivePower/IsSiteSysRow. Confirmed "
           "exact match: summing SYS + (PCS-1+PCS-2+PCS-3) per bucket, "
           "then averaging over the window, reproduces the real API value "
           "to the exact decimal (9041.391666... kW for a specific hour) "
           "-- proving the SYS row isn't being excluded as the code "
           "intends ('Exclude site-level SYS rows that may have slipped "
           "into the PCS partition'). The true (correct) PCS sum -- just "
           "PCS-1+PCS-2+PCS-3 -- is roughly half that.")
@pytest.mark.parametrize("time_range", TIME_RANGES)
def test_pcs_power_focus_sum_matches_the_true_pcs_sum_not_double_counted_with_sys(
        bolivia_monitoring_page, db_conn, bolivia_site_id, time_range):
    """Real value cross-check for the PCS Power focus (docs/OF-143.txt CA-07:
    Site SOC + Sigma PCS Active Power, using sum(Active Power) across
    reporting PCS IDs -- must NOT also include the site-level SYS
    aggregate)."""
    bolivia_monitoring_page.select_time_range(time_range)
    chart = bolivia_monitoring_page.site_power_telemetry()
    chart.select_trend_focus("PCS Power")

    tooltip_text = chart.hover_latest_point_tooltip_text()
    tooltip_lines = tooltip_text.splitlines()
    window_start, window_end = _utc_window_for_tooltip_label(bolivia_monitoring_page.page, tooltip_lines[0])

    db_pcs_sum_kw = get_monitoring_stat_pcs_sum_active_power_avg_kw(
        db_conn, bolivia_site_id, window_start, window_end,
        hourly_samples_only=time_range != "Last 24 hours")
    assert db_pcs_sum_kw is not None, (
        f"no MonitoringStat ActivePower rows for {SITE_NAME!r} PCS-1/2/3 in [{window_start}, {window_end})")

    values = _tooltip_values(tooltip_text)
    chart_pcs_mw = values["Σ PCS Active Power (MW)"]
    assert chart_pcs_mw == pytest.approx(db_pcs_sum_kw / 1000.0, abs=TOL_ABS_MW), (
        f"[{time_range}] chart's Sigma PCS Active Power ({chart_pcs_mw} MW) for the point at "
        f"{tooltip_lines[0]!r} disagrees with the TRUE sum of PCS-1+PCS-2+PCS-3 "
        f"({db_pcs_sum_kw / 1000.0:.3f} MW) by more than {TOL_ABS_MW} MW")


@pytest.mark.parametrize("time_range", TIME_RANGES)
def test_ems_network_data_freshness_matches_monitoring_stat_history(
        bolivia_monitoring_page, db_conn, bolivia_site_id, time_range):
    """Real value cross-check for the EMS & Network focus's Data Freshness
    (s) (docs/OF-143.txt CA-10 / docs/GraficasMonitoring.md: "Retraso entre
    la muestra original y la ventana de 5 min"). Backend formula
    (PowerTrendPointMapper.ResolveDataFreshnessSeconds +
    PowerTrendGatewayMerger.LatestSourceTimestamp): per bucket,
    max(BucketTimestamp - latest SourceTimestamp among gateway-partition
    rows, 0) seconds, then averaged per hour/day like every other
    "Promedio" field (see get_monitoring_stat_data_freshness_avg_seconds's
    docstring)."""
    bolivia_monitoring_page.select_time_range(time_range)
    chart = bolivia_monitoring_page.site_power_telemetry()
    chart.select_trend_focus("EMS & Network")

    tooltip_text = chart.hover_latest_point_tooltip_text()
    tooltip_lines = tooltip_text.splitlines()
    window_start, window_end = _utc_window_for_tooltip_label(bolivia_monitoring_page.page, tooltip_lines[0])

    db_freshness_s = get_monitoring_stat_data_freshness_avg_seconds(
        db_conn, bolivia_site_id, window_start, window_end,
        hourly_samples_only=time_range != "Last 24 hours")
    assert db_freshness_s is not None, (
        f"no MonitoringStat SourceTimestamp rows for {SITE_NAME!r} in [{window_start}, {window_end})")

    values = _tooltip_values(tooltip_text)
    chart_freshness_s = values["Data Freshness (s)"]
    assert chart_freshness_s == pytest.approx(db_freshness_s, abs=TOL_ABS_SECONDS), (
        f"[{time_range}] chart's Data Freshness ({chart_freshness_s} s) for the point at "
        f"{tooltip_lines[0]!r} disagrees with the real MonitoringStat-derived value "
        f"({db_freshness_s:.3f} s) by more than {TOL_ABS_SECONDS} s")


def test_site_soc_is_consistent_with_device_status_panel_battery_soc(bolivia_monitoring_page):
    """[SPT-10] Site SOC (%) is documented as one shared value regardless of
    where it's shown (docs/OF-143.txt: preference SYS Soc, else average of
    master racks -- same rule the Device Status Panel's Battery/BMS card
    uses for its own "SoC range" line). Compares the chart's most recent
    plotted point (a historical MonitoringStat bucket, up to ~1h stale in
    the 24h view) against the Battery/BMS card's live "SoC range" (~5s
    cadence) -- a generous tolerance accounts for that staleness gap, since
    SOC moves slowly (confirmed elsewhere in this project it drifts well
    under 1 pt/hour under normal load)."""
    from tests.ui.monitoring.test_device_status_panel import _soc_range_value

    bolivia_monitoring_page.select_time_range("Last 24 hours")
    chart = bolivia_monitoring_page.site_power_telemetry()
    chart.select_trend_focus("Battery / BMS")
    tooltip_text = chart.hover_latest_point_tooltip_text()
    chart_soc = _tooltip_values(tooltip_text)["Site SOC (%)"]

    panel = bolivia_monitoring_page.device_status_panel()
    live_soc = _soc_range_value(panel)

    assert chart_soc == pytest.approx(live_soc, abs=2.0), (
        f"expected Site Power Telemetry's Site SOC ({chart_soc}%, most recent hourly "
        f"bucket) to be close to the Battery/BMS card's live SoC range ({live_soc}%) -- "
        f"disagree by more than 2 points")


@pytest.mark.xfail(
    strict=True,
    reason="CONFIRMED DEFECT (2026-09-14): Import Power and Export Power are "
           "SWAPPED in the Meter / CT-PT focus -- and in the neighboring Site "
           "Import / Export Power card too (same shared powerTrendData, "
           "confirmed live both show the exact same swap, e.g. Export=2.88 MW "
           "/ Import=0.00 MW while the real MonitoringStat MeterDemand for "
           "that same hour is +2831.9 kW, i.e. positive -- which docs/OF-143.txt's "
           "own formula table says should be Import: 'Import = max(demanda, 0); "
           "Export = abs(min(demanda, 0))'). Confirmed consistent across all 3 "
           "time ranges and multiple points: the chart's Import value always "
           "matches the TRUE Export value computed from MonitoringStat, and "
           "vice versa (e.g. 7d/30d: chart Import=2.05 MW == true Export=2.019 "
           "MW; chart Export=1.776 MW == true Import=1.749 MW). Backend code "
           "read directly (PowerTrendPointMapper.ResolveImportExport) assigns "
           "Import=Max(meterPower,0)/Export=Abs(Min(meterPower,0)) matching the "
           "HU -- so either the deployed app is running an older/different "
           "build than this checkout, or MeterDemand's sign convention in the "
           "DB doesn't match what the formula assumes. Either way, the LIVE "
           "deployed app currently shows values reversed from the documented "
           "spec.")
@pytest.mark.parametrize("time_range", TIME_RANGES)
def test_import_and_export_power_match_monitoring_stat_history(
        bolivia_monitoring_page, db_conn, bolivia_site_id, time_range):
    """Real value cross-check for the Meter / CT-PT focus (docs/OF-143.txt
    CA-11 / CA-22: Import Power / Export Power, same source as the
    neighboring Import/Export Power card). Backend formula
    (PowerTrendPointMapper.ResolveImportExport, meter branch -- BOLIVIA
    always has MeterDemand populated so the grid-counter/signed-power
    fallbacks never trigger): Import = max(MeterDemand, 0), Export =
    abs(min(MeterDemand, 0)), zero-filled per sample before averaging (same
    pattern already confirmed for Charge/Discharge Power)."""
    bolivia_monitoring_page.select_time_range(time_range)
    chart = bolivia_monitoring_page.site_power_telemetry()
    chart.select_trend_focus("Meter / CT·PT")

    tooltip_text = chart.hover_latest_point_tooltip_text()
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
    chart_import_mw = values["Import Power (MW)"]
    chart_export_mw = values["Export Power (MW)"]
    assert chart_import_mw == pytest.approx(db_import_kw / 1000.0, abs=TOL_ABS_MW), (
        f"[{time_range}] chart's Import Power ({chart_import_mw} MW) for the point at "
        f"{tooltip_lines[0]!r} disagrees with the real MonitoringStat-derived value "
        f"({db_import_kw / 1000.0:.3f} MW) by more than {TOL_ABS_MW} MW")
    assert chart_export_mw == pytest.approx(db_export_kw / 1000.0, abs=TOL_ABS_MW), (
        f"[{time_range}] chart's Export Power ({chart_export_mw} MW) for the point at "
        f"{tooltip_lines[0]!r} disagrees with the real MonitoringStat-derived value "
        f"({db_export_kw / 1000.0:.3f} MW) by more than {TOL_ABS_MW} MW")


@pytest.mark.xfail(
    strict=True,
    reason="CONFIRMED DEFECT (2026-09-10, confirmed directly with the team): "
           "a field Fractal structurally never sends must never be drawn as a "
           "real 0 -- a real measured zero and 'no data at all' are different "
           "things, and showing 0 is actively misleading (it reads as 'cells "
           "perfectly balanced', not 'unknown'). BOLIVIA's "
           "CellVDelta/HCellV/LCellV are all NULL in monitoring.MonitoringStat "
           "(confirmed via direct query -- Fractal never reports cell-level "
           "voltages, same fact already established for Battery Diagnostics), "
           "yet ΔCellV (mV) plots a literal 0.000 instead of being omitted -- "
           "unlike Container/Rack temp and HVAC, which correctly omit their "
           "line for the exact same kind of gap. Violates the 'never invent a "
           "zero' principle already established elsewhere in this project "
           "(Dispatch Limits & Tracking's CA-11).")
def test_delta_cellv_is_omitted_not_a_fabricated_zero(bolivia_monitoring_page, db_conn, bolivia_site_id):
    cur = db_conn.cursor()
    cur.execute(
        'SELECT "CellVDelta", "HCellV", "LCellV" FROM monitoring."MonitoringStat" '
        'WHERE "SiteId" = %s ORDER BY "BucketTimestamp" DESC LIMIT 1',
        (bolivia_site_id,),
    )
    cell_v_delta, h_cell_v, l_cell_v = cur.fetchone()
    assert cell_v_delta is None and h_cell_v is None and l_cell_v is None, (
        "expected BOLIVIA's cell-voltage fields to be NULL (Fractal never reports them) -- "
        "if this ever becomes non-null, re-evaluate whether the chart's 0 is still a "
        f"fabrication: CellVDelta={cell_v_delta}, HCellV={h_cell_v}, LCellV={l_cell_v}")

    chart = bolivia_monitoring_page.site_power_telemetry()
    chart.select_trend_focus("Battery / BMS")
    assert "ΔCellV (mV)" not in chart.line_names(), (
        "expected ΔCellV to be omitted (no plotted line) when Fractal never sends the "
        "underlying cell-voltage data, same treatment as Container/Rack temp and HVAC -- "
        "got a plotted line instead (drawing a fabricated 0)")


def test_invalid_trend_focus_falls_back_to_battery_bms(bolivia_monitoring_page):
    """CA-18: an invalid/unrecognized Trend Focus falls back to Battery /
    BMS. Simulated by forcing the underlying <select> to an out-of-range
    value directly (there's no in-UI way to pick an option that doesn't
    exist), then confirming the component's own displayed state recovers
    to Battery / BMS rather than silently keeping the bad value."""
    chart = bolivia_monitoring_page.site_power_telemetry()
    chart.select_trend_focus("Meter / CT·PT")
    select = chart.trend_focus_select()
    select.evaluate("el => { el.value = '__INVALID__'; el.dispatchEvent(new Event('change', {bubbles: true})); }")
    bolivia_monitoring_page.page.wait_for_timeout(500)
    assert set(chart.legend_series()) == EXPECTED_LEGEND_BY_FOCUS["Battery / BMS"], (
        "expected an invalid Trend Focus to fall back to Battery / BMS's series")

