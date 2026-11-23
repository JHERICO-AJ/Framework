"""Quotation module -- FSE Arrangement tab (OP-20 / HU-09, Qase suite 49).

Cross-checked against Jira OP-20's own Acceptance Criteria (the clearest
source for this form's formulas) AND the real deployed app (2026-09-24,
Guest/Viewer role -- write permission works fine here, same as WO
Snapshot: these tests only reach client-side calculation/validation and
never persist anything, except test_planners_can_save_partial_progress).

Several fields and formulas work differently live than OP-20 documents --
see fse_arrangement.py's module docstring for the full diff. Those are
encoded below as CONFIRMED DEFECT xfail tests, same convention as
test_wo_snapshot.py.

Every assertion on a recalculated/reactive value uses Playwright's own
expect(...).to_have_text(...)/to_have_class(...) instead of a fixed
wait_for_timeout() + immediate read -- expect() polls (default 5s) until
the real DOM value matches or the timeout is hit, so it's both faster on
the common case (doesn't block for the full guessed delay every time) and
more robust if the app is ever slower to recalculate than today.
"""
import re
import time

import pytest
from playwright.sync_api import expect

from framework_ui.pages.quotation.components import fse_arrangement_locators as loc

from tests.ui.quotation.am_page import quotation_page  # noqa: F401  (runs as the AM, not the admin)

pytestmark = pytest.mark.ui

_INACTIVE_TAB_CLASS = re.compile("bg-transparent")


@pytest.fixture
def fse(quotation_page):
    """Same lifecycle as WoSnapshot's own fixture: a fresh, blank quotation
    per test, closed afterwards so the shared browser lands back on the
    Quotation list."""
    arrangement = quotation_page.create_quotation().fse_arrangement()
    yield arrangement
    quotation_page.close_form()


def _select_a_customer_and_site(quotation_page, customer=None):
    """Shared by the 2 tests that need a real Site selected before FSE
    Select can be reached -- opens a fresh quotation, then waits for the
    Site Name dropdown to actually populate (Site Name is dependent on
    Customer) instead of guessing a fixed delay."""
    wo = quotation_page.create_quotation().wo_snapshot()
    if customer:
        wo.field("Customer").select_option(label=customer)
    else:
        wo.field("Customer").select_option(index=1)
    site_options = wo.field("Site Name").locator("option")
    expect(site_options).not_to_have_count(1)
    wo.field("Site Name").select_option(index=1)
    return wo


def _type(page, field, text):
    """Types with real keystrokes (not .fill(), which bypasses the browser's own input filtering)."""
    field.click()
    page.keyboard.press("Control+A")
    page.keyboard.press("Delete")
    page.keyboard.type(text)
    return field.input_value()


def _pick_day(page, field, day):
    """Picks a day of the month in the custom (react-datepicker) calendar; returns False if that day is disabled."""
    field.click()
    cell = page.locator(f".react-datepicker__day--0{day:02d}:not(.react-datepicker__day--outside-month)").first
    cell.wait_for(timeout=5000)
    if "disabled" in (cell.get_attribute("class") or ""):
        page.keyboard.press("Escape")
        return False
    cell.click()
    return True


def _assert_minus_is_blocked(fse, section, label):
    """FIXED 2026-10-06 (defect #91): the minus sign is filtered while typing, so a negative value cannot be entered."""
    assert _type(fse.page, fse.field(section, label), "-5") == "5"


# ---- structure / tabs (Qase #818-821) ----

def test_fse_arrangement_includes_the_4_defined_cost_blocks(fse):
    """Qase #818: OP-20 AC-1 -- Statement of FSE Resource, Labor Costs,
    Onsite Support Costs and Reimbursable Costs must all be present."""
    headings = fse.page.locator("h2").all_text_contents()
    for expected in [
        loc.SECTION_HEADING_STATEMENT, loc.SECTION_HEADING_LABOR,
        loc.SECTION_HEADING_ONSITE, loc.SECTION_HEADING_REIMBURSABLE,
    ]:
        assert expected in headings, f"missing block: {expected}"


def test_fse_arrangement_is_the_default_tab(fse):
    """Qase #819: FSE Arrangement (Flat Rate) is shown/active by default
    when the form opens, before either tab is clicked."""
    assert fse.is_fse_arrangement_tab_active()


def test_switching_to_fse_select_requires_a_site_selected_first(fse):
    """Without a Customer/Site chosen in WO Snapshot yet, clicking 'FSE
    Select (Variable Rate)' shows a 'Site Selection Required' modal instead
    of switching -- a real precondition, not a broken tab."""
    fse.open_fse_select_tab()
    expect(fse.site_required_modal().first).to_be_visible()
    assert fse.is_fse_arrangement_tab_active()
    fse.dismiss_site_required_modal()


def test_switching_to_fse_select_tab_works_once_a_site_is_selected(quotation_page):
    _select_a_customer_and_site(quotation_page)
    fse = quotation_page.fse_arrangement()
    fse.open_fse_select_tab()
    expect(fse.fse_select_tab_locator()).not_to_have_class(_INACTIVE_TAB_CLASS)
    assert fse.site_required_modal().count() == 0
    quotation_page.close_form()


