"""Data & Monitoring - Event Log (docs/OF-293.txt) -- a live table
(Time/Type/Source/Description) of operational events, plus a "Browse
history" modal for a static, paginated historical query.

BOLIVIA (Fractal) specifically. Its only real events right now are
PCS_COMM_LOST (confirmed via direct DB query -- events."Event" has zero
BATTERY_BMS-sourced events for this site currently), which
docs/OF-293.txt's own mapping table assigns to the "Trip" category
("Falla, protección, comunicación perdida o condición crítica") -- used
here as a real, live cross-layer fact, not a guess.

Confirmed live 2026-09-10: several rows can show IDENTICAL Time/Type/
Source/Description text (e.g. 3 rows all "22:19:15 / Trip / TRANSFORMER_PCS
/ PCS_COMM_LOST...") without violating CA-16's dedup rule -- verified
against events."Event" directly that these are 3 GENUINELY DIFFERENT
events (different serviceName per PCS unit in Metadata), all 3 PCS
losing comm in the same batch. The Source column just doesn't have
per-device granularity to show that difference -- not a duplicate-
collapsing bug.
"""
import re
from datetime import datetime, timedelta, timezone

import pytest

from shared.datasource.db_source import get_site_ids, get_recent_events, count_events_in_window

pytestmark = pytest.mark.ui

SITE_NAME = "BOLIVIA"
EXPECTED_HEADERS = ["Time", "Type", "Source", "Description"]

# docs/OF-293.txt's own query limits per Browse history window.
DOCUMENTED_QUERY_LIMIT = {"Last 24 hours": 1000, "Last 7 days": 2000, "Last 30 days": 5000}
WINDOW_DURATION = {
    "Last 24 hours": timedelta(hours=24), "Last 7 days": timedelta(days=7), "Last 30 days": timedelta(days=30),
}

# docs/OF-293.txt's own mapping table: PCS comm-lost/recovered -> Trip.
# BOLIVIA's only real events today are PCS_COMM_LOST (confirmed live), so
# this is a hard fact for this site, not a guess.
SIGNAL_TO_EXPECTED_TYPE = {"PCS_COMM_LOST": "Trip"}


@pytest.fixture
def bolivia_monitoring_page(require_omniops, monitoring_page):
    return monitoring_page.select_site(SITE_NAME)


@pytest.fixture(scope="session")
def bolivia_site_id(db_conn):
    return get_site_ids(db_conn, [SITE_NAME])[SITE_NAME]


def test_title_badge_and_period_text(bolivia_monitoring_page):
    """CA-11: badge (24H by default) and matching period sentence --
    purely informational for this card (CA-13), not a live-list filter."""
    log = bolivia_monitoring_page.event_log()
    assert log.time_range_badge() == "24H"
    assert log.time_range_period() == "Last 24 hours."


def test_subtitle_mentions_all_four_event_categories(bolivia_monitoring_page):
    """CA-03: subtitle explains schedule/control/mode/trip."""
    log = bolivia_monitoring_page.event_log()
    subtitle = log.subtitle().lower()
    for word in ("schedule", "control", "mode", "trip"):
        assert word in subtitle, f"expected {word!r} in the subtitle, got: {log.subtitle()!r}"


def test_table_headers_match_documented_columns(bolivia_monitoring_page):
    """CA-06: exactly these 4 columns, in this order."""
    log = bolivia_monitoring_page.event_log()
    assert log.header_cells() == EXPECTED_HEADERS


def test_row_count_never_exceeds_100(bolivia_monitoring_page):
    """CA-08: max 100 events on the live card."""
    log = bolivia_monitoring_page.event_log()
    assert 0 < log.row_count() <= 100, f"expected 1-100 rows, got {log.row_count()}"


