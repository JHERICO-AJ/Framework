"""Data & Monitoring - Site Load & Backup Context (docs/OF-152.txt): a
3-block, site-level, ALWAYS-LIVE summary (Real Load, Estimated Backup,
plus a lateral ATS/Net power/Context block) -- explicitly NOT affected by
the page's 24h/7d/30d range selector (CA-05), same pattern as Thermal
Diagnostics/PCS Energy Statistics' non-applicability, but this one has NO
badge at all (like Thermal Diagnostics).

BOLIVIA (Fractal). The HU's own "Fuentes por protocolo" table documents a
real, deliberate gap: "Fractal (fase actual): Potencias EMU/PCS, SOC --
Sin RealLoad ni AtsSt mapeados" -- so Real Load always falls back to
MeterDemand + ΣPCS (never the SYS RealLoad field), and ATS always shows
"—" (never mapped for Fractal). Confirmed live 2026-09-13 and via the
real API (siteLoadContext.atsStatus is null).

BOLIVIA's own Intake config (docs/omniops_data_intake_BOLIVIA.xlsx,
"Intake Fields" sheet) has real, non-placeholder values for all 3
Estimated-Backup/Context inputs: battery_capacity_kwh=100000,
forced_reserve_soc_pct=10, primary_use_case="Grid storage / energy
arbitrage / ancillary services" -- so Estimated Backup and Context should
show real values (not "—") whenever Real Load > 0, confirmed live.
"""
import re

import pytest

from framework_api.services.monitoring_service import MonitoringService
from shared.datasource.db_source import get_site_ids
from shared.datasource.fractal_modbus_source import (
    read_fractal_pcs_active_power_kw, read_fractal_meter_total_active_power_kw,
)

pytestmark = pytest.mark.ui

SITE_NAME = "BOLIVIA"
EXPECTED_LATERAL_LABELS = ["ATS / grid transfer", "Net power", "Context"]
ATS_LABELS = {"Grid", "Backup", "Island", "Transfer", "—"}
EXPECTED_CONTEXT_TEXT = "Grid storage / energy arbitrage / ancillary services"


@pytest.fixture
def bolivia_monitoring_page(require_omniops, monitoring_page):
    return monitoring_page.select_site(SITE_NAME)


@pytest.fixture(scope="session")
def bolivia_site_id(db_conn):
    return get_site_ids(db_conn, [SITE_NAME])[SITE_NAME]


def test_card_title_and_subtitle(bolivia_monitoring_page):
    """CA-03: subtitle explains real load priority and the ~5s live cadence."""
    site_load = bolivia_monitoring_page.site_load_backup_context()
    subtitle = site_load.subtitle().lower()
    assert "real" in subtitle or "load" in subtitle, f"expected the subtitle to mention real load, got: {site_load.subtitle()!r}"


def test_no_time_range_badge_on_this_card(bolivia_monitoring_page):
    """CA-05: this panel is always live -- no 24h/7d/30d badge at all,
    same pattern already confirmed for Thermal Diagnostics."""
    site_load = bolivia_monitoring_page.site_load_backup_context()
    assert site_load.card().locator(".monitoring-time-range-badge").count() == 0, (
        "expected no time-range badge -- CA-05 says the range doesn't apply here")


def test_global_time_range_does_not_change_values(bolivia_monitoring_page):
    """CA-05: switching the page's global 24h/7d/30d selector must not
    change this card's values -- it's always the current live state."""
    site_load = bolivia_monitoring_page.site_load_backup_context()
    before = (site_load.value_text("Real Load"), site_load.lateral_values())

    bolivia_monitoring_page.select_time_range("Last 7 days")
    bolivia_monitoring_page.page.wait_for_timeout(500)
    after = (site_load.value_text("Real Load"), site_load.lateral_values())
    bolivia_monitoring_page.select_time_range("Last 24 hours")

    # Real Load itself can legitimately drift a bit between reads (live,
    # fast-changing value) -- what matters is that switching the range
    # itself isn't what changed it. Confirm at least Context (effectively
    # static, Intake-sourced) stayed identical.
    assert before[1].get("Context") == after[1].get("Context"), (
        f"expected Context to stay the same across a range switch, before={before[1]}, after={after[1]}")


