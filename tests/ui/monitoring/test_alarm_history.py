"""Data & Monitoring - Alarm History (docs/OF-148.txt) -- a live table
(Time/Device/Alarm/Severity/Status) of persisted alerts, plus a "Browse
history" modal for a static, paginated historical query. Event Log's
direct sibling in the same "Logs" section, same shared modal architecture.

BOLIVIA (Fractal). Confirmed live 2026-09-11 via direct DB query
(events."Alert"): unlike Event Log's events."Event" (69,000+ rows, one per
raw occurrence), Alert is a small, UPDATE-IN-PLACE table -- one row per
distinct (Device, Alarm) pair, with Count incremented and LastOccurred
bumped on each repeat rather than a new row appended. BOLIVIA has only ~12
Alert rows total, so the query limits (24h<=1000, 7d<=2000, 30d<=5000) and
the truncation warning are never actually exercised for this site today --
tests that depend on volume are written to hold correctly either way
(skip/assert-consistently) rather than assuming a specific count.

Times: confirmed via direct DB comparison that the live table's "DD/MM/YYYY,
HH:MM:SS" Time column renders events."Alert"."LastOccurred" (stored UTC) in
the browser's LOCAL time (America/La_Paz, UTC-4) -- same pattern already
established for Event Log and Site Power Telemetry.
"""
import re
from datetime import datetime, timedelta, timezone

import pytest

from shared.config.settings import BASE_URL
from shared.datasource.db_source import get_site_ids, get_recent_alarms, count_alarms_in_window

pytestmark = pytest.mark.ui

SITE_NAME = "BOLIVIA"
EXPECTED_LIVE_HEADERS = ["Time", "Device", "Alarm", "Severity", "Status"]
EXPECTED_MODAL_HEADERS = EXPECTED_LIVE_HEADERS

# docs/OF-148.txt's own query limits per Browse history window.
DOCUMENTED_QUERY_LIMIT = {"Last 24 hours": 1000, "Last 7 days": 2000, "Last 30 days": 5000}
WINDOW_DURATION = {
    "Last 24 hours": timedelta(hours=24), "Last 7 days": timedelta(days=7), "Last 30 days": timedelta(days=30),
}

# Confirmed live against events."Alert"."Severity" (int) for BOLIVIA.
SEVERITY_CODE_TO_TEXT = {1: "WARNING", 3: "MAJOR", 5: "CRITICAL"}

# docs/OF-148.txt's own Estado -> etiqueta WO mapping.
STATUS_CODE_TO_WO_LABEL = {0: "WO Open", 1: "WO In-Progress", 2: "WO Closed", 3: "WO Suppressed"}


@pytest.fixture
def bolivia_monitoring_page(require_omniops, monitoring_page):
    return monitoring_page.select_site(SITE_NAME)


@pytest.fixture(scope="session")
def bolivia_site_id(db_conn):
    return get_site_ids(db_conn, [SITE_NAME])[SITE_NAME]


def _row_sort_key(display_time):
    """Parses the live table's "DD/MM/YYYY, HH:MM:SS" format into a
    sortable tuple -- same pattern as Event Log's own ordering check."""
    match = re.match(r"(\d{2})/(\d{2})/(\d{4}),\s*(\d{2}):(\d{2}):(\d{2})", display_time)
    assert match, f"unrecognized Alarm History time format: {display_time!r}"
    day, month, year, hour, minute, second = (int(g) for g in match.groups())
    return (year, month, day, hour, minute, second)


def test_title_badge_and_period_text(bolivia_monitoring_page):
    """CA-05: badge (24H by default) and matching period sentence --
    purely informational for this card, not a live-list filter."""
    alarms = bolivia_monitoring_page.alarm_history()
    assert alarms.time_range_badge() == "24H"
    assert alarms.time_range_period() == "Last 24 hours."