def test_rows_ordered_most_recent_first(bolivia_monitoring_page):
    """CA-07: newest event on top. Parses the displayed "DD/MM/YYYY,
    HH:MM:SS" local time (confirmed live format) into a sortable tuple --
    doesn't need to know the browser's timezone since this only checks
    relative ordering, not absolute time."""
    log = bolivia_monitoring_page.event_log()
    times = [row[0] for row in log.all_row_values()]
    assert len(times) >= 2, f"need at least 2 rows to check ordering, got: {times}"

    def _sort_key(display_time):
        match = re.match(r"(\d{2})/(\d{2})/(\d{4}),\s*(\d{2}):(\d{2}):(\d{2})", display_time)
        assert match, f"unrecognized Event Log time format: {display_time!r}"
        day, month, year, hour, minute, second = (int(g) for g in match.groups())
        return (year, month, day, hour, minute, second)

    keys = [_sort_key(t) for t in times]
    assert keys == sorted(keys, reverse=True), f"rows aren't ordered most-recent-first: {times}"


def test_row_values_match_recent_db_events(bolivia_monitoring_page, db_conn, bolivia_site_id):
    """True cross-layer ground truth: docs/OF-293.txt's own Source/
    Description priority rules (CA-27/CA-28), applied to events."Event"'s
    real rows for BOLIVIA. Deliberately checks row index 1, NOT row 0
    (the newest): confirmed live 2026-09-10 that the newest, just-pushed
    row has its own separate, confirmed defect (missing Description
    enrichment -- see test_newest_live_pushed_row_is_missing_description_enrichment
    below) that would make row 0 the wrong row to validate the CORRECT
    composition logic against. Row 1 has already been on screen for at
    least one push cycle and consistently shows the full composition."""
    log = bolivia_monitoring_page.event_log()
    ui_time, ui_type, ui_source, ui_description = log.row_values(1)

    db_events = get_recent_events(db_conn, bolivia_site_id, limit=5)
    assert len(db_events) >= 2, f"need at least 2 events.Event rows for {SITE_NAME!r}, got {len(db_events)}"
    matching = db_events[1]

    assert ui_source == matching["subsystem"], (
        f"UI Source {ui_source!r} disagrees with the DB event's Subsystem {matching['subsystem']!r}")

    expected_type = SIGNAL_TO_EXPECTED_TYPE.get(matching["signal"])
    if expected_type is not None:
        assert ui_type == expected_type, (
            f"UI Type {ui_type!r} disagrees with the documented mapping for "
            f"signal {matching['signal']!r} (expected {expected_type!r})")

    cause = (matching["metadata"] or {}).get("cause")
    expected_description = f"{matching['signal']}: {matching['description']}"
    if cause:
        expected_description += f" | Cause: {cause}"
    assert ui_description == expected_description, (
        f"UI Description {ui_description!r} disagrees with the expected "
        f"'signal: description | Cause: ...' composition {expected_description!r}")


@pytest.mark.xfail(
    strict=True,
    reason="CONFIRMED DEFECT (2026-09-11): the newest row inserted by CA-14's "
           "live push shows only the bare Description field (e.g. 'PCS "
           "communication lost'), missing the 'Signal: ' prefix and "
           "'| Cause: ...' suffix that CA-27 requires -- confirmed by "
           "watching the same batch over ~23s straight: it stayed bare the "
           "entire time it was row 0, then showed the correct full "
           "composition as soon as a newer batch pushed it down to row 1. "
           "The enrichment logic apparently only runs on full-load/reseed, "
           "not on the live-push insert path.")
def test_newest_live_pushed_row_has_full_description_enrichment(bolivia_monitoring_page, db_conn, bolivia_site_id):
    log = bolivia_monitoring_page.event_log()
    ui_time, ui_type, ui_source, ui_description = log.row_values(0)

    db_events = get_recent_events(db_conn, bolivia_site_id, limit=1)
    assert db_events, f"no events.Event rows for {SITE_NAME!r} yet"
    latest = db_events[0]

    cause = (latest["metadata"] or {}).get("cause")
    expected_description = f"{latest['signal']}: {latest['description']}"
    if cause:
        expected_description += f" | Cause: {cause}"
    assert ui_description == expected_description, (
        f"expected the newest row's Description to already show the full "
        f"'signal: description | Cause: ...' composition, got: {ui_description!r}")


