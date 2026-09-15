"""Data & Monitoring - language consistency: the platform is an English-only
system (confirmed by the user), so no screen should ever render Spanish
text -- including dates. This is specifically about the "Browse history"
modal's date rendering (Event Log and Alarm History share the exact same
modal component, so both are checked), plus a standing regression guard
that scans each Data & Monitoring card for any Spanish month/day
abbreviation leaking into visible text.

CONFIRMED DEFECT (2026-09-11): the modal's day-range <select> options and
its own 7d/30d row "D month YYYY, HH:MM:SS" format both render using the
browser's Spanish locale (es-ES-shaped abbreviations: "s�b, 5 sept 2026",
"11 sept 2026, 11:05:37") instead of English ("Sat, Sep 5, 2026" / "Sep 11,
2026, 11:05:37") -- almost certainly a bare toLocaleDateString()/
toLocaleString() call with no explicit 'en-US' locale argument, picking up
the OS/browser's locale instead of hardcoding the platform's own English-only
language policy.
"""
import re

import pytest

pytestmark = pytest.mark.ui

SITE_NAME = "BOLIVIA"

# Spanish weekday/month abbreviations that must never appear in this
# English-only platform's rendered text (confirmed live: "sept", "sáb",
# "dom", "mié", etc.) -- deliberately excludes ambiguous 3-letter forms
# that collide with real English words/abbreviations (e.g. "may").
SPANISH_DATE_TOKENS = re.compile(
    r"\b(ene|abr|ago|sept?|dic|lun|mié|mie|jue|vié|vie|sáb|sab|dom)\b",
    re.IGNORECASE,
)


@pytest.fixture
def bolivia_monitoring_page(require_omniops, monitoring_page):
    return monitoring_page.select_site(SITE_NAME)


@pytest.mark.parametrize("card_getter", ["event_log", "alarm_history"])
@pytest.mark.xfail(
    strict=True,
    reason="CONFIRMED DEFECT (2026-09-11): the Browse history modal's "
           "day-range dropdown options render Spanish weekday/month "
           "abbreviations (e.g. 'sáb, 5 sept 2026') instead of English, "
           "on an English-only platform. Same shared modal component for "
           "both Event Log and Alarm History, so both reproduce it "
           "identically.")
def test_day_range_dropdown_options_are_in_english(bolivia_monitoring_page, card_getter):
    card = getattr(bolivia_monitoring_page, card_getter)()
    modal = card.open_browse_history()
    try:
        modal.select_window("Last 7 days")
        modal.page.wait_for_timeout(500)
        options = modal.page.locator("select.monitoring-modal-day-range-select").first.locator("option")
        texts = [options.nth(i).inner_text().strip() for i in range(options.count())]
        assert texts, "expected at least 1 day-range option"
        spanish_hits = [t for t in texts if SPANISH_DATE_TOKENS.search(t)]
        assert not spanish_hits, (
            f"expected all-English day-range option text, found Spanish-looking "
            f"tokens in: {spanish_hits!r} (all options: {texts!r})")
    finally:
        modal.close()


@pytest.mark.parametrize("card_getter", ["event_log", "alarm_history"])
@pytest.mark.xfail(
    strict=True,
    reason="CONFIRMED DEFECT (2026-09-11): the modal's 7d/30d full-datetime "
           "row format ('D month YYYY, HH:MM:SS') renders the month "
           "abbreviation in Spanish (e.g. '11 sept 2026, 11:05:37') instead "
           "of English ('Sep 11, 2026, 11:05:37' or similar). Same shared "
           "modal component for both Event Log and Alarm History.")
def test_7d_30d_row_datetime_is_in_english(bolivia_monitoring_page, card_getter):
    card = getattr(bolivia_monitoring_page, card_getter)()
    modal = card.open_browse_history()
    try:
        modal.select_window("Last 7 days")
        if modal.row_count() == 0:
            pytest.skip(f"no rows in the 7d window for {SITE_NAME}")
        full_datetime = modal.row_time_datetime(0)
        assert full_datetime, f"expected a full-datetime string in row 0, got: {full_datetime!r}"
        assert not SPANISH_DATE_TOKENS.search(full_datetime), (
            f"expected an English month abbreviation, got a Spanish-looking "
            f"one in: {full_datetime!r}")
    finally:
        modal.close()


