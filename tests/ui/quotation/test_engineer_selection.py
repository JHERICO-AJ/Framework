"""Quotation module -- Engineer Selection panel (OP-28 / HU-10, Qase suite 47).

Cross-checked against Jira OP-28's 8 Acceptance Criteria, HUsACC, and
Quotation_Spec_bilingual_V13's section 7 (FSE Select), AND the real
deployed app (re-verified 2026-10-07, Guest/Viewer role).

Scope discipline: this file only covers what belongs to HU-10 itself
(Support Engineers, Selected/Required, Field Leader, Planned Check-In/Out).
The MAP button's own sub-window (candidate list, map pins, Add FSE) is
HU-11's scope, tested separately -- here it's only ever used mechanically, as
a precondition to reach a populated state (pick a candidate and press
"Complete"), never asserted on for its own behavior. The CALCULATE button and
PWA radio group are HU-12/HU-14 scope and are not touched here at all.

UI changes found on 2026-10-07 (all handled below): Support Engineers is a
number <input> between the - and + buttons; Planned Check-in/out are custom
date-time pickers (react-datepicker, "MM/DD/YYYY h:mm AA"); the Possible
Check-in/out inputs are hidden (the developer said so on OP-74: planned for
Sprint 2); the MAP sub-window has Clear / Close / Save Draft / Complete (Close
discards the selection).
"""
import re
import time

import pytest
from playwright.sync_api import expect

from framework_ui.pages.quotation.components import engineer_selection_locators as loc

from tests.ui.quotation.am_page import quotation_page  # noqa: F401  (runs as the AM, not the admin)

pytestmark = pytest.mark.ui


@pytest.fixture
def engineer_selection(quotation_page):
    """A fresh quotation with a Customer/Site already selected (required
    before the FSE Select tab can be opened) and the Engineer Selection
    panel active."""
    wo = quotation_page.create_quotation().wo_snapshot()
    wo.field("Customer").select_option(index=1)
    site_options = wo.field("Site Name").locator("option")
    expect(site_options).not_to_have_count(1)
    wo.field("Site Name").select_option(index=1)
    quotation_page.fse_arrangement().open_fse_select_tab()
    panel = quotation_page.engineer_selection()
    yield panel
    quotation_page.close_form()


def _type(page, field, text):
    """Real keystrokes (not .fill(), which bypasses the browser's own input filtering)."""
    field.click()
    page.keyboard.press("Control+A")
    page.keyboard.press("Delete")
    page.keyboard.type(text)
    return field.input_value()


def _pick_day(page, field, day):
    """Picks a day of the month in the custom calendar; returns False if that day is disabled."""
    field.click()
    cell = page.locator(f".react-datepicker__day--0{day:02d}:not(.react-datepicker__day--outside-month)").first
    cell.wait_for(timeout=5000)
    if "disabled" in (cell.get_attribute("class") or ""):
        page.keyboard.press("Escape")
        return False
    cell.click()
    page.keyboard.press("Escape")
    return True


def _errors(page):
    return page.evaluate("() => [...document.querySelectorAll('section p.text-red-400')].map(e => e.innerText)")


# ---- Support Engineers / Selected-Required (Qase #883-886, #890) ----

def test_support_engineers_defaults_to_1(engineer_selection):
    """OP-28 AC #2 / V13 AC-7.1.1 (Qase #883): SUPPORT ENGINEERS defaults to 1 on a fresh form."""
    assert engineer_selection.support_engineers_value() == "1"


def test_support_engineers_cannot_go_below_1(engineer_selection):
    """OP-28 AC #2 / V13 AC-7.1.2 (Qase #884): the minimum is 1; the decrease button is disabled at 1 and any value
    below 1 (0, empty, negative, text) is forced back to 1 (a typed minus sign is dropped)."""
    es = engineer_selection
    page = es.page
    field = es.field(loc.LABEL_SUPPORT_ENGINEERS)
    assert field.get_attribute("min") == "1"
    assert es.is_decrease_support_engineers_disabled()
    assert _type(page, field, "0") == "1"
    assert _type(page, field, "abc") == "1"
    assert _type(page, field, "-5") == "5"
    field.fill("")
    field.blur()
    expect(field).to_have_value("1")


def test_support_engineers_increases_and_updates_required(engineer_selection):
    """OP-28 AC #3 / V13 AC-7.3.2 (Qase #885): Required always equals the current SUPPORT ENGINEERS value."""
    engineer_selection.increase_support_engineers()
    assert engineer_selection.support_engineers_value() == "2"
    expect(engineer_selection.root.get_by_text("Selected:", exact=False).first).to_have_text(
        "Selected: 0 · Required: 2")