def test_fse_arrangement_content_area_is_scrollable(fse):
    """Qase #821: the panel holding all 4 blocks scrolls internally
    (confirmed live -- Onsite Support Costs and Reimbursable Costs are
    below the fold and only reachable by scrolling inside the panel, not
    the outer page)."""
    panel = fse.page.locator("section").filter(
        has=fse.page.get_by_role("heading", name=loc.SECTION_HEADING_STATEMENT, exact=True)
    ).locator("xpath=ancestor::div[contains(@class,'overflow-y-auto')]").first
    scroll_height = panel.evaluate("e => e.scrollHeight")
    client_height = panel.evaluate("e => e.clientHeight")
    assert scroll_height > client_height, "panel should be internally scrollable"


# ---- Statement of FSE Resource (Qase #822-829) ----

def test_statement_of_fse_resource_displays_its_9_documented_fields(fse):
    labels = set(fse.section_field_labels(loc.SECTION_HEADING_STATEMENT))
    missing = [label for label in loc.STATEMENT_FIELDS if label not in labels]
    assert not missing, f"missing fields: {missing}"


def test_support_engineers_has_a_minimum_value_of_1(fse):
    """Qase #823 / defect #91: FIXED, re-verified 2026-10-06. AC-6.3.2 / AC-6.7.1: minimum 1. The field has min=1,
    blocks the minus sign and a typed 0 is not kept (it goes back to 1)."""
    field = fse.field(loc.SECTION_HEADING_STATEMENT, loc.LABEL_SUPPORT_ENGINEERS)
    assert field.get_attribute("min") == "1"
    assert _type(fse.page, field, "-5") == "5"
    assert _type(fse.page, field, "0") == "1"


def test_support_engineers_stays_synchronized_with_fse_select(quotation_page):
    """Qase #824 / defect #85: FIXED, re-verified 2026-10-06. Setting 5 in FSE Arrangement shows Required: 5 in
    Engineer Selection, and the value is kept when going back."""
    _select_a_customer_and_site(quotation_page)
    fse = quotation_page.fse_arrangement()
    field = fse.field(loc.SECTION_HEADING_STATEMENT, loc.LABEL_SUPPORT_ENGINEERS)
    _type(quotation_page.page, field, "5")
    fse.open_fse_select_tab()
    try:
        expect(fse.engineer_selection_required_locator(5)).to_be_visible()
        fse.open_fse_arrangement_tab()
        expect(field).to_have_value("5")
    finally:
        quotation_page.close_form()


def test_working_hour_tech_day_defaults_to_8(fse):
    """Qase #825 / defect #92: FIXED, re-verified 2026-10-06 (OP-20 AC: default value of 8 hours)."""
    field = fse.field(loc.SECTION_HEADING_STATEMENT, loc.LABEL_WORKING_HOUR_TECH_DAY)
    assert field.input_value() == "8"


def test_est_start_time_calendar_icon_has_dark_theme_contrast(fse):
    """Qase #874 / defect #86: FIXED, re-verified 2026-10-06. The native date input was replaced by a custom date picker
    (react-datepicker) whose calendar icon is light on the dark background."""
    row = fse.field_row(loc.SECTION_HEADING_STATEMENT, loc.LABEL_EST_START_TIME)
    rgb = row.locator("svg").first.evaluate(
        "e => getComputedStyle(e).color.match(/\\d+/g).slice(0, 3).map(Number)")
    luminance = (0.299 * rgb[0] + 0.587 * rgb[1] + 0.114 * rgb[2]) / 255
    assert luminance > 0.5, f"calendar icon color {rgb} is too dark for the dark theme"


def test_est_end_time_rejects_a_value_earlier_than_est_start_time(fse):
    """Qase #826 / defect #93: FIXED, re-verified 2026-10-06 (AC-6.7.3). Setting the end date first and the start
    date later shows field errors on both and keeps Submit blocked; with the start date set first, the calendar disables
    every earlier day for the end date."""
    start = fse.field(loc.SECTION_HEADING_STATEMENT, loc.LABEL_EST_START_TIME)
    end = fse.field(loc.SECTION_HEADING_STATEMENT, loc.LABEL_EST_END_TIME)
    assert _pick_day(fse.page, end, 8)
    assert _pick_day(fse.page, start, 20)
    expect(fse.error_locator(loc.SECTION_HEADING_STATEMENT, loc.LABEL_EST_END_TIME)).to_be_visible()
    expect(fse.error_locator(loc.SECTION_HEADING_STATEMENT, loc.LABEL_EST_START_TIME)).to_be_visible()
    fse.page.get_by_role("button", name="Submit Quotation", exact=True).click()
    expect(fse.page.get_by_text("WO Snapshot", exact=True)).to_be_visible()
    expect(fse.error_locator(loc.SECTION_HEADING_STATEMENT, loc.LABEL_EST_END_TIME)).to_be_visible()


def test_est_end_time_calendar_disables_days_before_the_start_date(fse):
    """Qase #826 (second half): with the start date set first, earlier days cannot be picked for the end date."""
    start = fse.field(loc.SECTION_HEADING_STATEMENT, loc.LABEL_EST_START_TIME)
    end = fse.field(loc.SECTION_HEADING_STATEMENT, loc.LABEL_EST_END_TIME)
    assert _pick_day(fse.page, start, 20)
    assert not _pick_day(fse.page, end, 10)


def test_date_fields_turn_off_the_browser_autofill(fse):
    """Qase #957 / defect #140 (OP-109): FIXED, verified 2026-11-09, also in FSE Arrangement (HU-09): Est. Start Time and Est. End Time declare autocomplete=off."""
    for label in (loc.LABEL_EST_START_TIME, loc.LABEL_EST_END_TIME):
        assert fse.field(loc.SECTION_HEADING_STATEMENT, label).get_attribute("autocomplete") == "off", f"{label} does not disable autocomplete"