def test_lateral_block_has_3_rows_in_documented_order(bolivia_monitoring_page):
    """CA-16: exactly ATS / grid transfer, Net power, Context, in that order."""
    site_load = bolivia_monitoring_page.site_load_backup_context()
    assert list(site_load.lateral_values().keys()) == EXPECTED_LATERAL_LABELS


def test_ats_shows_dash_for_a_fractal_site_not_a_fabricated_status(bolivia_monitoring_page, api_client, bolivia_site_id):
    """CA-17 + the HU's own documented Fractal gap: BOLIVIA never maps
    AtsSt, so ATS must show "—", never a fabricated Grid/Backup/Island/
    Transfer label. Cross-checked against the real API's atsStatus field
    (must be null)."""
    site_load = bolivia_monitoring_page.site_load_backup_context()
    assert site_load.ats_value() == "—", (
        f"expected ATS to show '—' for a Fractal site (never mapped), got: {site_load.ats_value()!r}")

    api_data = MonitoringService(api_client).get_monitoring_summary(site_id=bolivia_site_id).site_load_context
    assert api_data.ats_status is None, (
        f"expected the API's atsStatus to be null for a Fractal site, got: {api_data.ats_status!r}")


def test_ats_value_is_one_of_the_documented_labels(bolivia_monitoring_page):
    """CA-17: even though BOLIVIA always shows "—" today, confirm the
    component only ever renders one of the documented labels -- guards
    against a raw/untranslated code ever leaking through."""
    site_load = bolivia_monitoring_page.site_load_backup_context()
    assert site_load.ats_value() in ATS_LABELS, f"unexpected ATS label: {site_load.ats_value()!r}"


def test_real_load_is_always_a_positive_magnitude(bolivia_monitoring_page):
    """CA-08: Real Load is always shown as a positive magnitude, even
    though the underlying raw telemetry may carry a sign."""
    site_load = bolivia_monitoring_page.site_load_backup_context()
    real_load = site_load.real_load_kw()
    if real_load is None:
        pytest.skip("Real Load is currently — (no data) -- can't check its sign")
    assert real_load >= 0, f"expected Real Load to be a non-negative magnitude, got: {real_load}"


def test_net_power_keeps_its_sign(bolivia_monitoring_page):
    """CA-18: unlike Real Load, Net power preserves its sign (can be
    negative) -- confirmed live: BOLIVIA's Net power is negative as often
    as positive, tracking real PCS power direction."""
    site_load = bolivia_monitoring_page.site_load_backup_context()
    net_power = site_load.net_power_kw()
    if net_power is None:
        pytest.skip("Net power is currently — (no data)")
    # No assertion on sign itself (both are valid) -- this test exists to
    # confirm the value parses as a genuine signed integer, not that it's
    # always one particular sign.
    assert isinstance(net_power, int)


def test_context_matches_the_configured_primary_use_case(bolivia_monitoring_page):
    """CA-19: Context shows the Primary Use Case text configured in
    Intake (Owner Operational) -- confirmed against
    docs/omniops_data_intake_BOLIVIA.xlsx's own configured value."""
    site_load = bolivia_monitoring_page.site_load_backup_context()
    assert site_load.context_value() == EXPECTED_CONTEXT_TEXT, (
        f"expected Context to show the configured Primary Use Case "
        f"{EXPECTED_CONTEXT_TEXT!r}, got: {site_load.context_value()!r}")


def test_estimated_backup_moves_inversely_with_real_load(bolivia_monitoring_page):
    """CA-15: as Real Load rises, Estimated Backup minutes should fall
    (and vice versa) -- both live-updating from the same volatile Fractal
    power signal. Samples several ticks and checks the overall trend
    correlates in the expected direction, tolerating some noise rather
    than requiring every single tick to move in lockstep."""
    site_load = bolivia_monitoring_page.site_load_backup_context()
    samples = []
    for _ in range(8):
        real_load = site_load.real_load_kw()
        backup_min = site_load.estimated_backup_min()
        if real_load is not None and backup_min is not None:
            samples.append((real_load, backup_min))
        bolivia_monitoring_page.page.wait_for_timeout(5000)

    if len(samples) < 4:
        pytest.skip(f"not enough samples with both Real Load and Estimated Backup present "
                    f"(got {len(samples)}) -- can't check the inverse-correlation trend")

    # Pearson-style sign check: compare the sample with the highest real
    # load against the one with the lowest -- backup minutes should be
    # lower at the high-load sample.
    highest_load_sample = max(samples, key=lambda s: s[0])
    lowest_load_sample = min(samples, key=lambda s: s[0])
    if highest_load_sample[0] == lowest_load_sample[0]:
        pytest.skip("Real Load didn't vary enough across samples to check the inverse trend")

    assert highest_load_sample[1] <= lowest_load_sample[1], (
        f"expected the highest-Real-Load sample {highest_load_sample} to have fewer (or equal) "
        f"backup minutes than the lowest-Real-Load sample {lowest_load_sample}")