def test_selected_required_indicator_shows_initial_state(engineer_selection):
    """OP-28 AC #3 / V13 AC-7.3.1 (Qase #886): "Selected: X · Required: Y" is displayed next to the title."""
    expect(engineer_selection.root.get_by_text("Selected:", exact=False).first).to_have_text(
        "Selected: 0 · Required: 1")


def test_selected_required_indicator_updates_after_selection(engineer_selection):
    """OP-28 AC #3 / V13 AC-7.3.3 (Qase #890): both values update immediately when an engineer is selected."""
    engineer_selection.select_one_engineer()
    expect(engineer_selection.root.get_by_text("Selected:", exact=False).first).to_have_text(
        "Selected: 1 · Required: 1")


# ---- Field Leader (Qase #888, #889) ----

def test_field_leader_is_disabled_until_an_engineer_is_selected(engineer_selection):
    """V13 AC-7.9.4 (Qase #888): with no engineer selected, Field Leader is empty and natively disabled."""
    assert engineer_selection.field(loc.LABEL_FIELD_LEADER).is_disabled()


def test_field_leader_defaults_to_the_first_selected_engineer(engineer_selection):
    """OP-28 AC #4 / V13 AC-7.9.2 (Qase #889): once engineers are selected, the first one is the Field Leader."""
    name = engineer_selection.select_one_engineer()
    field_leader = engineer_selection.field(loc.LABEL_FIELD_LEADER)
    expect(field_leader).to_be_enabled()
    assert name in field_leader.evaluate("e => e.options[e.selectedIndex]?.text ?? ''")


def test_selected_engineers_appear_in_the_field_leader_list_and_cards_show_email_and_mobile(engineer_selection):
    """Qase #891 / defect #100 (suggestion): covered by the current design, re-verified 2026-10-07 (confirmed with the
    developer: the ENGINEER dropdown of the specification is the Field Leader select). The select lists exactly the
    engineers selected in the map, the star moves with the leader, and each engineer's card shows name, email, company
    and phone. The distance is shown in the map (candidate list and pin tooltip)."""
    es = engineer_selection
    es.increase_support_engineers()
    names = es.select_first_engineers(2)
    leader = es.field(loc.LABEL_FIELD_LEADER)
    options = [o.strip() for o in leader.locator("option").all_inner_texts() if "Select via Map" not in o]
    assert options == names, f"Field Leader should list exactly the selected engineers, got {options}"
    card = es.root.get_by_role("group", name="Selected FSE")
    for n in names:
        expect(card).to_contain_text(n)
    expect(card).to_contain_text("@")
    assert re.search(r"\+\d[\d\- ]{6,}", card.inner_text()), "expected a phone number in the engineer cards"
    leader.select_option(label=names[1])
    assert names[1] in leader.evaluate("e => e.options[e.selectedIndex].text")
    for n in names:
        expect(card).to_contain_text(n)


# ---- Planned Check-in/out (Qase #887, #892, #893, #898) ----

def test_planned_check_in_out_default_to_9am_5pm_next_day(engineer_selection):
    """V13 AC-7.4.2 (Qase #887): on first opening, Planned Check-in defaults to 9:00 AM and Planned Check-out to
    5:00 PM of the next day (shown as "MM/DD/YYYY h:mm AA")."""
    page = engineer_selection.page
    tomorrow = page.evaluate(
        "() => { const d = new Date(); d.setDate(d.getDate() + 1); "
        "return String(d.getMonth() + 1).padStart(2, '0') + '/' + String(d.getDate()).padStart(2, '0') + '/' + d.getFullYear(); }")
    check_in = engineer_selection.field(loc.LABEL_PLANNED_CHECK_IN).input_value()
    check_out = engineer_selection.field(loc.LABEL_PLANNED_CHECK_OUT).input_value()
    assert check_in == f"{tomorrow} 9:00 AM", f"expected {tomorrow} 9:00 AM, got {check_in!r}"
    assert check_out == f"{tomorrow} 5:00 PM", f"expected {tomorrow} 5:00 PM, got {check_out!r}"