def test_date_fields_use_the_apps_own_english_picker(fse):
    """Qase #875 / defect #87: FIXED, re-verified 2026-10-06. The date fields are a custom picker with a fixed
    MM/DD/YYYY format and an English calendar, not the browser's native widget. The test browser is es-ES, where a native date field would show dd/mm/yyyy, so this also proves the picker does not follow the OS/browser language."""
    start = fse.field(loc.SECTION_HEADING_STATEMENT, loc.LABEL_EST_START_TIME)
    assert start.get_attribute("placeholder") == "MM/DD/YYYY"
    start.click()
    expect(fse.page.get_by_text("Today", exact=True)).to_be_visible()
    expect(fse.page.get_by_text(re.compile(r"^(January|February|March|April|May|June|July|August|September|October|November|December) \d{4}$"))).to_be_visible()
    fse.page.keyboard.press("Escape")


def test_total_man_working_hours_includes_total_over_hours(fse):
    fse.field(loc.SECTION_HEADING_STATEMENT, loc.LABEL_SUPPORT_ENGINEERS).fill("2")
    fse.field(loc.SECTION_HEADING_STATEMENT, loc.LABEL_WORKING_HOUR_TECH_DAY).fill("4")
    fse.field(loc.SECTION_HEADING_STATEMENT, loc.LABEL_ESTIMATED_WORKING_DAYS).fill("2")
    over = fse.field(loc.SECTION_HEADING_STATEMENT, loc.LABEL_TOTAL_OVER_HOURS_TECH)
    over.fill("2")
    over.blur()
    expect(fse.computed_value_locator(
        loc.SECTION_HEADING_STATEMENT, loc.LABEL_TOTAL_MAN_WORKING_HOURS)).to_have_text("20 h", timeout=2000)


def test_total_days_equals_support_engineers_times_estimated_working_days(fse):
    fse.field(loc.SECTION_HEADING_STATEMENT, loc.LABEL_SUPPORT_ENGINEERS).fill("2")
    days = fse.field(loc.SECTION_HEADING_STATEMENT, loc.LABEL_ESTIMATED_WORKING_DAYS)
    days.fill("3")
    days.blur()
    expect(fse.computed_value_locator(loc.SECTION_HEADING_STATEMENT, loc.LABEL_TOTAL_DAYS)).to_have_text("6")


def test_calculated_fields_refresh_immediately_when_support_engineers_changes(fse):
    fse.field(loc.SECTION_HEADING_STATEMENT, loc.LABEL_ESTIMATED_WORKING_DAYS).fill("2")
    se = fse.field(loc.SECTION_HEADING_STATEMENT, loc.LABEL_SUPPORT_ENGINEERS)
    total_days = fse.computed_value_locator(loc.SECTION_HEADING_STATEMENT, loc.LABEL_TOTAL_DAYS)
    se.fill("1")
    se.blur()
    expect(total_days).to_have_text("2")
    se.fill("4")
    se.blur()
    expect(total_days).to_have_text("8")


# ---- Labor Costs (Qase #830-832) ----

def test_labor_costs_card_displays_exactly_3_fields(fse):
    labels = fse.section_field_labels(loc.SECTION_HEADING_LABOR)
    assert labels == [loc.LABEL_LABOR_COST_HOUR, loc.LABEL_LABOR_OVER_COST_HOUR]


def test_labor_cost_per_hour_rejects_a_negative_value(fse):
    """Qase #831 / defect #91: FIXED, re-verified 2026-10-06 (the minus sign is blocked while typing)."""
    _assert_minus_is_blocked(fse, loc.SECTION_HEADING_LABOR, loc.LABEL_LABOR_COST_HOUR)


def test_labor_subtotal_matches_the_documented_formula(fse):
    """OP-20 AC: Labor Subtotal = (Total Working Hour x SUPPORT ENGINEERS x
    Labor Cost/Hour) + (Total Over Hours x SUPPORT ENGINEERS x Labor Over
    Cost/Hour). Confirmed live: this specific formula IS implemented
    correctly (unlike Total Man Working Hours' formula, see the xfail
    above) -- (8*2*45)+(2*2*60) = 960."""
    fse.field(loc.SECTION_HEADING_STATEMENT, loc.LABEL_SUPPORT_ENGINEERS).fill("2")
    fse.field(loc.SECTION_HEADING_STATEMENT, loc.LABEL_WORKING_HOUR_TECH_DAY).fill("4")
    fse.field(loc.SECTION_HEADING_STATEMENT, loc.LABEL_ESTIMATED_WORKING_DAYS).fill("2")
    fse.field(loc.SECTION_HEADING_STATEMENT, loc.LABEL_TOTAL_OVER_HOURS_TECH).fill("2")
    fse.field(loc.SECTION_HEADING_LABOR, loc.LABEL_LABOR_COST_HOUR).fill("45")
    over_cost = fse.field(loc.SECTION_HEADING_LABOR, loc.LABEL_LABOR_OVER_COST_HOUR)
    over_cost.fill("60")
    over_cost.blur()
    expect(fse.subtotal_locator(loc.SECTION_HEADING_LABOR)).to_have_text("$960")


# ---- Onsite Support Costs (Qase #833-836) ----

def test_onsite_support_costs_card_displays_its_4_documented_fields(fse):
    labels = fse.section_field_labels(loc.SECTION_HEADING_ONSITE)
    assert labels == [loc.LABEL_HOTEL_COST, loc.LABEL_PER_DIEM, loc.LABEL_TRAVEL_DRIVE_TIME]