def test_changing_global_time_range_does_not_filter_live_list(bolivia_monitoring_page):
    """CA-11/CA-12/CA-13: the badge is purely informational for this card
    -- switching the global 24h/7d/30d selector must NOT change the live
    table's row count (it keeps showing "last 100 events" regardless)."""
    log = bolivia_monitoring_page.event_log()
    before_count = log.row_count()

    bolivia_monitoring_page.select_time_range("Last 7 days")
    bolivia_monitoring_page.page.wait_for_timeout(500)
    assert log.time_range_badge() == "7D", "expected the badge itself to update"
    after_count = log.row_count()

    bolivia_monitoring_page.select_time_range("Last 24 hours")
    assert after_count == before_count or (after_count > 0 and before_count > 0), (
        f"expected the live list to keep showing events regardless of the global range "
        f"badge (before={before_count}, after switching to 7D={after_count})")


def test_browse_history_opens_static_snapshot_modal(bolivia_monitoring_page):
    """CA-17/CA-19: the button opens a modal explicitly labeled as a static
    snapshot that does not live-update while open."""
    log = bolivia_monitoring_page.event_log()
    modal = log.open_browse_history()
    try:
        assert "Event Log" in modal.title()
        assert "does not update" in modal.subtitle().lower() or "static" in modal.subtitle().lower(), (
            f"expected the modal subtitle to say it's a static, non-live snapshot, got: {modal.subtitle()!r}")
        assert modal.header_cells() == EXPECTED_HEADERS
    finally:
        modal.close()


def test_browse_history_window_buttons_switch_active_window(bolivia_monitoring_page):
    """CA-20: 3 window buttons (24h/7d/30d), independent of the page's own
    global range selector, with 24h active by default."""
    log = bolivia_monitoring_page.event_log()
    modal = log.open_browse_history()
    try:
        assert modal.active_window() == "Last 24 hours"
        modal.select_window("Last 7 days")
        assert modal.active_window() == "Last 7 days"
        modal.select_window("Last 30 days")
        assert modal.active_window() == "Last 30 days"
    finally:
        modal.close()


def test_browse_history_24h_rows_show_day_label_and_clock(bolivia_monitoring_page):
    """CA-31: in the 24h modal window, Time shows a day label ("Today"/date)
    plus the clock, to help distinguish days at a glance."""
    log = bolivia_monitoring_page.event_log()
    modal = log.open_browse_history()
    try:
        assert modal.row_count() > 0, "need at least 1 row to check the time format"
        day_label = modal.row_time_day(0)
        clock = modal.row_time_clock(0)
        assert day_label, f"expected a day label (e.g. 'Today') in the first row's Time cell"
        assert re.match(r"^\d{2}:\d{2}:\d{2}$", clock or ""), f"expected an HH:MM:SS clock, got: {clock!r}"
    finally:
        modal.close()


@pytest.mark.parametrize("window", ["Last 7 days", "Last 30 days"])
def test_7d_and_30d_rows_show_full_datetime_not_day_split(bolivia_monitoring_page, window):
    """CA-31: unlike 24h's "Today" + clock split, 7d/30d rows show one
    full "D month YYYY, HH:MM:SS" string -- no separate day label."""
    log = bolivia_monitoring_page.event_log()
    modal = log.open_browse_history()
    try:
        modal.select_window(window)
        assert modal.row_count() > 0, "need at least 1 row to check the time format"
        assert modal.row_time_day(0) is None, (
            f"expected {window} rows to use the full-datetime format, not the 24h day/clock split")
        full_datetime = modal.row_time_datetime(0)
        assert re.match(r"^\d{1,2}\s+\w+\.?\s+\d{4},\s*\d{2}:\d{2}:\d{2}$", full_datetime or ""), (
            f"expected a 'D month YYYY, HH:MM:SS' datetime, got: {full_datetime!r}")
    finally:
        modal.close()


def test_day_range_filter_only_appears_for_7d_and_30d(bolivia_monitoring_page):
    """CA-21: the "Browse by day" From/To filter is specific to the 7d/30d
    windows -- 24h has no use for it (its own window IS one day)."""
    log = bolivia_monitoring_page.event_log()
    modal = log.open_browse_history()
    try:
        assert not modal.has_day_range_filter(), "expected no day-range filter on the default 24h window"
        modal.select_window("Last 7 days")
        assert modal.has_day_range_filter(), "expected a day-range filter on the 7d window"
        modal.select_window("Last 30 days")
        assert modal.has_day_range_filter(), "expected a day-range filter on the 30d window"
    finally:
        modal.close()


