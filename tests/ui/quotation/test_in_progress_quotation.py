"""Quotation module -- PERSISTENCE OF THE IN-PROGRESS QUOTATION (OP-26 / HU-20, Qase suite 41), signed in as the AM (the only role that creates quotations).

Regression 2026-11-10. How the feature works (confirmed live 2026-11-10): the quotation in progress is NOT sent to the server. The form saves itself in the browser (localStorage, key
'quotation_current:<id of the user>': one per account, defect OP-41) a moment after every change and shows 'Auto-saved at h:mm:ss'. CLOSE leaves the form without asking anything; the landing then
shows the 'Current Quote' button (it does not exist when nothing is in progress) and the quotation is NOT a row of the table. 'Create Quotation' with something in progress raises the modal
'Unsaved Quotation in Progress' with Continue Editing / Save as Draft & Start New (OP-40, fixed) / Discard & Start New / Cancel. So there is no API or database layer to test in this story.
Qase 774 (a quotation can no longer be created from an alarm) is deprecated and not tested.
The titles are 'Workflow Progress test HU20-...' so the QA cleanup finds the Drafts these tests create (only the 'Save as Draft' one makes a record)."""
import re
import time

import pytest
from playwright.sync_api import expect

import framework_ui.pages.quotation.components.fse_arrangement_locators as fse_loc
from framework_ui.pages.auth.login_page import LoginPage
from framework_ui.pages.quotation.quotation_page import QuotationPage
from shared.config.credentials import load_role_credentials
from tests.ui.quotation.am_page import quotation_page  # noqa: F401  (runs as the AM, not the admin)
from tests.ui.quotation.support import pick_first_enabled_day

pytestmark = pytest.mark.ui

STMT, LABOR = fse_loc.SECTION_HEADING_STATEMENT, fse_loc.SECTION_HEADING_LABOR
STAMP = re.compile(r"Auto-saved at (\d{1,2}:\d{2}:\d{2})")
MODAL_BODY = "You have an unsaved quotation in progress. What would you like to do?"
NOTES_PLACEHOLDER = "PPE, spare parts, access restrictions..."


def _title(tag):
    return f"Workflow Progress test HU20-{tag}-{int(time.time()) % 1000000}"


def _clear_in_progress(page):
    """Nothing in progress: removes the key of the account from the browser and reloads the module."""
    page.evaluate("() => Object.keys(localStorage).filter(k => k.startsWith('quotation_current')).forEach(k => localStorage.removeItem(k))")


@pytest.fixture
def qp(quotation_page):
    """The Quotation landing with nothing in progress (any leftover of the previous test is removed)."""
    page = quotation_page.page
    _clear_in_progress(page)
    quotation_page.open(refresh=True)
    yield quotation_page
    page.keyboard.press("Escape")
    close = page.get_by_role("button", name="CLOSE", exact=True)
    if close.count() > 0:
        close.first.click()
        page.wait_for_timeout(500)


def _stamp(page):
    m = STAMP.search(page.evaluate("() => document.body.innerText"))
    return m.group(1) if m else None


def _wait_saved(page, seconds=4):
    """The form saves a moment after a change: waits and returns the 'Auto-saved at' time."""
    page.wait_for_timeout(seconds * 1000)
    stamp = _stamp(page)
    assert stamp, "the 'Auto-saved at hh:mm:ss' indicator is not shown"
    return stamp


def _fill_title(page, text):
    box = page.get_by_placeholder("Enter work order title")
    box.fill(text)
    box.blur()


def _title_value(page):
    return page.get_by_placeholder("Enter work order title").input_value()


def _current_quote(page):
    return page.get_by_role("button", name="Current Quote")


def _row_count(page):
    return page.locator("span.truncate.text-slate-100").count()


def _modal(page):
    return page.locator("div.fixed.inset-0").last


def _leave_in_progress(qp, title, **more):
    """Creates a quotation, types the title (and more), waits for the auto-save and leaves with CLOSE."""
    qp.create_quotation()
    page = qp.page
    _fill_title(page, title)
    if "units" in more:
        qp.wo_snapshot().field("Units").fill(str(more["units"]))
    if "notes" in more:
        page.get_by_placeholder(NOTES_PLACEHOLDER).fill(more["notes"])
    _wait_saved(page)
    qp.close_form()
    page.wait_for_timeout(1500)