@pytest.mark.xfail(
    strict=True,
    reason="CONFIRMED DEFECT (2026-09-11): a THIRD surface for the same root "
           "cause -- Telemetry Data Table's 'Browse snapshots' modal (a "
           "DIFFERENT component from Event Log/Alarm History's 'Browse "
           "history', with no day-range filter at all) still renders every "
           "row's Timestamp with a Spanish month abbreviation (e.g. "
           "'11 sept 2026, 11:30:00') instead of English. Confirms this "
           "isn't isolated to the shared modal's day-range dropdown -- "
           "whatever date-formatting call is used platform-wide for these "
           "modals defaults to the browser/OS locale instead of hardcoding "
           "English.")
def test_snapshots_modal_row_timestamp_is_in_english(bolivia_monitoring_page):
    table = bolivia_monitoring_page.telemetry_data_table()
    table.wait_for_rows()
    modal = table.browse_snapshots()
    try:
        modal.wait_for_rows()
        if modal.row_count() == 0:
            pytest.skip(f"no rows in the snapshots modal for {SITE_NAME}")
        timestamp = modal.row_values(0)["Timestamp"]
        assert not SPANISH_DATE_TOKENS.search(timestamp), (
            f"expected an English month abbreviation in the snapshot row's "
            f"Timestamp, got a Spanish-looking one in: {timestamp!r}")
    finally:
        modal.close()


@pytest.mark.xfail(
    strict=True,
    reason="CONFIRMED DEFECT (2026-09-14): a FOURTH surface for the same "
           "root cause -- Site Power Telemetry's own chart tooltip (7d/30d "
           "views) renders its date label with a Spanish weekday/month "
           "abbreviation (e.g. 'dom, 13 sept 2026') instead of English, on "
           "this English-only platform. Not caught by the page-wide "
           "Spanish-text guard below because the tooltip only exists in "
           "the DOM while actively hovering a point -- it's absent from a "
           "static page scan.")
def test_chart_tooltip_date_label_is_in_english(bolivia_monitoring_page):
    chart = bolivia_monitoring_page.site_power_telemetry()
    chart.select_trend_focus("Battery / BMS")
    bolivia_monitoring_page.select_time_range("Last 7 days")

    tooltip_text = chart.hover_latest_point_tooltip_text()
    date_label = tooltip_text.splitlines()[0]
    assert not SPANISH_DATE_TOKENS.search(date_label), (
        f"expected an English date label on the Site Power Telemetry chart's tooltip, got a "
        f"Spanish-looking one: {date_label!r}")


@pytest.mark.xfail(
    strict=True,
    reason="CONFIRMED DEFECT (2026-09-14): a FIFTH surface for the same root "
           "cause -- the neighboring 'Site Import / Export Power' card's own "
           "chart tooltip (7d/30d views) ALSO renders its date label with a "
           "Spanish weekday/month abbreviation (e.g. 'dom, 13 sept 2026') "
           "instead of English, same as Site Power Telemetry's own tooltip. "
           "Not caught by the page-wide Spanish-text guard below because the "
           "tooltip only exists in the DOM while actively hovering a point.")
def test_import_export_card_tooltip_date_label_is_in_english(bolivia_monitoring_page):
    card = bolivia_monitoring_page.site_import_export_power()
    bolivia_monitoring_page.select_time_range("Last 7 days")

    tooltip_text = card.hover_latest_point_tooltip_text()
    date_label = tooltip_text.splitlines()[0]
    assert not SPANISH_DATE_TOKENS.search(date_label), (
        f"expected an English date label on the Site Import/Export Power card's tooltip, got a "
        f"Spanish-looking one: {date_label!r}")


def test_no_spanish_text_visible_on_data_and_monitoring_page(bolivia_monitoring_page):
    """Standing regression guard (not itself a reproduction of the dropdown/
    row-format defects above, which need the modal open): scans the whole
    Data & Monitoring page's visible text for Spanish month/day
    abbreviations. Passes today outside the 2 known modal defects above --
    kept passing so any NEW Spanish-text leak elsewhere on this page gets
    caught immediately instead of waiting for another manual report."""
    page = bolivia_monitoring_page.page
    page.wait_for_timeout(1000)
    visible_text = page.evaluate("() => document.body.innerText")
    hits = [line.strip() for line in visible_text.split("\n") if SPANISH_DATE_TOKENS.search(line)]
    assert not hits, f"found Spanish-looking date text outside any modal: {hits!r}"