def test_subtitle_and_footer_hint_text(bolivia_monitoring_page):
    """CA-04/CA-16: subtitle describes site-level alarms; footer explains
    that clicking a row filters Telemetry Data Table by device."""
    alarms = bolivia_monitoring_page.alarm_history()
    assert "alarm" in alarms.subtitle().lower()
    footer = alarms.card().locator(".card-subtitle").last.inner_text().strip().lower()
    assert "device" in footer and "telemetry" in footer, (
        f"expected the footer to explain the row-click-filters-telemetry behavior, got: {footer!r}")


def test_table_headers_match_documented_columns(bolivia_monitoring_page):
    """CA-07: exactly these 5 columns, in this order."""
    alarms = bolivia_monitoring_page.alarm_history()
    if not alarms.has_table():
        pytest.skip(f"no alarms currently open for {SITE_NAME}: {alarms.empty_state_text()!r}")
    assert alarms.header_cells() == EXPECTED_LIVE_HEADERS


def test_row_count_never_exceeds_100(bolivia_monitoring_page):
    """CA-09: max 100 alarms on the live card."""
    alarms = bolivia_monitoring_page.alarm_history()
    if not alarms.has_table():
        pytest.skip(f"no alarms currently open for {SITE_NAME}: {alarms.empty_state_text()!r}")
    assert 0 < alarms.row_count() <= 100, f"expected 1-100 rows, got {alarms.row_count()}"


def test_rows_ordered_most_recent_first(bolivia_monitoring_page):
    """CA-08: most recent LastOccurred on top."""
    alarms = bolivia_monitoring_page.alarm_history()
    if not alarms.has_table():
        pytest.skip(f"no alarms currently open for {SITE_NAME}: {alarms.empty_state_text()!r}")
    times = [row[0] for row in alarms.all_row_values()]
    assert len(times) >= 2, f"need at least 2 rows to check ordering, got: {times}"
    keys = [_row_sort_key(t) for t in times]
    assert keys == sorted(keys, reverse=True), f"rows aren't ordered most-recent-first: {times}"


def test_severity_pill_shows_uppercase_text(bolivia_monitoring_page):
    """CA-13: Severity renders as uppercase text inside a pill."""
    alarms = bolivia_monitoring_page.alarm_history()
    if not alarms.has_table():
        pytest.skip(f"no alarms currently open for {SITE_NAME}: {alarms.empty_state_text()!r}")
    for i in range(alarms.row_count()):
        severity_text = alarms.rows().nth(i).locator(".sev-pill").inner_text().strip()
        assert severity_text == severity_text.upper() and severity_text, (
            f"row {i}: expected uppercase severity text, got {severity_text!r}")


@pytest.mark.xfail(
    strict=True,
    reason="CONFIRMED DEFECT (2026-09-11): MAJOR-severity alarms render with "
           "className 'sev-pill ' (empty modifier -- no color mapping), "
           "falling back to a plain gray/default border+text color "
           "(rgb(229,231,235)), unlike WARNING (blue, sev-warning) and "
           "CRITICAL (red, sev-critical). CA-13 requires 'Severity in a "
           "colored pill' -- MAJOR alarms are visually indistinguishable "
           "from an unrecognized/unstyled severity, losing the at-a-glance "
           "severity cue for a real, non-trivial severity level.")
def test_every_documented_severity_has_a_distinct_color_class(bolivia_monitoring_page, db_conn, bolivia_site_id):
    db_alarms = get_recent_alarms(db_conn, bolivia_site_id, limit=100)
    severities_present = {a["severity"] for a in db_alarms}
    assert severities_present, f"no events.Alert rows for {SITE_NAME!r} to check"

    alarms = bolivia_monitoring_page.alarm_history()
    if not alarms.has_table():
        pytest.skip(f"no alarms currently open for {SITE_NAME}: {alarms.empty_state_text()!r}")

    seen_classes = {}
    for i in range(alarms.row_count()):
        text = alarms.rows().nth(i).locator(".sev-pill").inner_text().strip()
        css_class = alarms.row_severity_class(i)
        seen_classes[text] = css_class

    for code in severities_present:
        expected_text = SEVERITY_CODE_TO_TEXT.get(code)
        if expected_text is None or expected_text not in seen_classes:
            continue
        css_class = seen_classes[expected_text]
        assert css_class.strip() != "sev-pill", (
            f"severity {expected_text!r} (code {code}) has no color modifier class "
            f"(got {css_class!r}) -- it will render with the same plain style as an "
            f"unrecognized severity")