def _raise_modal(qp):
    qp.page.get_by_role("button", name="Create Quotation", exact=True).click()
    qp.page.get_by_role("heading", name="Unsaved Quotation in Progress").wait_for(timeout=10000)


# ---- Leaving the form and finding the work again (Qase #768 to #772) ------------------------------------------------------------------------
def test_close_keeps_the_work_without_asking_and_without_a_new_record(qp):
    """Qase #768."""
    page = qp.page
    title = _title("CLOSE")
    qp.create_quotation()
    _fill_title(page, title)
    _wait_saved(page)
    qp.close_form()
    page.wait_for_timeout(1500)
    assert page.get_by_role("heading", name="Unsaved Quotation in Progress").count() == 0, "CLOSE must not ask anything"
    expect(_current_quote(page)).to_be_enabled()
    assert title not in page.evaluate("() => document.body.innerText"), "the quotation in progress is not a row of the table"


def test_the_work_is_kept_when_going_to_another_module_and_back(qp):
    """Qase #769."""
    page = qp.page
    title = _title("NAV")
    qp.create_quotation()
    _fill_title(page, title)
    _wait_saved(page)
    page.locator("a.nav-item", has_text="Fleet Overview").click()
    page.wait_for_timeout(1500)
    qp.open()
    expect(_current_quote(page)).to_be_visible()
    qp.open_current_quote()
    assert _title_value(page) == title


def test_the_work_is_kept_when_the_tab_is_closed_without_closing_the_form(qp):
    """Qase #770: the tab is closed with the form open; a new tab of the same browser finds the quotation in 'Current Quote'."""
    page = qp.page
    context = page.context
    origin = re.match(r"https?://[^/]+", page.url).group(0)
    title = _title("TAB")
    first = context.new_page()
    first.goto(origin)
    first_qp = QuotationPage(first).open()
    first_qp.create_quotation()
    _fill_title(first, title)
    _wait_saved(first)
    first.close()                                   # no CLOSE button
    second = context.new_page()
    try:
        second.goto(origin)
        second_qp = QuotationPage(second).open()
        expect(_current_quote(second)).to_be_visible(timeout=15000)
        second_qp.open_current_quote()
        assert _title_value(second) == title
    finally:
        second.close()


def test_there_is_no_current_quote_button_when_nothing_is_in_progress(qp):
    """Qase #771."""
    assert _current_quote(qp.page).count() == 0


def test_current_quote_opens_the_form_with_the_data_the_step_and_the_last_save_time(qp):
    """Qase #772."""
    page = qp.page
    title = _title("RESUME")
    qp.create_quotation()
    _fill_title(page, title)
    qp.fse_arrangement().field(STMT, fse_loc.LABEL_SUPPORT_ENGINEERS).fill("3")
    qp.fse_arrangement().field(LABOR, fse_loc.LABEL_LABOR_COST_HOUR).fill("50")
    stamp = _wait_saved(page)
    qp.close_form()
    page.wait_for_timeout(1500)
    qp.open_current_quote()
    body = page.evaluate("() => document.body.innerText")
    assert _title_value(page) == title
    assert qp.fse_arrangement().field(STMT, fse_loc.LABEL_SUPPORT_ENGINEERS).input_value() == "3"
    assert "Current step" in body and "WO Quoting" in body
    assert _stamp(page), "the 'Auto-saved at' indicator is shown"          # its exact value is checked in the two tests of the auto-save time below


def test_each_account_has_its_own_in_progress_quotation(qp, role_page):
    """Qase #775 / defect OP-41: the key of the browser storage carries the user id; another AM (AM2) sees his own empty state."""
    page = qp.page
    qp.create_quotation()
    _fill_title(page, _title("OWN"))
    _wait_saved(page)
    keys = page.evaluate("() => Object.keys(localStorage).filter(k => k.startsWith('quotation_current'))")
    assert len(keys) == 1 and re.fullmatch(r"quotation_current:[0-9a-f-]{36}", keys[0]), keys
    other = role_page("AM2")
    QuotationPage(other).open(refresh=True)
    other_keys = other.evaluate("() => Object.keys(localStorage).filter(k => k.startsWith('quotation_current'))")
    assert keys[0] not in other_keys and _current_quote(other).count() == 0, "AM2 must not see the quotation of the AM"