def test_hotel_cost_rejects_a_negative_value(fse):
    """Qase #834 / defect #91: FIXED, re-verified 2026-10-06 (the minus sign is blocked while typing)."""
    _assert_minus_is_blocked(fse, loc.SECTION_HEADING_ONSITE, loc.LABEL_HOTEL_COST)


def test_travel_drive_time_rejects_a_negative_value(fse):
    """Qase #835 / defect #91: FIXED, re-verified 2026-10-06 (the minus sign is blocked while typing)."""
    _assert_minus_is_blocked(fse, loc.SECTION_HEADING_ONSITE, loc.LABEL_TRAVEL_DRIVE_TIME)


def test_onsite_support_subtotal_refreshes_immediately(fse):
    """Qase #836: still true that it's read-only and auto-calculated, and
    that it refreshes without a page reload -- its EXACT formula is wrong
    (see the two dedicated defect tests below), but the field itself does
    react live to input changes."""
    hotel = fse.field(loc.SECTION_HEADING_ONSITE, loc.LABEL_HOTEL_COST)
    hotel.fill("100")
    hotel.blur()
    expect(fse.subtotal_locator(loc.SECTION_HEADING_ONSITE)).to_have_text("$100")


# ---- Reimbursable Costs (Qase #837-840) ----

def test_reimbursable_costs_card_displays_its_5_fields_and_subtotal(fse):
    labels = fse.section_field_labels(loc.SECTION_HEADING_REIMBURSABLE)
    assert labels == loc.REIMBURSABLE_FIELDS + [loc.LABEL_MISCELLANEOUS_NOTE]


def test_empty_reimbursable_field_is_treated_as_0_in_the_subtotal(fse):
    fse.field(loc.SECTION_HEADING_REIMBURSABLE, loc.LABEL_AIR_TRANSPORTATION).fill("200")
    expect(fse.subtotal_locator(loc.SECTION_HEADING_REIMBURSABLE)).to_have_text("$200")


def test_reimbursable_subtotal_equals_the_sum_of_its_5_fields(fse):
    values = {
        loc.LABEL_AIR_TRANSPORTATION: "200", loc.LABEL_CAR_EXPENSE: "100",
        loc.LABEL_MATERIAL_EXPENSE: "50", loc.LABEL_EQUIPMENT_RENTAL: "75",
        loc.LABEL_MISCELLANEOUS: "25",
    }
    for label, value in values.items():
        f = fse.field(loc.SECTION_HEADING_REIMBURSABLE, label)
        f.fill(value)
        f.blur()
    expect(fse.subtotal_locator(loc.SECTION_HEADING_REIMBURSABLE)).to_have_text("$450")


def test_miscellaneous_note_stores_a_note_alongside_the_amount(fse):
    fse.field(loc.SECTION_HEADING_REIMBURSABLE, loc.LABEL_MISCELLANEOUS).fill("25")
    note = fse.field(loc.SECTION_HEADING_REIMBURSABLE, loc.LABEL_MISCELLANEOUS_NOTE)
    note.fill("Client-provided spare parts")
    note.blur()
    assert note.input_value() == "Client-provided spare parts"


# ---- Cross-block (Qase #841-845) ----

def test_total_fse_arrangement_cost_equals_the_sum_of_the_3_block_subtotals(fse):
    fse.field(loc.SECTION_HEADING_LABOR, loc.LABEL_LABOR_COST_HOUR).fill("10")
    fse.field(loc.SECTION_HEADING_STATEMENT, loc.LABEL_WORKING_HOUR_TECH_DAY).fill("1")
    fse.field(loc.SECTION_HEADING_STATEMENT, loc.LABEL_ESTIMATED_WORKING_DAYS).fill("1")
    fse.field(loc.SECTION_HEADING_ONSITE, loc.LABEL_HOTEL_COST).fill("50")
    reimbursable_field = fse.field(loc.SECTION_HEADING_REIMBURSABLE, loc.LABEL_CAR_EXPENSE)
    reimbursable_field.fill("30")
    reimbursable_field.blur()
    expect(fse.subtotal_locator(loc.SECTION_HEADING_REIMBURSABLE)).to_have_text("$30")

    def to_number(text):
        return int(text.replace("$", "").replace(",", ""))

    labor = to_number(fse.subtotal_text(loc.SECTION_HEADING_LABOR))
    onsite = to_number(fse.subtotal_text(loc.SECTION_HEADING_ONSITE))
    reimbursable = to_number(fse.subtotal_text(loc.SECTION_HEADING_REIMBURSABLE))
    expect(fse.total_locator()).to_have_text(f"${labor + onsite + reimbursable}")


def test_planners_can_save_partial_progress(quotation_page):
    """Qase #842: Save Draft must succeed with only some FSE Arrangement
    fields filled in (unique title per run -- Save Draft creates a real row
    in the shared QA environment, same convention as WO Snapshot's own
    persistence test). Save Draft itself closes the form (HUsACC HU-20 AC),
    so there's nothing left to close afterward."""
    fse = quotation_page.create_quotation().fse_arrangement()
    fse.field(loc.SECTION_HEADING_LABOR, loc.LABEL_LABOR_COST_HOUR).fill("15")
    quotation_page.wo_snapshot().field("WO Title").fill(f"FSE partial save {time.time()}")
    quotation_page.save_draft()
    expect(quotation_page.page.get_by_text("WO Snapshot", exact=True)).to_be_hidden(timeout=8000)