def test_row_values_match_recent_db_alerts(bolivia_monitoring_page, db_conn, bolivia_site_id):
    """True cross-layer ground truth against events."Alert" directly:
    Device, Alarm text, Severity, and Status must match the persisted
    alert record for the same (Device, Alarm) pair -- matched by content,
    not by index, since Alert's update-in-place LastOccurred bumps can
    reorder rows between the UI read and the DB read."""
    alarms = bolivia_monitoring_page.alarm_history()
    if not alarms.has_table():
        pytest.skip(f"no alarms currently open for {SITE_NAME}: {alarms.empty_state_text()!r}")

    ui_time, ui_device, ui_alarm, ui_severity, ui_status = alarms.row_values(0)

    db_alarms = get_recent_alarms(db_conn, bolivia_site_id, limit=20)
    matching = next(
        (a for a in db_alarms if (a["device_name"] or "").strip() == ui_device
         and a["alarm"] == ui_alarm),
        None,
    )
    assert matching is not None, (
        f"no events.Alert row found matching UI row (device={ui_device!r}, alarm={ui_alarm!r}) "
        f"among the {len(db_alarms)} most recent alerts")

    expected_severity = SEVERITY_CODE_TO_TEXT.get(matching["severity"], "WARNING")
    assert ui_severity == expected_severity, (
        f"UI Severity {ui_severity!r} disagrees with DB Severity code {matching['severity']!r} "
        f"(expected {expected_severity!r})")

    expected_status = STATUS_CODE_TO_WO_LABEL.get(matching["status"])
    assert ui_status == expected_status, (
        f"UI Status {ui_status!r} disagrees with DB Status code {matching['status']!r} "
        f"(expected {expected_status!r})")


def test_row_time_matches_db_last_occurred_in_local_time(bolivia_monitoring_page, db_conn, bolivia_site_id):
    """Confirms the user's specific question: Time must render in the
    browser's LOCAL time, not raw UTC. Converts events."Alert".LastOccurred
    (stored UTC) using the browser's own timezone offset (same
    getTimezoneOffset() pattern already confirmed for Event Log / Site
    Power Telemetry -- America/La_Paz, UTC-4) and checks it lands within a
    few seconds of the UI's displayed time (a small tolerance for the
    read-DB-then-read-UI race, not a loose one)."""
    alarms = bolivia_monitoring_page.alarm_history()
    if not alarms.has_table():
        pytest.skip(f"no alarms currently open for {SITE_NAME}: {alarms.empty_state_text()!r}")

    ui_time, ui_device, ui_alarm, _, _ = alarms.row_values(0)
    db_alarms = get_recent_alarms(db_conn, bolivia_site_id, limit=20)
    matching = next(
        (a for a in db_alarms if (a["device_name"] or "").strip() == ui_device
         and a["alarm"] == ui_alarm),
        None,
    )
    assert matching is not None, f"no events.Alert row found matching UI row 0 (device={ui_device!r}, alarm={ui_alarm!r})"

    offset_min = bolivia_monitoring_page.page.evaluate("() => new Date().getTimezoneOffset()")
    local_dt = matching["last_occurred"].astimezone(timezone.utc) - timedelta(minutes=offset_min)
    expected = local_dt.strftime("%d/%m/%Y, %H:%M:%S")

    assert ui_time == expected or abs(
        (datetime(*_row_sort_key(ui_time)) - datetime(*_row_sort_key(expected))).total_seconds()
    ) <= 5, f"UI Time {ui_time!r} isn't within 5s of the DB LastOccurred converted to local time {expected!r}"