# ---- The warning modal (Qase #776 to #780) ----------------------------------------------------------------------------------------------------
def test_the_warning_modal_text_buttons_and_blocked_background(qp):
    """Qase #776."""
    page = qp.page
    _leave_in_progress(qp, _title("MODAL"))
    _raise_modal(qp)
    modal = _modal(page)
    text = modal.inner_text()
    assert "Unsaved Quotation in Progress" in text and MODAL_BODY in text
    buttons = [b.inner_text().strip() for b in modal.locator("button").all()]
    assert buttons == ["Continue Editing", "Save as Draft & Start New", "Discard & Start New", "Cancel"], buttons
    with pytest.raises(Exception):
        _current_quote(page).click(timeout=1500)    # the landing is blocked behind the modal
    modal.get_by_role("button", name="Cancel", exact=True).click()


def test_continue_editing_reopens_the_same_quotation_with_all_its_values(qp):
    """Qase #777 (GSP # is generated by the system now, so the four values are title, units, notes and the cost)."""
    page = qp.page
    title = _title("CONTINUE")
    qp.create_quotation()
    _fill_title(page, title)
    qp.wo_snapshot().field("Units").fill("7")
    page.get_by_placeholder(NOTES_PLACEHOLDER).fill("PPE required")
    _wait_saved(page)
    qp.close_form()
    page.wait_for_timeout(1500)
    rows = _row_count(page)
    _raise_modal(qp)
    _modal(page).get_by_role("button", name="Continue Editing", exact=True).click()
    page.get_by_text("WO Snapshot", exact=True).wait_for(timeout=15000)
    assert (_title_value(page), qp.wo_snapshot().field("Units").input_value(), page.get_by_placeholder(NOTES_PLACEHOLDER).input_value()) == (title, "7", "PPE required")
    qp.close_form()
    page.wait_for_timeout(1500)
    assert _row_count(page) == rows, "no new quotation may be created"


def test_discard_and_start_new_gives_a_blank_form_and_loses_the_old_one(qp):
    """Qase #778."""
    page = qp.page
    old, new = _title("DISCARD"), _title("BRANDNEW")
    _leave_in_progress(qp, old)
    _raise_modal(qp)
    _modal(page).get_by_role("button", name="Discard & Start New", exact=True).click()
    page.get_by_text("WO Snapshot", exact=True).wait_for(timeout=15000)
    wo = qp.wo_snapshot()
    assert _title_value(page) == "" and wo.field("Units").input_value() == "0" and wo.field("OEM Name").input_value() == ""
    assert wo.field("Type of Work").input_value() == "" or "Select" in wo.field("Type of Work").evaluate("e => e.options[e.selectedIndex].text")
    expect(page.get_by_role("button", name=fse_loc.TAB_FSE_ARRANGEMENT, exact=True)).to_be_visible()
    _fill_title(page, new)
    _wait_saved(page)
    qp.close_form()
    page.wait_for_timeout(1500)
    qp.open_current_quote()
    assert _title_value(page) == new
    qp.close_form()
    page.wait_for_timeout(1500)
    search = page.get_by_placeholder("Search WO, Quote #, site...")
    search.fill(old)
    page.wait_for_timeout(1500)
    assert old not in page.evaluate("() => Array.from(document.querySelectorAll('span.truncate')).map(e => e.innerText).join('|')")


def test_cancel_closes_the_modal_and_keeps_the_work(qp):
    """Qase #779."""
    page = qp.page
    title = _title("CANCEL")
    _leave_in_progress(qp, title)
    _raise_modal(qp)
    _modal(page).get_by_role("button", name="Cancel", exact=True).click()
    page.wait_for_timeout(800)
    assert page.get_by_role("heading", name="Unsaved Quotation in Progress").count() == 0 and page.get_by_text("WO Snapshot", exact=True).count() == 0
    qp.open_current_quote()
    assert _title_value(page) == title