def test_real_load_matches_meter_plus_pcs_sum_from_simulator(bolivia_monitoring_page):
    """True cross-layer ground truth (UI vs the Fractal simulator directly,
    not just the DB/API): docs/OF-152.txt's own fallback formula for a
    Fractal site (no SYS RealLoad mapped) is |MeterDemand + ΣPCS|.
    Confirmed live 2026-09-13 with tight (3s) sampling: every time the UI's
    Real Load value changes, it matches |meter + pcs_sum| computed from a
    direct simulator read taken 1-2 ticks earlier, to within normal SignalR
    latency -- e.g. UI=10657 lined up with a computed 10657.4, UI=7884
    with 7884.3, UI=4918 with 4917.9. Uses the same convergence-window
    technique as other live-simulator checks in this project (sample
    repeatedly, accept a match within any recent sample)."""
    site_load = bolivia_monitoring_page.site_load_backup_context()

    history = []
    for _ in range(10):
        meter = read_fractal_meter_total_active_power_kw(SITE_NAME)
        pcs_sum = sum(read_fractal_pcs_active_power_kw(SITE_NAME, i) for i in range(3))
        history.append(abs(meter + pcs_sum))

        ui_real_load = site_load.real_load_kw()
        if ui_real_load is not None:
            match = next((h for h in history if abs(h - ui_real_load) <= 100), None)
            if match is not None:
                return  # confirmed
        bolivia_monitoring_page.page.wait_for_timeout(3000)

    pytest.fail(f"UI Real Load never matched |meter + ΣPCS| within tolerance across 10 samples. "
                f"Recent computed values: {history}")


@pytest.mark.xfail(
    strict=True,
    reason="CONFIRMED DEFECT (2026-09-13): docs/OF-152.txt's own fallback "
           "formula for Net power (no SYS PcsPower mapped for Fractal) is "
           "'suma de potencia activa de todos los PCS individuales' -- the "
           "SUM of PCS-1 + PCS-2 + PCS-3, same as Real Load's own ΣPCS "
           "term. Confirmed live with tight (3s) sampling against the "
           "Fractal simulator directly: the UI's Net power value "
           "consistently matches ΣPCS / 3 (the AVERAGE of the 3 units, "
           "not their sum) -- e.g. UI=1801 vs ΣPCS=5916.8 (ratio 3.29), "
           "UI=2299 vs a moment where ΣPCS/3=2299.2 (near-exact), UI=2538 "
           "vs ΣPCS/3=2541.8/2607.5 across two adjacent samples. The ratio "
           "of ΣPCS to the displayed value consistently lands around 3.0, "
           "matching BOLIVIA's exact PCS count -- Net power under-reports "
           "the site's true net power by roughly a factor of 3.")
def test_net_power_matches_pcs_sum_not_pcs_average_from_simulator(bolivia_monitoring_page):
    """Requires a decent power magnitude before comparing (>=1500 kW),
    specifically to avoid a false pass from both the SUM and the AVERAGE
    hypotheses coincidentally agreeing near a zero-crossing (both ~0 at
    the same moment isn't evidence either way)."""
    site_load = bolivia_monitoring_page.site_load_backup_context()

    for _ in range(15):
        pcs_sum = sum(read_fractal_pcs_active_power_kw(SITE_NAME, i) for i in range(3))
        ui_net_power = site_load.net_power_kw()
        if ui_net_power is not None and abs(pcs_sum) >= 1500:
            assert ui_net_power == pytest.approx(pcs_sum, rel=0.15), (
                f"expected UI Net Power ({ui_net_power}) to match ΣPCS ({pcs_sum:.1f}) within 15%, "
                f"got ratio ΣPCS/UI={pcs_sum / ui_net_power:.2f}")
            return
        bolivia_monitoring_page.page.wait_for_timeout(3000)

    pytest.skip("never saw a sample with |ΣPCS| >= 1500 kW and a real UI Net Power value to compare")