def test_missing_required_field_is_flagged_on_submit(fse):
    """Qase #843: the specific missing fields are flagged (not just a generic banner) when Submit is attempted with
    the arrangement incomplete. Support Engineers (1) and Working Hour/Tech Day (8) now have defaults, so the
    fields flagged on a fresh form are Estimated Working Days and the two dates."""
    fse.page.get_by_role("button", name="Submit Quotation", exact=True).click()
    expect(fse.error_locator(loc.SECTION_HEADING_STATEMENT, loc.LABEL_ESTIMATED_WORKING_DAYS)).to_be_visible()
    expect(fse.error_locator(loc.SECTION_HEADING_STATEMENT, loc.LABEL_EST_START_TIME)).to_be_visible()
    expect(fse.error_locator(loc.SECTION_HEADING_STATEMENT, loc.LABEL_EST_END_TIME)).to_be_visible()


def test_every_statement_field_is_either_editable_or_computed(fse):
    """Qase #844: each of the 9 Statement of FSE Resource fields is
    unambiguously EITHER a plain editable input OR a read-only computed
    <div> -- never both, never neither."""
    editable = {loc.LABEL_SUPPORT_ENGINEERS, loc.LABEL_WORKING_HOUR_TECH_DAY,
                loc.LABEL_ESTIMATED_WORKING_DAYS, loc.LABEL_TOTAL_OVER_HOURS_TECH,
                loc.LABEL_EST_START_TIME, loc.LABEL_EST_END_TIME}
    computed = {loc.LABEL_TOTAL_WORKING_HOUR_TECH, loc.LABEL_TOTAL_MAN_WORKING_HOURS,
                loc.LABEL_TOTAL_DAYS}
    assert editable | computed == set(loc.STATEMENT_FIELDS)
    for label in editable:
        assert fse.field(loc.SECTION_HEADING_STATEMENT, label).count() == 1
    for label in computed:
        row = fse.field_row(loc.SECTION_HEADING_STATEMENT, label)
        assert row.locator("input, select, textarea").count() == 0
        assert row.locator("div").count() == 1


def test_est_start_time_label_has_no_typo(fse):
    """Qase #845: an earlier build reportedly showed 'Est. Start Tome' --
    confirmed corrected in the live app."""
    labels = fse.section_field_labels(loc.SECTION_HEADING_STATEMENT)
    assert loc.LABEL_EST_START_TIME in labels
    assert "Est. Start Tome" not in labels


def test_per_diem_is_charged_per_employee_per_day(fse):
    """Qase #846 / defect #83: FIXED, re-verified 2026-10-06. The field is now 'Per Diem / Person' and its
    contribution is rate x SUPPORT ENGINEERS x days worked (50 x 2 x 3 = 300)."""
    fse.field(loc.SECTION_HEADING_STATEMENT, loc.LABEL_SUPPORT_ENGINEERS).fill("2")
    fse.field(loc.SECTION_HEADING_STATEMENT, loc.LABEL_ESTIMATED_WORKING_DAYS).fill("3")
    per_diem = fse.field(loc.SECTION_HEADING_ONSITE, loc.LABEL_PER_DIEM)
    per_diem.fill("50")
    per_diem.blur()
    expect(fse.subtotal_locator(loc.SECTION_HEADING_ONSITE)).to_have_text("$300")


def test_travel_drive_time_does_not_affect_labor_subtotal(fse):
    """Qase #847: Travel & Drive Time only ever contributes to the Onsite
    Support Subtotal -- Labor Subtotal must never react to it. Support
    Engineers/Working Hour/Estimated Days must be set to something non-zero
    first -- both default to 0, and Labor Subtotal multiplies through them,
    so leaving them at 0 would make Labor Subtotal trivially $0 no
    matter what Travel & Drive Time does, and the "doesn't change" check
    would pass for the wrong reason."""
    fse.field(loc.SECTION_HEADING_STATEMENT, loc.LABEL_SUPPORT_ENGINEERS).fill("1")
    fse.field(loc.SECTION_HEADING_STATEMENT, loc.LABEL_WORKING_HOUR_TECH_DAY).fill("1")
    fse.field(loc.SECTION_HEADING_STATEMENT, loc.LABEL_ESTIMATED_WORKING_DAYS).fill("1")
    labor_cost = fse.field(loc.SECTION_HEADING_LABOR, loc.LABEL_LABOR_COST_HOUR)
    labor_cost.fill("10")
    labor_cost.blur()
    labor_subtotal = fse.subtotal_locator(loc.SECTION_HEADING_LABOR)
    onsite_subtotal = fse.subtotal_locator(loc.SECTION_HEADING_ONSITE)
    expect(labor_subtotal).to_have_text("$10")
    travel = fse.field(loc.SECTION_HEADING_ONSITE, loc.LABEL_TRAVEL_DRIVE_TIME)
    travel.fill("999")
    travel.blur()
    # Onsite Support Subtotal's own exact formula is wrong (Qase #862) --
    # not asserted here, only that it reacts at all (moves off $0),
    # which is enough to prove Travel & Drive Time was actually applied
    # before checking Labor Subtotal stayed untouched.
    expect(onsite_subtotal).not_to_have_text("$0")
    expect(labor_subtotal).to_have_text("$10")


# ---- New UI/data-quality findings (Qase #848-850) ----

def test_miscellaneous_note_rejects_emoji_characters(fse):
    """Qase #848 / defect #94: FIXED, re-verified 2026-10-06 (emojis are stripped while typing)."""
    note = fse.field(loc.SECTION_HEADING_REIMBURSABLE, loc.LABEL_MISCELLANEOUS_NOTE)
    assert _type(fse.page, note, "a\U0001F600b") == "ab"