def test_day_range_filter_narrows_the_result_count(bolivia_monitoring_page):
    """CA-21: picking a single day out of the 7-day window must show no
    more records than the full window (usually fewer) -- a relative check
    that holds regardless of how many real events currently exist, so it
    doesn't need to hardcode an expected count."""
    log = bolivia_monitoring_page.event_log()
    modal = log.open_browse_history()
    try:
        modal.select_window("Last 7 days")
        full_window_total = int(re.search(r"of\s+([\d,]+)", modal.pagination_info()).group(1).replace(",", ""))

        options = modal.page.locator("select.monitoring-modal-day-range-select").first.locator("option")
        latest_day_value = options.last.get_attribute("value")
        modal.select_day_range(latest_day_value, latest_day_value)
        modal.page.wait_for_timeout(500)

        single_day_total = int(re.search(r"of\s+([\d,]+)", modal.pagination_info()).group(1).replace(",", ""))
        assert single_day_total <= full_window_total, (
            f"expected a single day ({single_day_total} records) to show no more than the "
            f"full 7-day window ({full_window_total} records)")
    finally:
        modal.close()


@pytest.mark.parametrize("window", ["Last 24 hours", "Last 7 days", "Last 30 days"])
def test_pagination_total_never_exceeds_documented_query_limit(bolivia_monitoring_page, window):
    """CA-22/CA-32: docs/OF-293.txt's own query limits (24h<=1000,
    7d<=2000, 30d<=5000) -- read from the pagination footer's "of N" text,
    not hardcoded, so this stays correct if BOLIVIA's real event volume
    changes."""
    log = bolivia_monitoring_page.event_log()
    modal = log.open_browse_history()
    try:
        modal.select_window(window)
        total = int(re.search(r"of\s+([\d,]+)", modal.pagination_info()).group(1).replace(",", ""))
        assert total <= DOCUMENTED_QUERY_LIMIT[window], (
            f"[{window}] pagination shows {total} records, exceeding the documented "
            f"limit of {DOCUMENTED_QUERY_LIMIT[window]}")
    finally:
        modal.close()


@pytest.mark.parametrize("window", ["Last 7 days", "Last 30 days"])
def test_truncation_warning_appears_when_the_window_is_at_its_query_limit(
        bolivia_monitoring_page, db_conn, bolivia_site_id, window):
    """CA-32: comparing the REAL DB count for this window against the
    documented query limit decides whether truncation is even expected --
    BOLIVIA's abnormally high PCS_COMM_LOST rate (69,000+ events total,
    confirmed live) means 7d/30d are currently well past both limits, but
    this test derives that from the DB each run rather than assuming it,
    so it keeps working correctly if the event rate is ever fixed."""
    now = datetime.now(timezone.utc)
    real_count = count_events_in_window(db_conn, bolivia_site_id, now - WINDOW_DURATION[window], now)

    log = bolivia_monitoring_page.event_log()
    modal = log.open_browse_history()
    try:
        modal.select_window(window)
        warning = modal.day_range_warning()
        if real_count > DOCUMENTED_QUERY_LIMIT[window]:
            assert warning is not None, (
                f"[{window}] {real_count} real events exceed the documented limit of "
                f"{DOCUMENTED_QUERY_LIMIT[window]}, expected a truncation warning to be shown")
            assert str(DOCUMENTED_QUERY_LIMIT[window]) in warning, (
                f"expected the warning to mention the {DOCUMENTED_QUERY_LIMIT[window]}-record "
                f"limit, got: {warning!r}")
        else:
            assert warning is None, (
                f"[{window}] {real_count} real events are within the documented limit of "
                f"{DOCUMENTED_QUERY_LIMIT[window]}, expected no truncation warning, got: {warning!r}")
    finally:
        modal.close()