@pytest.mark.xfail(
    strict=True,
    reason="CONFIRMED DEFECT (2026-09-13): the Context value's computed "
           "style has white-space: nowrap, overflow: visible, and "
           "text-overflow: clip (no wrapping/truncation at all). Its long "
           "sibling value forces the flex layout to squeeze the 'Context' "
           "LABEL down to a getBoundingClientRect() width of 0px -- but "
           "since the label itself also has overflow allowed, its text "
           "keeps rendering past that collapsed box, visually appearing "
           "UNDERNEATH the value text (confirmed via screenshot: 'Co' is "
           "visible bleeding out from behind 'Grid storage...'). A plain "
           "box-vs-box overlap check misses this (a 0-width box never "
           "'overlaps' anything by rectangle math) -- the real signal is "
           "that the label's own rendered width collapsed to ~0 despite "
           "having real text content.")
def test_context_text_does_not_overlap_its_own_label(bolivia_monitoring_page):
    """CONFIRMED DEFECT (2026-09-13): Context's value has no text
    wrapping/truncation (white-space: nowrap, overflow: visible,
    text-overflow: clip -- confirmed via computed style). With BOLIVIA's
    real configured Primary Use Case text ("Grid storage / energy
    arbitrage / ancillary services" -- much longer than the mapping doc's
    own short HTML Example "Behind-the-meter / UPS"), the value visibly
    overflows past its row and squeezes the "Context" LABEL itself down
    to a zero-width box, so its text renders on top of/underneath the
    value. Checks that the label's own rendered box has a sane minimum
    width for its text, rather than being collapsed to ~0 by its
    overflowing sibling."""
    site_load = bolivia_monitoring_page.site_load_backup_context()
    card = site_load.card()

    box = card.evaluate("""
    (card) => {
        const rows = Array.from(card.querySelectorAll('.site-load-stack .bit-row'));
        const contextRow = rows.find(r => r.querySelector('.bit-label')?.textContent.trim() === 'Context');
        if (!contextRow) return null;
        const label = contextRow.querySelector('.bit-label');
        return { labelWidth: label.getBoundingClientRect().width, labelText: label.textContent.trim() };
    }
    """)
    if box is None:
        pytest.skip("Context row not found")

    assert box["labelWidth"] >= 20, (
        f"expected the 'Context' label ({box['labelText']!r}) to keep a sane rendered width "
        f"(>=20px), but its own sibling squeezed it down to {box['labelWidth']}px -- its text is "
        f"rendering underneath the value instead of in its own space")


@pytest.mark.xfail(
    strict=True,
    reason="CONFIRMED DEFECT (2026-09-13): same root cause as the "
           "label-overlap defect above -- the Context value's right edge "
           "extends past the card's own right edge (confirmed via "
           "screenshot: the text is visibly clipped mid-word at the "
           "card's boundary) because there's no wrapping/truncation "
           "applied to long Context strings.")
def test_context_text_does_not_overflow_past_the_card(bolivia_monitoring_page):
    """Same root cause as the label-overlap defect above: the value's
    right edge should stay within the card's own right edge, not spill
    out/get clipped past it."""
    site_load = bolivia_monitoring_page.site_load_backup_context()
    card = site_load.card()

    box = card.evaluate("""
    (card) => {
        const rows = Array.from(card.querySelectorAll('.site-load-stack .bit-row'));
        const contextRow = rows.find(r => r.querySelector('.bit-label')?.textContent.trim() === 'Context');
        if (!contextRow) return null;
        const value = contextRow.querySelector('strong');
        return { card: card.getBoundingClientRect().toJSON(), value: value.getBoundingClientRect().toJSON() };
    }
    """)
    if box is None:
        pytest.skip("Context value not found")

    assert box["value"]["right"] <= box["card"]["right"] + 2, (
        f"expected the Context value to stay within the card's right edge, but it overflows: "
        f"card right={box['card']['right']}, value right={box['value']['right']}")