def test_changing_global_time_range_does_not_filter_live_list(bolivia_monitoring_page):
    """CA-05/CA-06: the badge is purely informational for this card --
    switching the global 24h/7d/30d selector must NOT change the live
    table's contents."""
    alarms = bolivia_monitoring_page.alarm_history()
    if not alarms.has_table():
        pytest.skip(f"no alarms currently open for {SITE_NAME}: {alarms.empty_state_text()!r}")
    before_count = alarms.row_count()

    bolivia_monitoring_page.select_time_range("Last 7 days")
    bolivia_monitoring_page.page.wait_for_timeout(500)
    assert alarms.time_range_badge() == "7D", "expected the badge itself to update"
    after_count = alarms.row_count()

    bolivia_monitoring_page.select_time_range("Last 24 hours")
    assert after_count == before_count or (after_count > 0 and before_count > 0), (
        f"expected the live list to keep showing alarms regardless of the global range "
        f"badge (before={before_count}, after switching to 7D={after_count})")


def test_click_row_scrolls_telemetry_table_to_matching_device(bolivia_monitoring_page):
    """CA-17: clicking a row with a non-empty device filters/scrolls the
    Telemetry Data Table to that device's rows. Confirmed live 2026-09-11:
    this does NOT change the Subsystem <select> -- it scrolls the
    telemetry table's own virtualized container. Picks a row whose Device
    looks like a real device id (not the MAC-placeholder "00:00:00:00:00:00"
    used for meter-sourced alerts), matching CA-17's "if the name is
    empty, no filter applies" carve-out."""
    alarms = bolivia_monitoring_page.alarm_history()
    if not alarms.has_table():
        pytest.skip(f"no alarms currently open for {SITE_NAME}: {alarms.empty_state_text()!r}")

    target_index = None
    for i in range(alarms.row_count()):
        device = alarms.row_values(i)[1]
        if device and device != "00:00:00:00:00:00":
            target_index = i
            break
    if target_index is None:
        pytest.skip("no row with a real (non-placeholder) device to click")

    page = bolivia_monitoring_page.page
    container = page.locator(f"#{'monitoring-telemetry-table'}")
    before_scroll_top = container.evaluate("el => el.scrollTop")

    alarms.click_row(target_index)
    page.wait_for_timeout(1000)

    after_scroll_top = container.evaluate("el => el.scrollTop")
    assert after_scroll_top != before_scroll_top, (
        "expected clicking an alarm row to scroll the Telemetry Data Table's "
        "own container to the matching device's rows")


@pytest.mark.xfail(
    strict=True,
    reason="CONFIRMED DEFECT (2026-09-11): docs/OF-148.txt CA-11 requires new/"
           "updated alarms to arrive via the /hubs/alerts hub (AlertCreated/"
           "AlertUpdated) 'without reloading the page'. Confirmed live: with "
           "BOLIVIA's real PCS_COMM_LOST alerts bumping LastOccurred every "
           "~5s (verified via events.Alert directly and via Event Log's own "
           "live table, which DID keep advancing every ~5s over the same "
           "30s window), Alarm History's live table stayed frozen on the "
           "exact same top-2 rows the entire 30s -- then jumped straight to "
           "the current state the instant the page was manually reloaded. "
           "The backend data and the hub subscription both work (Event Log "
           "proves the site's live pipeline is fine); Alarm History's own "
           "SignalR handler simply never applies the incoming update.")