def test_check_out_rejects_a_value_earlier_than_check_in(engineer_selection):
    """Qase #892 / defect #101: FIXED, re-verified 2026-10-07 (Planned Check-in/out; the Possible fields are hidden). A
    check-in later than the check-out flags both fields, and the check-out calendar disables the days before the check-in."""
    page = engineer_selection.page
    check_in = engineer_selection.field(loc.LABEL_PLANNED_CHECK_IN)
    check_out = engineer_selection.field(loc.LABEL_PLANNED_CHECK_OUT)
    assert _pick_day(page, check_in, 20)
    errors = _errors(page)
    assert "Can't be later than Planned Check-out" in errors
    assert "Can't be earlier than Planned Check-in" in errors
    assert not _pick_day(page, check_out, 10), "days before the check-in should be disabled in the check-out calendar"


def test_check_in_out_use_the_apps_own_english_picker(engineer_selection):
    """Qase #893 / defect #102: FIXED, re-verified 2026-10-07. Planned Check-in/out are a custom picker with a fixed
    "MM/DD/YYYY h:mm AA" format and an English calendar. The test browser is es-ES, where a native date-time field
    would use a day/month/year format, so this proves the picker does not follow the OS/browser language."""
    page = engineer_selection.page
    for label in (loc.LABEL_PLANNED_CHECK_IN, loc.LABEL_PLANNED_CHECK_OUT):
        field = engineer_selection.field(label)
        assert field.get_attribute("placeholder") == "MM/DD/YYYY h:mm AA"
        assert re.fullmatch(r"\d{2}/\d{2}/\d{4} \d{1,2}:\d{2} (AM|PM)", field.input_value())
    engineer_selection.field(loc.LABEL_PLANNED_CHECK_IN).click()
    expect(page.get_by_text(re.compile(
        r"^(January|February|March|April|May|June|July|August|September|October|November|December) \d{4}$"))).to_be_visible()
    page.keyboard.press("Escape")


def test_check_in_out_calendar_icons_have_dark_theme_contrast(engineer_selection):
    """Qase #898 / defect #105: FIXED, re-verified 2026-10-07. The native date-time inputs were replaced by a custom
    picker whose calendar icon is light on the dark background."""
    icon = engineer_selection.root.locator("span").filter(has=engineer_selection.page.locator("svg")).first
    color = icon.evaluate("e => getComputedStyle(e).color")
    lightness = re.match(r"oklch\(([\d.]+)", color)
    if lightness:
        assert float(lightness.group(1)) > 0.5, f"calendar icon color {color} is too dark for the dark theme"
    else:
        rgb = [int(x) for x in re.findall(r"\d+", color)[:3]]
        assert (0.299 * rgb[0] + 0.587 * rgb[1] + 0.114 * rgb[2]) / 255 > 0.5, f"calendar icon color {color} is too dark"


def test_hovered_time_in_the_time_list_stays_readable(engineer_selection):
    """Qase #956 / defect #139 (OP-108): FIXED, verified 2026-11-09 (before: light gray text on a near-white background, contrast 1.3:1; now at least 4.5:1)."""
    page = engineer_selection.page
    engineer_selection.field(loc.LABEL_PLANNED_CHECK_IN).click()
    item = page.locator(".react-datepicker__time-list-item").nth(4)
    item.hover()
    page.wait_for_timeout(300)
    colors = item.evaluate("e => { const s = getComputedStyle(e); return [s.color, s.backgroundColor]; }")

    def luminance(c):
        r, g, b = [int(x) for x in re.findall(r"\d+", c)[:3]]
        f = lambda v: v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4
        return 0.2126 * f(r / 255) + 0.7152 * f(g / 255) + 0.0722 * f(b / 255)

    hi, lo = sorted([luminance(colors[0]), luminance(colors[1])], reverse=True)
    ratio = (hi + 0.05) / (lo + 0.05)
    page.keyboard.press("Escape")
    assert ratio >= 4.5, f"hovered time {colors} has a contrast of only {ratio:.1f}:1"


def test_date_time_fields_turn_off_the_browser_autofill(engineer_selection):
    """Qase #957 / defect #140 (OP-109): FIXED, verified 2026-11-09 (the fields now declare autocomplete=off). The panel itself is not shown by the automation, so this checks the setting."""
    for label in (loc.LABEL_PLANNED_CHECK_IN, loc.LABEL_PLANNED_CHECK_OUT):
        assert engineer_selection.field(label).get_attribute("autocomplete") == "off", f"{label} does not disable autocomplete"


# ---- Open items: the criterion in Jira OP-28 still requires them (developer: planned for Sprint 2) ----