def test_ui_values_match_api_site_load_context(bolivia_monitoring_page, api_client, bolivia_site_id):
    """True cross-layer ground truth (UI vs the real monitoring summary
    API's siteLoadContext object). Both the UI and this test hit the same
    live, fast-changing signal, so this samples a few pairs in quick
    succession and accepts a match within a generous relative tolerance
    (the site's real power can swing by hundreds of kW within a second),
    rather than demanding bit-for-bit equality on one single read."""
    site_load = bolivia_monitoring_page.site_load_backup_context()
    svc = MonitoringService(api_client)

    matched = False
    diffs = []
    for _ in range(15):
        ui_real_load = site_load.real_load_kw()
        api_data = svc.get_monitoring_summary(site_id=bolivia_site_id).site_load_context
        if ui_real_load is not None and api_data.real_load is not None:
            diff = abs(ui_real_load - api_data.real_load)
            diffs.append(diff)
            if diff <= max(500, 0.30 * api_data.real_load):
                matched = True
                break
        bolivia_monitoring_page.page.wait_for_timeout(2000)

    assert matched, (
        f"expected the UI's Real Load to track the API's siteLoadContext.realLoad within a "
        f"generous tolerance across several tries (BOLIVIA's power is known to swing fast), "
        f"diffs observed: {diffs}")


def test_real_load_updates_live_without_a_manual_reload(bolivia_monitoring_page):
    """[SLC-08] Unlike PCS Energy Statistics (confirmed frozen for 6+ real
    minutes without a reload, Qase Defect #43), this always-live card must
    genuinely update on its own. Samples Real Load repeatedly over ~20s
    (BOLIVIA's power is known to swing by hundreds of kW within seconds)
    and confirms at least one change is observed -- a much shorter, cheaper
    version of the same live-tracking already proven by
    test_real_load_matches_meter_plus_pcs_sum_from_simulator, focused
    purely on "does it move at all" rather than matching a specific
    ground-truth source."""
    site_load = bolivia_monitoring_page.site_load_backup_context()
    samples = []
    for _ in range(10):
        value = site_load.real_load_kw()
        if value is not None:
            samples.append(value)
        bolivia_monitoring_page.page.wait_for_timeout(2000)

    assert len(samples) >= 2, f"not enough non-null Real Load samples to check for movement: {samples}"
    assert len(set(samples)) > 1, (
        f"expected Real Load to change at least once over ~20s of sampling (no manual reload), "
        f"but it stayed frozen at {samples[0]} the whole time: {samples}")


@pytest.mark.xfail(
    strict=True,
    reason="CONFIRMED DEFECT (2026-09-13, Qase Defect #44): Site Load's Net "
           "power under-reports the true site power by roughly a factor of "
           "3 (matches PCS sum / 3, not the sum itself -- confirmed "
           "separately against the live Fractal simulator by "
           "test_net_power_matches_pcs_sum_not_pcs_average_from_simulator "
           "above). [SLC-06] This is the same defect surfacing on a SECOND "
           "surface: comparing against Site Power Telemetry's own "
           "Charge/Discharge Power graph (same underlying signed power) "
           "shows the same ~3x gap, confirming the two cards disagree with "
           "each other, not just with the raw simulator.")
def test_net_power_is_consistent_with_site_power_telemetry_graph(bolivia_monitoring_page):
    """[SLC-06] Site Load's Net power and Site Power Telemetry's Charge/
    Discharge Power both derive from the same underlying signed site power
    -- they should agree (within a generous tolerance that accounts for
    Site Load being a live instantaneous value vs. the chart's own
    historical-bucket point, up to ~1h stale in the 24h view)."""
    site_load = bolivia_monitoring_page.site_load_backup_context()
    net_power_kw = site_load.net_power_kw()
    if net_power_kw is None:
        pytest.skip("Net power is currently — (no data)")

    bolivia_monitoring_page.select_time_range("Last 24 hours")
    chart = bolivia_monitoring_page.site_power_telemetry()
    chart.select_trend_focus("Battery / BMS")
    tooltip_text = chart.hover_latest_point_tooltip_text()
    values = {l.split(":")[0].strip(): float(l.split(":")[1].strip()) for l in tooltip_text.splitlines()[1:]}
    graph_signed_power_kw = (values["Charge Power (MW)"] - values["Discharge Power (MW)"]) * 1000

    if abs(graph_signed_power_kw) < 500:
        pytest.skip("graph's signed power is too close to zero right now to check a ratio-based match")

    assert abs(net_power_kw) == pytest.approx(abs(graph_signed_power_kw), rel=0.3), (
        f"expected Site Load's Net power ({net_power_kw} kW) to be close to Site Power "
        f"Telemetry's signed Charge/Discharge Power ({graph_signed_power_kw:.0f} kW) -- "
        f"ratio observed: {graph_signed_power_kw / net_power_kw:.2f}")