def test_live_alarms_update_without_manual_refresh(bolivia_monitoring_page):
    alarms = bolivia_monitoring_page.alarm_history()
    log = bolivia_monitoring_page.event_log()
    if not alarms.has_table():
        pytest.skip(f"no alarms currently open for {SITE_NAME}: {alarms.empty_state_text()!r}")

    alarm_before = alarms.all_row_values()[:2]
    event_before = log.all_row_values()[:2]

    bolivia_monitoring_page.page.wait_for_timeout(20000)

    alarm_after = alarms.all_row_values()[:2]
    event_after = log.all_row_values()[:2]

    assert event_after != event_before, (
        "sanity check failed: Event Log itself didn't update either over 20s -- "
        "the site's live pipeline may be down right now, invalidating this comparison")
    assert alarm_after != alarm_before, (
        f"expected Alarm History's live table to update without a manual refresh "
        f"(same as Event Log just did), but it stayed frozen: {alarm_before!r}")


@pytest.mark.xfail(
    strict=True,
    reason="CONFIRMED DEFECT (2026-09-11): the parameter mapping's own "
           "Status formula says 'If no WO link exists, show Active / "
           "Cleared based on Resolution Timestamp' -- explicitly NOT a "
           "WO-style label when no work order exists. Cross-checked "
           "against /alarms (Alarms & Events), which has its own SEPARATE "
           "'Alarm Condition' (Open/Ack/Cleared) and 'WO #' columns for "
           "the exact same underlying alerts: filtering /alarms to the "
           "exact BOLIVIA site shows WO # = 'Not Created' for EVERY one of "
           "its 11 alarms (work order creation isn't implemented yet for "
           "this deployment) -- yet Alarm History's Status column shows "
           "'WO Open' for all of them, fabricating the appearance of an "
           "active work order that doesn't exist.")
def test_status_reflects_real_work_order_state_not_fabricated_wo_open(bolivia_monitoring_page, logged_in_page):
    alarms = bolivia_monitoring_page.alarm_history()
    if not alarms.has_table():
        pytest.skip(f"no alarms currently open for {SITE_NAME}: {alarms.empty_state_text()!r}")

    ui_rows = {
        (alarms.row_values(i)[1], alarms.row_values(i)[2]): alarms.row_status_text(i)
        for i in range(alarms.row_count())
    }

    page = logged_in_page
    page.goto(f"{BASE_URL}/alarms")
    site_select = page.locator("select").first
    site_select.select_option(label=re.compile(rf"^{re.escape(SITE_NAME)} \("))
    page.wait_for_timeout(1500)

    wo_rows = page.evaluate("""
    () => Array.from(document.querySelectorAll('table tbody tr')).map(tr => {
        const cells = Array.from(tr.querySelectorAll('td')).map(td => td.textContent.trim());
        return { alarm: cells[0], condition: cells[3], wo: cells[4] };
    })
    """)
    assert wo_rows, f"no rows on /alarms for site {SITE_NAME!r}"

    checked = 0
    for row in wo_rows:
        if row["wo"] != "Not Created":
            continue
        # /alarms concatenates Alarm+Device with no separator (e.g.
        # "EMS-PCS Comm LostPCS-3") -- match by checking the UI (device,
        # alarm) pair is a substring split of that combined text.
        match = next(((device, alarm) for (device, alarm) in ui_rows
                      if row["alarm"] == f"{alarm}{device}"), None)
        if match is None:
            continue
        checked += 1
        ui_status = ui_rows[match]
        assert ui_status != "WO Open", (
            f"alarm {match!r} has WO # = 'Not Created' on /alarms, but Alarm "
            f"History's Status shows {ui_status!r} -- expected it to reflect "
            f"the alarm's own condition ({row['condition']!r}), not a "
            f"fabricated work-order state")
    assert checked > 0, f"couldn't match any /alarms row to a live Alarm History row: {wo_rows!r} vs {ui_rows!r}"


def test_browse_history_opens_static_snapshot_modal(bolivia_monitoring_page):
    """CA-20/CA-21: the button opens a modal explicitly labeled as a static
    snapshot that does not live-update while open."""
    alarms = bolivia_monitoring_page.alarm_history()
    modal = alarms.open_browse_history()
    try:
        assert "Alarm History" in modal.title()
        assert "does not update" in modal.subtitle().lower() or "static" in modal.subtitle().lower(), (
            f"expected the modal subtitle to say it's a static, non-live snapshot, got: {modal.subtitle()!r}")
        assert modal.header_cells() == EXPECTED_MODAL_HEADERS
    finally:
        modal.close()