def test_save_as_draft_and_start_new_moves_the_work_to_the_table_as_a_draft(qp, api_roles):
    """Qase #780 (defect OP-40, fixed)."""
    page = qp.page
    title = _title("DRAFTMODAL")
    _leave_in_progress(qp, title)
    _raise_modal(qp)
    _modal(page).get_by_role("button", name="Save as Draft & Start New", exact=True).click()
    page.get_by_text("WO Snapshot", exact=True).wait_for(timeout=15000)
    assert _title_value(page) == "", "a blank new form opens"
    qp.close_form()
    page.wait_for_timeout(1500)
    page.get_by_placeholder("Search WO, Quote #, site...").fill(title)
    page.wait_for_timeout(2000)
    expect(page.get_by_text(title).first).to_be_visible(timeout=15000)
    listed = api_roles["AM"].get("/api/quotations", page=1, pageSize=50).json()["items"]
    mine = [q for q in listed if q["title"] == title]
    assert mine and mine[0]["status"] == "Draft", f"the quotation moved to the table must be a Draft: {[(q['title'], q['status']) for q in mine]}"


# ---- What is saved and what comes back (Qase #781 to #787) ------------------------------------------------------------------------------------
def test_the_last_change_is_saved_when_closing_right_away(qp):
    """Qase #781."""
    page = qp.page
    qp.create_quotation()
    _fill_title(page, _title("LAST"))
    _wait_saved(page)
    cost = qp.fse_arrangement().field(LABOR, fse_loc.LABEL_LABOR_COST_HOUR)
    cost.fill("120")
    qp.close_form()                                  # at once, without waiting for the indicator
    page.wait_for_timeout(1500)
    qp.open_current_quote()
    assert qp.fse_arrangement().field(LABOR, fse_loc.LABEL_LABOR_COST_HOUR).input_value() == "120"


def test_a_value_that_is_replaced_does_not_come_back(qp):
    """Qase #782."""
    page = qp.page
    first, second = _title("A"), _title("B")
    _leave_in_progress(qp, first)
    qp.open_current_quote()
    _fill_title(page, second)
    _wait_saved(page)
    qp.close_form()
    page.wait_for_timeout(1500)
    qp.open_current_quote()
    assert _title_value(page) == second
    page.reload()
    page.wait_for_timeout(1500)
    QuotationPage(page).open()
    qp.open_current_quote()
    assert _title_value(page) == second and first not in page.evaluate("() => document.body.innerText")


def test_the_auto_save_time_advances_with_each_saved_change(qp):
    """Qase #783."""
    page = qp.page
    qp.create_quotation()
    _fill_title(page, _title("STAMP"))
    first = _wait_saved(page)
    page.wait_for_timeout(1100)
    box = page.get_by_placeholder("Enter work order title")
    box.press_sequentially("x"); box.blur()
    second = _wait_saved(page)
    page.get_by_placeholder(NOTES_PLACEHOLDER).fill("note")
    page.get_by_placeholder(NOTES_PLACEHOLDER).blur()
    third = _wait_saved(page)
    assert first < second < third, (first, second, third)
    qp.close_form()
    page.wait_for_timeout(1500)
    qp.open_current_quote()
    assert page.get_by_placeholder(NOTES_PLACEHOLDER).input_value() == "note"


def test_every_wo_snapshot_field_is_restored(qp):
    """Qase #784 (GSP # and QUOTE # / WO NUMBER are generated by the system, they are compared as they were; the other 10 are typed or selected)."""
    page = qp.page
    qp.create_quotation()
    wo = qp.wo_snapshot()
    wo.field("OEM Name").fill("Siemens")
    wo.field("WO Title").fill(_title("SNAP"))
    wo.field("Type of Work").select_option(index=2)
    wo.field("Unit Info").fill("Unit 3B")
    wo.field("Device").fill("INV-204")
    wo.field("Customer").select_option(index=1)
    expect(wo.field("Site Name").locator("option")).not_to_have_count(1)
    wo.field("Site Name").select_option(index=1)
    wo.field("Site Location").fill("Sonora, MX")
    wo.field("Units").fill("6")
    wo.field("Severity").select_option(index=2)
    labels = ["OEM Name", "WO Title", "Type of Work", "Unit Info", "Device", "Customer", "Site Name", "Site Location", "Units", "Severity"]
    expect(wo.field("Quote # / WO Number")).not_to_have_value("", timeout=15000)      # generated by the system, may load a moment later
    quote_number = wo.field("Quote # / WO Number").input_value()

    def read():
        return {label: wo.field(label).input_value() for label in labels}
    before = read()
    _wait_saved(page)
    qp.close_form()
    page.wait_for_timeout(1500)
    qp.open_current_quote()
    wo = qp.wo_snapshot()
    assert read() == before
    assert wo.field("Quote # / WO Number").input_value() == quote_number, "the Quote # / WO Number generated before leaving is the same"
    expect(wo.field("GSP #")).not_to_have_value("", timeout=15000)                    # 'Generated on save': it has its value once the form is saved