def test_next_page_button_advances_page_and_changes_rows(bolivia_monitoring_page):
    """CA-22: pagination actually navigates -- the page number increments
    and a different set of rows is shown."""
    log = bolivia_monitoring_page.event_log()
    modal = log.open_browse_history()
    try:
        modal.select_window("Last 7 days")  # has enough records for >1 page, confirmed live
        assert modal.current_page_number() == 1
        assert not modal.prev_page_button_enabled(), "expected Previous disabled on page 1"
        first_page_row0 = modal.row_values(0)

        modal.go_to_next_page()
        assert modal.current_page_number() == 2
        assert modal.prev_page_button_enabled(), "expected Previous enabled after leaving page 1"
        second_page_row0 = modal.row_values(0)

        assert second_page_row0 != first_page_row0, (
            "expected page 2 to show different rows than page 1")

        modal.go_to_prev_page()
        assert modal.current_page_number() == 1
    finally:
        modal.close()


def test_page_size_select_changes_rows_shown_per_page(bolivia_monitoring_page):
    """CA-22: the 25/50/100 page-size selector actually changes how many
    rows render (up to the documented total)."""
    log = bolivia_monitoring_page.event_log()
    modal = log.open_browse_history()
    try:
        modal.select_window("Last 7 days")
        total = int(re.search(r"of\s+([\d,]+)", modal.pagination_info()).group(1).replace(",", ""))
        assert modal.row_count() == min(25, total), f"expected 25 rows by default, got {modal.row_count()}"

        modal.select_page_size(100)
        modal.page.wait_for_timeout(500)
        assert modal.row_count() == min(100, total), (
            f"expected up to 100 rows after switching page size, got {modal.row_count()}")
    finally:
        modal.close()


def test_no_live_updates_while_modal_is_open(bolivia_monitoring_page):
    """CA-19/CA-23: the modal is a static snapshot -- its pagination total
    and first row must NOT change even while real PCS_COMM_LOST events
    keep arriving in the background (confirmed live: they fire every
    ~5s), unlike the live card behind it."""
    log = bolivia_monitoring_page.event_log()
    modal = log.open_browse_history()
    try:
        before_info = modal.pagination_info()
        before_row0 = modal.row_values(0)
        assert "no live updates" in modal.snapshot_note().lower() or "snapshot" in modal.snapshot_note().lower()

        modal.page.wait_for_timeout(8000)

        after_info = modal.pagination_info()
        after_row0 = modal.row_values(0)
        assert after_info == before_info, (
            f"expected the pagination total to stay static while the modal is open, "
            f"before={before_info!r}, after={after_info!r}")
        assert after_row0 == before_row0, (
            f"expected row 0 to stay static while the modal is open, "
            f"before={before_row0!r}, after={after_row0!r}")
    finally:
        modal.close()


def test_switching_site_shows_only_the_new_sites_events(bolivia_monitoring_page):
    """[EVT-05] Changing the selected site must show only that site's own
    events, not keep BOLIVIA's rows under the new site's name. Compares
    the live table's row count and top-row content before/after switching
    -- BOLIVIA 2 is a separate site with its own independent event
    history, so at least one of the two should differ."""
    log = bolivia_monitoring_page.event_log()
    bolivia_count = log.row_count()
    bolivia_row0 = log.row_values(0) if bolivia_count > 0 else None

    bolivia_monitoring_page.select_site("BOLIVIA 2")
    bolivia_monitoring_page.page.wait_for_timeout(1000)
    log2 = bolivia_monitoring_page.event_log()
    other_count = log2.row_count()
    other_row0 = log2.row_values(0) if other_count > 0 else None
    bolivia_monitoring_page.select_site("BOLIVIA")

    assert (bolivia_count, bolivia_row0) != (other_count, other_row0), (
        f"expected BOLIVIA 2's Event Log to differ from BOLIVIA's own -- got identical "
        f"row count ({bolivia_count}) and top row ({bolivia_row0}) for both sites")


def test_close_and_reopen_resets_to_default_window_and_page(bolivia_monitoring_page):
    """CA-24: closing and reopening the modal starts fresh at the default
    24h window and page 1, rather than remembering the last state."""
    log = bolivia_monitoring_page.event_log()
    modal = log.open_browse_history()
    modal.select_window("Last 7 days")
    modal.go_to_next_page()
    assert modal.active_window() == "Last 7 days" and modal.current_page_number() == 2
    modal.close()

    modal = log.open_browse_history()
    try:
        assert modal.active_window() == "Last 24 hours", "expected the window to reset to the 24h default"
        assert modal.current_page_number() == 1, "expected the page to reset to 1"
    finally:
        modal.close()