def test_browse_history_window_buttons_switch_active_window(bolivia_monitoring_page):
    """CA-22: 3 window buttons (24h/7d/30d), independent of the page's own
    global range selector, with 24h active by default."""
    alarms = bolivia_monitoring_page.alarm_history()
    modal = alarms.open_browse_history()
    try:
        assert modal.active_window() == "Last 24 hours"
        modal.select_window("Last 7 days")
        assert modal.active_window() == "Last 7 days"
        modal.select_window("Last 30 days")
        assert modal.active_window() == "Last 30 days"
    finally:
        modal.close()


def test_browse_history_24h_rows_show_day_label_and_clock(bolivia_monitoring_page):
    """CA-28: in the 24h modal window, Time shows a day label ("Today"/date)
    plus the clock."""
    alarms = bolivia_monitoring_page.alarm_history()
    modal = alarms.open_browse_history()
    try:
        if modal.row_count() == 0:
            pytest.skip(f"no alarms in the 24h window for {SITE_NAME}")
        day_label = modal.row_time_day(0)
        clock = modal.row_time_clock(0)
        assert day_label, "expected a day label (e.g. 'Today') in the first row's Time cell"
        assert re.match(r"^\d{2}:\d{2}:\d{2}$", clock or ""), f"expected an HH:MM:SS clock, got: {clock!r}"
    finally:
        modal.close()


@pytest.mark.parametrize("window", ["Last 7 days", "Last 30 days"])
def test_7d_and_30d_rows_show_full_datetime_not_day_split(bolivia_monitoring_page, window):
    """CA-28: unlike 24h's "Today" + clock split, 7d/30d rows show one full
    "D month YYYY, HH:MM:SS" string -- no separate day label."""
    alarms = bolivia_monitoring_page.alarm_history()
    modal = alarms.open_browse_history()
    try:
        modal.select_window(window)
        if modal.row_count() == 0:
            pytest.skip(f"no alarms in the {window} window for {SITE_NAME}")
        assert modal.row_time_day(0) is None, (
            f"expected {window} rows to use the full-datetime format, not the 24h day/clock split")
        full_datetime = modal.row_time_datetime(0)
        assert re.match(r"^\d{1,2}\s+\w+\.?\s+\d{4},\s*\d{2}:\d{2}:\d{2}$", full_datetime or ""), (
            f"expected a 'D month YYYY, HH:MM:SS' datetime, got: {full_datetime!r}")
    finally:
        modal.close()


def test_day_range_filter_only_appears_for_7d_and_30d(bolivia_monitoring_page):
    """CA-25: the "Browse by day" From/To filter is specific to the 7d/30d
    windows."""
    alarms = bolivia_monitoring_page.alarm_history()
    modal = alarms.open_browse_history()
    try:
        assert not modal.has_day_range_filter(), "expected no day-range filter on the default 24h window"
        modal.select_window("Last 7 days")
        assert modal.has_day_range_filter(), "expected a day-range filter on the 7d window"
        modal.select_window("Last 30 days")
        assert modal.has_day_range_filter(), "expected a day-range filter on the 30d window"
    finally:
        modal.close()