def test_the_selected_tab_is_restored(qp):
    """Qase #785."""
    page = qp.page
    qp.create_quotation()
    wo = qp.wo_snapshot()
    wo.field("Customer").select_option(index=1)
    expect(wo.field("Site Name").locator("option")).not_to_have_count(1)
    wo.field("Site Name").select_option(index=1)
    qp.fse_arrangement().open_fse_select_tab()
    _fill_title(page, _title("TAB2"))
    _wait_saved(page)
    qp.close_form()
    page.wait_for_timeout(1500)
    qp.open_current_quote()
    page.wait_for_timeout(800)
    assert page.get_by_text("Engineer Selection", exact=False).count() > 0, "FSE Select (Variable Rate) must be the active tab"
    assert page.get_by_text("Statement of FSE Resource", exact=True).count() == 0


def test_the_statement_of_fse_resource_is_restored_with_its_dates(qp):
    """Qase #786 (the dates are picked from the calendar; the format is mm/dd/yyyy)."""
    page = qp.page
    qp.create_quotation()
    fse = qp.fse_arrangement()
    fse.field(STMT, fse_loc.LABEL_SUPPORT_ENGINEERS).fill("3")
    fse.field(STMT, fse_loc.LABEL_WORKING_HOUR_TECH_DAY).fill("8")
    fse.field(STMT, fse_loc.LABEL_ESTIMATED_WORKING_DAYS).fill("5")
    fse.field(STMT, fse_loc.LABEL_TOTAL_OVER_HOURS_TECH).fill("2")
    pick_first_enabled_day(page, fse.field(STMT, fse_loc.LABEL_EST_START_TIME))
    pick_first_enabled_day(page, fse.field(STMT, fse_loc.LABEL_EST_END_TIME))
    labels = [fse_loc.LABEL_SUPPORT_ENGINEERS, fse_loc.LABEL_WORKING_HOUR_TECH_DAY, fse_loc.LABEL_ESTIMATED_WORKING_DAYS, fse_loc.LABEL_TOTAL_OVER_HOURS_TECH,
              fse_loc.LABEL_EST_START_TIME, fse_loc.LABEL_EST_END_TIME]

    def read():
        return [qp.fse_arrangement().field(STMT, label).input_value() for label in labels]
    before = read()
    assert all(before) and re.fullmatch(r"\d{2}/\d{2}/\d{4}", before[4]) and re.fullmatch(r"\d{2}/\d{2}/\d{4}", before[5]), before
    _wait_saved(page)
    qp.close_form()
    page.wait_for_timeout(1500)
    qp.open_current_quote()
    assert read() == before