def test_numeric_fields_reject_letters_and_special_characters(fse):
    """Qase #876: type=number filters out letters/symbols typed as real keystrokes -- only digits land (each field
    also has its own maximum number of digits)."""
    for section, label in [
        (loc.SECTION_HEADING_STATEMENT, loc.LABEL_SUPPORT_ENGINEERS),
        (loc.SECTION_HEADING_ONSITE, loc.LABEL_HOTEL_COST),
    ]:
        value = _type(fse.page, fse.field(section, label), "abc!@#$%^&*()123xyz")
        assert value == "123", f"{label}: expected only the digits 123 to land, got {value!r}"


def test_miscellaneous_note_sanitizes_html_and_script_input(fse):
    """Qase #877 / defect #88: FIXED for HTML, re-verified 2026-10-06 -- the angle brackets are stripped while typing,
    so a script tag cannot be entered."""
    note = fse.field(loc.SECTION_HEADING_REIMBURSABLE, loc.LABEL_MISCELLANEOUS_NOTE)
    value = _type(fse.page, note, "<script>alert(1)</script> & \"quotes\" 'test'")
    assert "<" not in value and ">" not in value


@pytest.mark.skip(reason="SKIPPED 2026-10-06 (Qase #881, defect #88 closed as record): no acceptance criterion covers input "
                         "sanitization; the SQL-style string is still accepted as plain text, which is harmless. Hardening "
                         "recommendation only (same as WO Snapshot, defect #89).")
def test_miscellaneous_note_rejects_sql_injection_style_input(fse):
    note = fse.field(loc.SECTION_HEADING_REIMBURSABLE, loc.LABEL_MISCELLANEOUS_NOTE)
    assert _type(fse.page, note, "' OR '1'='1' --") != "' OR '1'='1' --"


def test_numeric_fields_have_a_reasonable_maximum_length(fse):
    """Qase #849 / defect #95: FIXED, re-verified 2026-10-06. Typing a 15-digit number into Hotel Cost keeps at most
    6 digits (every numeric field has its own maximum number of digits)."""
    field = fse.field(loc.SECTION_HEADING_ONSITE, loc.LABEL_HOTEL_COST)
    assert len(_type(fse.page, field, "123456789012345")) <= 6


def test_miscellaneous_note_has_a_reasonable_maximum_length(fse):
    """Qase #849 / defect #95: FIXED, re-verified 2026-10-06. Miscellaneous Note is limited to 500 characters
    (a 600-character text keeps 500)."""
    note = fse.field(loc.SECTION_HEADING_REIMBURSABLE, loc.LABEL_MISCELLANEOUS_NOTE)
    assert len(_type(fse.page, note, "A" * 600)) == 500


def test_support_engineers_should_reject_a_decimal_value(fse):
    """Qase #850 / defect #96: FIXED, re-verified 2026-10-06. SUPPORT ENGINEERS only takes whole numbers: the decimal
    separator is dropped while typing (2.5 becomes 25)."""
    field = fse.field(loc.SECTION_HEADING_STATEMENT, loc.LABEL_SUPPORT_ENGINEERS)
    assert field.get_attribute("step") == "1"
    assert "." not in _type(fse.page, field, "2.5")


# ---- Boundary Value Analysis / Equivalence Partitioning gap-fill (Qase #851-855) ----

def test_estimated_working_days_rejects_0_or_negative(fse):
    """Qase #851 / defect #91: FIXED, re-verified 2026-10-06. A negative value cannot be typed and 0 is flagged
    with 'Must be greater than 0'."""
    section, label = loc.SECTION_HEADING_STATEMENT, loc.LABEL_ESTIMATED_WORKING_DAYS
    _assert_minus_is_blocked(fse, section, label)
    _type(fse.page, fse.field(section, label), "0")
    fse.page.get_by_role("button", name="Submit Quotation", exact=True).click()
    expect(fse.error_locator(section, label)).to_have_text("Must be greater than 0")


def test_total_over_hours_tech_rejects_negative(fse):
    """Qase #852 / defect #91: FIXED, re-verified 2026-10-06 (the minus sign is blocked while typing)."""
    _assert_minus_is_blocked(fse, loc.SECTION_HEADING_STATEMENT, loc.LABEL_TOTAL_OVER_HOURS_TECH)


def test_per_diem_rejects_negative(fse):
    """Qase #853 / defect #91: FIXED, re-verified 2026-10-06 (the minus sign is blocked while typing)."""
    _assert_minus_is_blocked(fse, loc.SECTION_HEADING_ONSITE, loc.LABEL_PER_DIEM)


def test_reimbursable_fields_reject_negative(fse):
    """Qase #854 / defect #91: FIXED, re-verified 2026-10-06 (the minus sign is blocked while typing)."""
    _assert_minus_is_blocked(fse, loc.SECTION_HEADING_REIMBURSABLE, loc.LABEL_CAR_EXPENSE)