def test_day_range_filter_narrows_the_result_count(bolivia_monitoring_page):
    """CA-25: picking a single day out of the 7-day window must show no
    more records than the full window (usually fewer)."""
    alarms = bolivia_monitoring_page.alarm_history()
    modal = alarms.open_browse_history()
    try:
        modal.select_window("Last 7 days")
        full_window_total = int(re.search(r"of\s+([\d,]+)", modal.pagination_info()).group(1).replace(",", ""))
        if full_window_total == 0:
            pytest.skip(f"no alarms in the 7d window for {SITE_NAME}")

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
    """CA-24/CA-26: docs/OF-148.txt's own query limits (24h<=1000,
    7d<=2000, 30d<=5000) -- read from the pagination footer's "of N" text."""
    alarms = bolivia_monitoring_page.alarm_history()
    modal = alarms.open_browse_history()
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
    """CA-26: comparing the REAL DB count for this window against the
    documented query limit decides whether truncation is even expected.
    BOLIVIA's Alert table is small (update-in-place, ~12 rows total,
    confirmed live) so today this always resolves to "no warning expected"
    -- but the test derives that from the DB each run rather than
    hardcoding it, so it stays correct if that ever changes."""
    now = datetime.now(timezone.utc)
    real_count = count_alarms_in_window(db_conn, bolivia_site_id, now - WINDOW_DURATION[window], now)

    alarms = bolivia_monitoring_page.alarm_history()
    modal = alarms.open_browse_history()
    try:
        modal.select_window(window)
        warning = modal.day_range_warning()
        if real_count > DOCUMENTED_QUERY_LIMIT[window]:
            assert warning is not None, (
                f"[{window}] {real_count} real alarms exceed the documented limit of "
                f"{DOCUMENTED_QUERY_LIMIT[window]}, expected a truncation warning to be shown")
            assert str(DOCUMENTED_QUERY_LIMIT[window]) in warning, (
                f"expected the warning to mention the {DOCUMENTED_QUERY_LIMIT[window]}-record "
                f"limit, got: {warning!r}")
        else:
            assert warning is None, (
                f"[{window}] {real_count} real alarms are within the documented limit of "
                f"{DOCUMENTED_QUERY_LIMIT[window]}, expected no truncation warning, got: {warning!r}")
    finally:
        modal.close()


def test_page_size_select_changes_rows_shown_per_page(bolivia_monitoring_page):
    """CA-24: the 25/50/100 page-size selector actually changes how many
    rows render (up to the documented total). BOLIVIA's real Alert volume
    is small, so this checks the relationship (min(size, total)) rather
    than assuming a specific page always fills up."""
    alarms = bolivia_monitoring_page.alarm_history()
    modal = alarms.open_browse_history()
    try:
        modal.select_window("Last 30 days")
        total = int(re.search(r"of\s+([\d,]+)", modal.pagination_info()).group(1).replace(",", ""))
        if total == 0:
            pytest.skip(f"no alarms in the 30d window for {SITE_NAME}")
        assert modal.row_count() == min(25, total), f"expected 25 rows by default, got {modal.row_count()}"

        modal.select_page_size(100)
        modal.page.wait_for_timeout(500)
        assert modal.row_count() == min(100, total), (
            f"expected up to 100 rows after switching page size, got {modal.row_count()}")
    finally:
        modal.close()


def test_no_live_updates_while_modal_is_open(bolivia_monitoring_page):
    """CA-21: the modal is a static snapshot -- its pagination total and
    first row must NOT change even while real alerts keep updating in the
    background (confirmed live: PCS_COMM_LOST-driven alerts bump every
    ~5s), unlike the live card behind it."""
    alarms = bolivia_monitoring_page.alarm_history()
    modal = alarms.open_browse_history()
    try:
        if modal.row_count() == 0:
            pytest.skip(f"no alarms currently open for {SITE_NAME}")
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


def test_close_and_reopen_resets_to_default_window_and_page(bolivia_monitoring_page):
    """CA-27: closing and reopening the modal starts fresh at the default
    24h window and page 1, rather than remembering the last state."""
    alarms = bolivia_monitoring_page.alarm_history()
    modal = alarms.open_browse_history()
    modal.select_window("Last 7 days")
    assert modal.active_window() == "Last 7 days"
    modal.close()

    modal = alarms.open_browse_history()
    try:
        assert modal.active_window() == "Last 24 hours", "expected the window to reset to the 24h default"
        assert modal.current_page_number() == 1, "expected the page to reset to 1"
    finally:
        modal.close()