@pytest.mark.skip(reason="OUT OF SCOPE OF HU-10 (decision of 2026-11-09): the developer moved this behaviour to Sprint 2 (OP-74, OP-78, OP-79), so the Qase case is deprecated and the defect closed as not applicable. Reactivate with the Sprint 2 story.")
def test_manual_override_of_an_autocompleted_field_is_indicated(engineer_selection):
    page = engineer_selection.page
    _pick_day(page, engineer_selection.field(loc.LABEL_PLANNED_CHECK_IN), 7)
    text = engineer_selection.field_row(loc.LABEL_PLANNED_CHECK_IN).inner_text().lower()
    assert any(w in text for w in ("override", "overridden", "manual", "edited", "basis", "based on")), (
        "expected a visible indicator marking this field as manually overridden or showing its calculation basis")


@pytest.mark.skip(reason="OUT OF SCOPE OF HU-10 (decision of 2026-11-09): the developer moved this behaviour to Sprint 2 (OP-74, OP-78, OP-79), so the Qase case is deprecated and the defect closed as not applicable. Reactivate with the Sprint 2 story.")
def test_planned_check_in_recalculates_when_engineers_change(engineer_selection):
    before = (engineer_selection.field(loc.LABEL_PLANNED_CHECK_IN).input_value(),
              engineer_selection.field(loc.LABEL_PLANNED_CHECK_OUT).input_value())
    engineer_selection.select_one_engineer()
    engineer_selection.increase_support_engineers()
    after = (engineer_selection.field(loc.LABEL_PLANNED_CHECK_IN).input_value(),
             engineer_selection.field(loc.LABEL_PLANNED_CHECK_OUT).input_value())
    assert after != before, "expected Planned Check-in/out to react to the engineer-selection change"


@pytest.mark.skip(reason="OUT OF SCOPE OF HU-10 (decision of 2026-11-09): the developer moved this behaviour to Sprint 2 (OP-74, OP-78, OP-79), so the Qase case is deprecated and the defect closed as not applicable. Reactivate with the Sprint 2 story.")
def test_possible_check_in_out_are_calculated_once_engineers_are_selected(engineer_selection):
    engineer_selection.select_one_engineer()
    possible_in = engineer_selection.root.get_by_label(loc.LABEL_POSSIBLE_CHECK_IN, exact=True)
    assert possible_in.count() > 0 and possible_in.input_value() != "", "expected Possible Check-In to be calculated"


@pytest.mark.skip(reason="OUT OF SCOPE OF HU-10 (decision of 2026-11-09): the developer moved this behaviour to Sprint 2 (OP-74, OP-78, OP-79), so the Qase case is deprecated and the defect closed as not applicable. Reactivate with the Sprint 2 story.")
def test_engineer_selection_feeds_fse_arrangement_est_start_end_time(engineer_selection, quotation_page):
    engineer_selection.select_one_engineer()
    fse = quotation_page.fse_arrangement()
    fse.open_fse_arrangement_tab()
    est_start = fse.field("Statement of FSE Resource", "Est. Start Time").input_value()
    est_end = fse.field("Statement of FSE Resource", "Est. End Time").input_value()
    assert est_start != "" and est_end != "", "expected Est. Start/End Time to be populated from Engineer Selection"


# ---- Persistence (Qase #896) ----

def test_engineer_selection_data_persists_across_save_draft_and_reopen(quotation_page):
    """V13 AC-7.0.2 (Qase #896): Support Engineers, the Selected/Required indicator and Field Leader must survive Save
    Draft and reopening the same draft."""
    wo = quotation_page.create_quotation().wo_snapshot()
    wo.field("Customer").select_option(index=1)
    expect(wo.field("Site Name").locator("option")).not_to_have_count(1)
    wo.field("Site Name").select_option(index=1)
    unique_title = f"HU-10 persistence test {time.time()}"
    wo.field("WO Title").fill(unique_title)

    quotation_page.fse_arrangement().open_fse_select_tab()
    es = quotation_page.engineer_selection()
    es.increase_support_engineers()
    picked = es.select_one_engineer()

    quotation_page.save_draft()
    expect(quotation_page.page.get_by_text("WO Snapshot", exact=True)).to_be_hidden(timeout=8000)
    quotation_page.page.get_by_text(unique_title, exact=True).click()
    quotation_page.page.get_by_text("WO Snapshot", exact=True).wait_for(timeout=15000)

    quotation_page.fse_arrangement().open_fse_select_tab()
    reopened = quotation_page.engineer_selection()
    assert reopened.support_engineers_value() == "2"
    assert reopened.selected_required_text() == "Selected: 1 · Required: 2"
    field_leader = reopened.field(loc.LABEL_FIELD_LEADER)
    assert not field_leader.is_disabled()
    assert picked in field_leader.evaluate("e => e.options[e.selectedIndex]?.text ?? ''")
    quotation_page.close_form()