WHOLE_NUMBER_FIELDS = [
    (loc.SECTION_HEADING_STATEMENT, loc.LABEL_SUPPORT_ENGINEERS), (loc.SECTION_HEADING_STATEMENT, loc.LABEL_WORKING_HOUR_TECH_DAY),
    (loc.SECTION_HEADING_STATEMENT, loc.LABEL_ESTIMATED_WORKING_DAYS), (loc.SECTION_HEADING_STATEMENT, loc.LABEL_TOTAL_OVER_HOURS_TECH),
    (loc.SECTION_HEADING_LABOR, loc.LABEL_LABOR_COST_HOUR), (loc.SECTION_HEADING_LABOR, loc.LABEL_LABOR_OVER_COST_HOUR),
    (loc.SECTION_HEADING_ONSITE, loc.LABEL_HOTEL_COST), (loc.SECTION_HEADING_ONSITE, loc.LABEL_PER_DIEM), (loc.SECTION_HEADING_ONSITE, loc.LABEL_TRAVEL_DRIVE_TIME),
    (loc.SECTION_HEADING_REIMBURSABLE, loc.LABEL_AIR_TRANSPORTATION), (loc.SECTION_HEADING_REIMBURSABLE, loc.LABEL_CAR_EXPENSE),
    (loc.SECTION_HEADING_REIMBURSABLE, loc.LABEL_MATERIAL_EXPENSE), (loc.SECTION_HEADING_REIMBURSABLE, loc.LABEL_EQUIPMENT_RENTAL),
    (loc.SECTION_HEADING_REIMBURSABLE, loc.LABEL_MISCELLANEOUS),
]


@pytest.mark.parametrize("section, label", WHOLE_NUMBER_FIELDS, ids=[label for _, label in WHOLE_NUMBER_FIELDS])
def test_every_numeric_field_takes_whole_numbers_only(fse, section, label):
    """Qase #855 (rewritten 2026-11-06) / defect #138 / OP-107: RULE CHANGED. The developer's comment on OP-107 (2026-10-23) and the QA decision
    of 2026-11-06 are that all 14 numeric fields take whole numbers only. Typing 2.5 with real keystrokes keeps no decimal separator (the dot
    is dropped, 2.5 becomes 25), the same in every field."""
    assert "." not in _type(fse.page, fse.field(section, label), "2.5")


# ---- New formula-coverage gap-fill (Qase #858-862, added 2026-09-24) ----

def test_total_working_hour_tech_equals_working_hour_day_times_estimated_days(fse):
    """Qase #858 (new): the intermediate Total Working Hour/Tech field
    itself, verified in isolation from Total Man Working Hours (which
    consumes it but has its own separate, confirmed-buggy formula)."""
    fse.field(loc.SECTION_HEADING_STATEMENT, loc.LABEL_WORKING_HOUR_TECH_DAY).fill("4")
    days = fse.field(loc.SECTION_HEADING_STATEMENT, loc.LABEL_ESTIMATED_WORKING_DAYS)
    days.fill("3")
    days.blur()
    expect(fse.computed_value_locator(
        loc.SECTION_HEADING_STATEMENT, loc.LABEL_TOTAL_WORKING_HOUR_TECH)).to_have_text("12 h")


def test_labor_subtotal_is_a_whole_dollar_amount(fse):
    """Qase #859 (rewritten 2026-11-06): with whole numbers only there is nothing to round to the cent. 1 engineer, 8 h, 1 day, $46/hour
    -> $368, shown as a whole amount with no cents."""
    fse.field(loc.SECTION_HEADING_STATEMENT, loc.LABEL_SUPPORT_ENGINEERS).fill("1")
    fse.field(loc.SECTION_HEADING_STATEMENT, loc.LABEL_WORKING_HOUR_TECH_DAY).fill("8")
    fse.field(loc.SECTION_HEADING_STATEMENT, loc.LABEL_ESTIMATED_WORKING_DAYS).fill("1")
    fse.field(loc.SECTION_HEADING_STATEMENT, loc.LABEL_TOTAL_OVER_HOURS_TECH).fill("0")
    fse.field(loc.SECTION_HEADING_LABOR, loc.LABEL_LABOR_OVER_COST_HOUR).fill("0")
    cost = fse.field(loc.SECTION_HEADING_LABOR, loc.LABEL_LABOR_COST_HOUR)
    cost.fill("46")
    cost.blur()
    expect(fse.subtotal_locator(loc.SECTION_HEADING_LABOR)).to_have_text("$368")


def test_calculated_fields_do_not_show_scientific_notation_with_large_inputs(fse):
    """Qase #857 / defect #97: FIXED, re-verified 2026-10-06 (the fields now limit the number of digits)."""
    _type(fse.page, fse.field(loc.SECTION_HEADING_STATEMENT, loc.LABEL_WORKING_HOUR_TECH_DAY), "999999999999")
    _type(fse.page, fse.field(loc.SECTION_HEADING_STATEMENT, loc.LABEL_ESTIMATED_WORKING_DAYS), "999999999999")
    value = fse.computed_value_locator(
        loc.SECTION_HEADING_STATEMENT, loc.LABEL_TOTAL_WORKING_HOUR_TECH).inner_text()
    assert "e+" not in value.lower(), f"expected a formatted number, got scientific notation: {value!r}"


def test_large_input_does_not_overflow_its_field_box_at_laptop_width(fse):
    """Qase #856 / defect #98: FIXED, re-verified 2026-10-06 (the fields limit the number of digits, so a calculated value
    fits its own box at a 1024px viewport)."""
    fse.page.set_viewport_size({"width": 1024, "height": 768})
    try:
        _type(fse.page, fse.field(loc.SECTION_HEADING_STATEMENT, loc.LABEL_WORKING_HOUR_TECH_DAY), "999999999999999")
        _type(fse.page, fse.field(loc.SECTION_HEADING_STATEMENT, loc.LABEL_ESTIMATED_WORKING_DAYS), "999999999999999")
        value_div = fse.computed_value_locator(loc.SECTION_HEADING_STATEMENT, loc.LABEL_TOTAL_WORKING_HOUR_TECH)
        metrics = value_div.evaluate("e => ({scrollWidth: e.scrollWidth, clientWidth: e.clientWidth})")
        assert metrics["scrollWidth"] <= metrics["clientWidth"], (
            f"field's text (scrollWidth={metrics['scrollWidth']}) overflows its own box "
            f"(clientWidth={metrics['clientWidth']})")
    finally:
        fse.page.set_viewport_size({"width": 1920, "height": 1080})