def test_the_calculated_fields_are_restored_and_not_reset(qp):
    """Qase #787."""
    page = qp.page
    qp.create_quotation()
    fse = qp.fse_arrangement()
    fse.field(STMT, fse_loc.LABEL_SUPPORT_ENGINEERS).fill("3")
    fse.field(STMT, fse_loc.LABEL_WORKING_HOUR_TECH_DAY).fill("8")
    fse.field(STMT, fse_loc.LABEL_ESTIMATED_WORKING_DAYS).fill("5")
    fse.field(STMT, fse_loc.LABEL_TOTAL_OVER_HOURS_TECH).fill("2")
    fse.field(LABOR, fse_loc.LABEL_LABOR_COST_HOUR).fill("50")
    fse.field(LABOR, fse_loc.LABEL_LABOR_OVER_COST_HOUR).fill("75")
    derived = [fse_loc.LABEL_TOTAL_WORKING_HOUR_TECH, fse_loc.LABEL_TOTAL_MAN_WORKING_HOURS, fse_loc.LABEL_TOTAL_DAYS]

    def read():
        f = qp.fse_arrangement()
        return [f.computed_value(STMT, label) for label in derived] + [f.total_text()]
    page.wait_for_timeout(800)
    before = read()
    assert all(v not in ("0 h", "0", "$0", "") for v in before), before
    _wait_saved(page)
    qp.close_form()
    page.wait_for_timeout(1500)
    qp.open_current_quote()
    page.wait_for_timeout(800)
    assert read() == before


# ---- Log out and in again (Qase #773) -----------------------------------------------------------------------------------------------------------
def test_the_work_is_kept_after_logging_out_and_in_again_with_the_same_account(qp):
    """Qase #773: Sign out (avatar menu) and log in again with the same AM in the same browser; 'Current Quote' still has the work."""
    page = qp.page
    title = _title("RELOGIN")
    _leave_in_progress(qp, title)
    page.get_by_text("JH", exact=True).first.click()
    page.get_by_text("Sign out").first.click()
    page.get_by_role("button", name=re.compile("sign in|log in|login", re.I)).first.wait_for(timeout=20000)
    creds = load_role_credentials("AM")
    LoginPage(page).login(creds["email"], creds["password"], method="native")
    page.wait_for_url(lambda url: "/login" not in url, timeout=20000)
    QuotationPage(page).open(refresh=True)
    expect(_current_quote(page)).to_be_visible(timeout=15000)
    qp.open_current_quote()
    assert _title_value(page) == title


# ---- The 'Auto-saved at' time (Qase #772, #783) ----------------------------------------------------------------------------------------------------
def test_reopening_keeps_the_data_and_the_time_is_not_earlier_than_the_last_change(qp):
    """OP-26 AC #5: the saved data reflect the last state the AM entered. The story says nothing about the time of the indicator: reopening saves the form again and the indicator shows that time
    (decision of 2026-11-10: not a defect), so the time is never earlier than the last change and it stays still afterwards."""
    page = qp.page
    title = _title("STAMPOPEN")
    qp.create_quotation()
    _fill_title(page, title)
    last = _wait_saved(page)
    qp.close_form()
    page.wait_for_timeout(2000)
    qp.open_current_quote()
    page.wait_for_timeout(1500)
    shown = _stamp(page)
    assert _title_value(page) == title and shown >= last, (last, shown)
    page.wait_for_timeout(5000)
    assert _stamp(page) == shown, "the time does not keep moving by itself"


# ---- OP-26 AC #7: corrupted auto-saved data ----------------------------------------------------------------------------------------------------------
# Qase #222 (OP-188): FIXED, verified 2026-11-19 (before, damaged saved data was thrown away silently; now the AM is notified).
@pytest.mark.parametrize("damaged", ["{this is not json", '{"formData": '], ids=["text that is not JSON", "JSON cut in the middle"])
def test_corrupted_saved_data_notifies_the_am_instead_of_a_silent_blank_form(qp, damaged):
    page = qp.page
    _leave_in_progress(qp, _title("AC7"))
    key = page.evaluate("() => Object.keys(localStorage).find(k => k.startsWith('quotation_current'))")
    page.evaluate("([k, v]) => localStorage.setItem(k, v)", [key, damaged])
    page.reload()
    QuotationPage(page).open()
    words = ("corrupt", "restor", "recover", "could not", "couldn't", "unable", "damaged", "lost", "invalid")
    seen = []
    if _current_quote(page).count() > 0:
        _current_quote(page).first.click()
    else:
        page.get_by_role("button", name="Create Quotation", exact=True).click()
    for _ in range(6):                               # a notice can be short-lived: look at the page for 3 seconds
        text = page.evaluate("() => document.body.innerText").lower()
        seen += [w for w in words if w in text]
        page.wait_for_timeout(500)
    assert seen, "no message tells the AM that the saved quotation could not be restored"