def test_reimbursable_subtotal_is_0_when_all_fields_are_at_default(fse):
    """Qase #860 (new): with every Reimbursable Costs field left untouched,
    the Subtotal must read a formatted $0 -- never blank, NaN or an
    error state."""
    expect(fse.subtotal_locator(loc.SECTION_HEADING_REIMBURSABLE)).to_have_text("$0")


def test_estimated_working_days_cascades_to_every_dependent_field(fse):
    """Qase #861 (new): changing Estimated Working Days alone must refresh
    Total Working Hour/Tech, Total Days AND Labor Subtotal together in one
    go -- not just whichever field #829 already isolates (Support
    Engineers -> Total Man Working Hours/Total Days)."""
    fse.field(loc.SECTION_HEADING_STATEMENT, loc.LABEL_SUPPORT_ENGINEERS).fill("2")
    fse.field(loc.SECTION_HEADING_STATEMENT, loc.LABEL_WORKING_HOUR_TECH_DAY).fill("4")
    fse.field(loc.SECTION_HEADING_LABOR, loc.LABEL_LABOR_COST_HOUR).fill("45")
    days = fse.field(loc.SECTION_HEADING_STATEMENT, loc.LABEL_ESTIMATED_WORKING_DAYS)
    total_working_hour = fse.computed_value_locator(loc.SECTION_HEADING_STATEMENT, loc.LABEL_TOTAL_WORKING_HOUR_TECH)
    total_days = fse.computed_value_locator(loc.SECTION_HEADING_STATEMENT, loc.LABEL_TOTAL_DAYS)
    labor_subtotal = fse.subtotal_locator(loc.SECTION_HEADING_LABOR)

    days.fill("2")
    days.blur()
    expect(total_working_hour).to_have_text("8 h")
    expect(total_days).to_have_text("4")
    expect(labor_subtotal).to_have_text("$720")

    days.fill("3")
    days.blur()
    expect(total_working_hour).to_have_text("12 h")
    expect(total_days).to_have_text("6")
    expect(labor_subtotal).to_have_text("$1080")


def test_travel_drive_time_is_valued_at_3_dollars_per_hour_and_counted_once(fse):
    """Qase #862 (rewritten 2026-11-06) / defect #84 / OP-61: CRITERION UPDATED. OP-20 AC #15 now documents it: each hour of Travel / Drive Time
    is valued at a fixed $3.00 and added once to the Onsite Support Subtotal (10 h -> $30). Before the AC existed this was filed as 'tripled'."""
    travel = fse.field(loc.SECTION_HEADING_ONSITE, loc.LABEL_TRAVEL_DRIVE_TIME)
    travel.fill("10")
    travel.blur()
    expect(fse.subtotal_locator(loc.SECTION_HEADING_ONSITE)).to_have_text("$30", timeout=2000)


def test_customer_prefilled_costs_are_labelled_customer_rate(quotation_page):
    """Qase #920 / defect #113: FIXED (suggestion adopted), re-verified 2026-10-06. After a Customer and Site are
    selected, Labor Cost/Hour, Hotel Cost, Per Diem / Person, Air Transportation and Car Expense are pre-filled with the
    customer's own amounts (intentional, per the developer) and each carries a 'Customer rate' label, so the user knows
    the value was not typed."""
    # 2026-11-06: the first customer of the list ('1SOlar') has no rates now, so a customer that has them is picked by name
    _select_a_customer_and_site(quotation_page, customer="Andes Renewables SpA")
    fse = quotation_page.fse_arrangement()
    try:
        for section, label in [
            (loc.SECTION_HEADING_LABOR, loc.LABEL_LABOR_COST_HOUR),
            (loc.SECTION_HEADING_ONSITE, loc.LABEL_HOTEL_COST), (loc.SECTION_HEADING_ONSITE, loc.LABEL_PER_DIEM),
            (loc.SECTION_HEADING_REIMBURSABLE, loc.LABEL_AIR_TRANSPORTATION), (loc.SECTION_HEADING_REIMBURSABLE, loc.LABEL_CAR_EXPENSE),
        ]:
            expect(fse.field_row(section, label).get_by_text("Customer rate")).to_be_visible()
    finally:
        quotation_page.close_form()


def test_working_hour_tech_day_no_longer_drops_a_digit_of_the_decimal(fse):
    """Qase #138 / OP-107: FIXED, verified 2026-11-06. Before, 7.75 became 7.7 and 10.5 cleared the field (a digit was lost). Now the rule is whole
    numbers only: typing 7.75 here keeps the whole part (7) and 10.5 keeps 10. NOTE (2026-11-06): the money fields behave differently, they drop only
    the dot (45.75 becomes 4575), see the suggestion filed with this regression."""
    field = fse.field(loc.SECTION_HEADING_STATEMENT, loc.LABEL_WORKING_HOUR_TECH_DAY)
    assert _type(fse.page, field, "7.75") == "7"
    assert _type(fse.page, field, "10.5") == "10"
