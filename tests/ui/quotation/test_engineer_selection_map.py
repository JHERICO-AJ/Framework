"""Quotation module -- ENGINEER SELECTION MAP sub-window (OP-29 / HU-11,
Qase suite 48).

Regression 2026-10-07 against the QA build after development's fixes. OP-29's
AC #5 was rewritten on 2026-09-30 ("search for and add any employee to the
selection (employees only)"). The sub-window now has Clear / Close / Save Draft
/ Complete (Close discards the changes; Complete applies them).

Defect status (Qase): #106 (limit), #107 (add an unlisted employee via search),
#108 (retry), #109 (search filter) and #111 (button set) are verified fixed here.
#110 (input validation) stays OPEN: the Contractor fields are sanitized and have
length limits, but the search box still accepts script/emoji text (it only has a
100 character limit). #141: long search text overflows the side panel.

Scope discipline: this file only covers what OP-29 documents as HU-11's own
scope. Support Engineers, Field Leader and Check-in/out are HU-10's scope,
tested in test_engineer_selection.py -- here they are only used mechanically.
"""
import re

import pytest
from playwright.sync_api import expect

from framework_ui.pages.quotation.components import engineer_selection_locators as loc

from tests.ui.quotation.am_page import quotation_page  # noqa: F401  (runs as the AM, not the admin)

pytestmark = pytest.mark.ui


@pytest.fixture
def engineer_selection(quotation_page):
    """A fresh quotation with a Customer/Site already selected and the
    Engineer Selection panel active (same precondition as HU-10).

    Teardown defensively closes a still-open MAP modal and removes any
    route interception a test may have installed (the retry test) -- logged_in_page is session-scoped, so leaking
    either into the next test breaks its own setup (the modal overlay
    intercepts the sidebar click; the route silently blocks every later
    test's employees-catalog request)."""
    wo = quotation_page.create_quotation().wo_snapshot()
    wo.field("Customer").select_option(index=1)
    site_options = wo.field("Site Name").locator("option")
    expect(site_options).not_to_have_count(1)
    wo.field("Site Name").select_option(index=1)
    quotation_page.fse_arrangement().open_fse_select_tab()
    panel = quotation_page.engineer_selection()
    yield panel
    page = panel.page
    try:
        page.unroute("**/api/amxcpcatalog/employees*")
    except Exception:
        pass
    overlay = page.locator("div.fixed.inset-0")
    if overlay.count() > 0 and overlay.last.is_visible():
        overlay.last.get_by_role("button", name=loc.MAP_CLOSE_BUTTON_TEXT, exact=True).click()
    quotation_page.close_form()





def _overlay(es):
    return es.page.locator("div.fixed.inset-0").last


def _suggested_names(es):
    cards = es.candidate_cards()
    return [cards.nth(i).inner_text().split("\n")[1].strip() for i in range(cards.count())]


def _search(es, text):
    box = es.page.get_by_placeholder(loc.MAP_SEARCH_PLACEHOLDER)
    box.click()
    box.press("Control+A")
    box.press("Delete")
    box.type(text, delay=20)
    return box


def _open_map_ready(es):
    es.open_map()
    es.candidate_cards().first.wait_for(timeout=15000)
    return es


def _open_contractor_form(es, no_match="Zzz Nonexistent Engineer Xyz"):
    """Types a no-match search and returns the 3 Contractor inputs (the Name input's placeholder echoes the search)."""
    _search(es, no_match)
    overlay = _overlay(es)
    name = overlay.get_by_placeholder(no_match)
    expect(name).to_be_visible()
    return (name, overlay.get_by_placeholder(loc.MAP_CONTRACTOR_PHONE_PLACEHOLDER),
            overlay.get_by_placeholder(loc.MAP_CONTRACTOR_LOCATION_PLACEHOLDER))


def test_map_subwindow_opens_with_map_and_candidate_list(engineer_selection):
    """OP-29 AC #1: opening MAP shows a subwindow with a map and a list of candidates."""
    es = _open_map_ready(engineer_selection)
    expect(es.page.get_by_text("ENGINEER SELECTION MAP")).to_be_visible()
    expect(es.page.locator(".leaflet-container")).to_be_visible()
    assert es.candidate_cards().count() >= 1


def test_candidate_cards_show_location_distance_and_availability(engineer_selection):
    """OP-29 AC #2: candidate cards show at minimum location/distance and availability status."""
    es = _open_map_ready(engineer_selection)
    card = es.candidate_cards().first
    expect(card).to_contain_text(" mi")
    expect(card).to_contain_text(re.compile("available", re.I))


def test_candidate_pool_size_follows_required_times_2(engineer_selection):
    """V13 formula cross-check for OP-29 AC #2: pool size is required*2."""
    engineer_selection.increase_support_engineers()
    es = engineer_selection.open_map()
    expect(es.page.get_by_text("suggested engineers", exact=False)).to_have_text("4 suggested engineers")


def test_selecting_more_than_required_is_blocked(engineer_selection):
    """OP-29 AC #3 (Qase #106, fixed): once Selected equals Required the remaining candidates are disabled and a
    message explains it."""
    es = _open_map_ready(engineer_selection)
    es.candidate_cards().nth(0).click()
    expect(es.map_selected_required_text()).to_have_text("Selected 1 / Required 1")
    expect(_overlay(es)).to_contain_text("Selection limit reached (1 of 1)")
    expect(es.candidate_cards().nth(1)).to_be_disabled()


def test_complete_is_blocked_when_required_is_lowered_below_selected(engineer_selection):
    """OP-29 AC #3, decrease path (Qase #106): lowering Required below the selected count keeps the selection, but
    Complete is disabled and the planner is told how many to remove."""
    engineer_selection.increase_support_engineers()  # Required: 2
    es = _open_map_ready(engineer_selection)
    es.candidate_cards().nth(0).click()
    es.candidate_cards().nth(1).click()
    es.complete_map()
    engineer_selection.decrease_support_engineers()  # Required: 1
    es.open_map()
    expect(_overlay(es)).to_contain_text("More engineers selected than required (1). Remove 1 to complete the selection.")
    expect(_overlay(es).get_by_role("button", name="Complete", exact=True)).to_be_disabled()


def test_deselecting_a_candidate_allows_choosing_another(engineer_selection):
    """OP-29 AC #4: deselect a previously selected FSE and choose another."""
    es = _open_map_ready(engineer_selection)
    first = _suggested_names(es)[0]
    es.candidate_cards().first.click()
    expect(es.map_selected_required_text()).to_have_text("Selected 1 / Required 1")
    _overlay(es).get_by_role("button", name=first, exact=False).first.click()
    expect(es.map_selected_required_text()).to_have_text("Selected 0 / Required 1")
    es.candidate_cards().nth(1).click()
    expect(es.map_selected_required_text()).to_have_text("Selected 1 / Required 1")


def test_unlisted_employee_can_be_found_by_search_and_added(engineer_selection):
    """OP-29 AC #5 (rewritten 2026-09-30; Qase #107, fixed): an employee that is not in the suggested list can be
    searched and added to the selection."""
    es = _open_map_ready(engineer_selection)
    assert "Marcela Vargas" not in _suggested_names(es), "precondition: Marcela Vargas must not be a suggestion"
    _search(es, "Marcela")
    expect(_overlay(es)).to_contain_text('1 match for "Marcela"')
    es.candidate_cards().first.click()
    es.complete_map()
    expect(engineer_selection.root.get_by_text("Selected:", exact=False)).to_have_text("Selected: 1 · Required: 1")
    expect(engineer_selection.field("Field Leader").locator("option:checked")).to_have_text("Marcela Vargas")
    expect(engineer_selection.root.get_by_text("Contractor", exact=True)).not_to_be_visible()


def test_adding_a_contractor_when_candidates_are_insufficient(engineer_selection):
    """OP-29 AC #6: provide an option to add a contractor/external staffing when internal candidates are
    insufficient."""
    es = _open_map_ready(engineer_selection)
    name, phone, location = _open_contractor_form(es)
    name.fill("Juan Perez Contratista")
    phone.fill("555-1234")
    location.fill("La Paz")
    es.add_and_select_contractor()
    expect(es.map_selected_required_text()).to_have_text("Selected 1 / Required 1")
    es.complete_map()
    expect(engineer_selection.field("Field Leader").locator("option:checked")).to_have_text("Juan Perez Contratista")
    expect(engineer_selection.root.get_by_text("Contractor", exact=True)).to_be_visible()


def test_search_box_filters_candidate_list(engineer_selection):
    """OP-29 AC #5 / 'SEARCH OR SELECT ENGINEER' (Qase #109, fixed): typing a name filters the list."""
    es = _open_map_ready(engineer_selection)
    first = _suggested_names(es)[0]
    _search(es, first[:4])
    expect(_overlay(es)).to_contain_text("1 match for")
    assert _suggested_names(es) == [first]


def test_search_box_enforces_max_length(engineer_selection):
    """Qase #110, search box, length part (fixed): the field limits its input to 100 characters."""
    es = _open_map_ready(engineer_selection)
    box = _search(es, "A" * 300)
    assert len(box.input_value()) == 100


def test_search_box_rejects_script_and_emoji(engineer_selection):
    """Qase #110, search box, content part: same input standard as the Contractor fields (angle brackets and emoji
    are removed)."""
    es = _open_map_ready(engineer_selection)
    box = _search(es, "<script>alert(1)</script>")
    assert "<" not in box.input_value() and ">" not in box.input_value()
    box = _search(es, "📞 Pedro")
    assert box.input_value().strip() == "Pedro"


def test_contractor_fields_sanitize_markup_sql_emoji_and_enforce_limits(engineer_selection):
    """Qase #110 (fixed for the Contractor form): angle brackets and emoji are stripped, Phone keeps only phone
    characters, and each field has a maximum length (Name 100, Phone 30, Location 120)."""
    es = _open_map_ready(engineer_selection)
    name, phone, location = _open_contractor_form(es)
    name.fill("")
    name.type("<script>alert(1)</script>", delay=5)
    assert "<" not in name.input_value() and ">" not in name.input_value()
    name.fill("")
    name.type("\U0001F4DE Juan", delay=5)
    assert name.input_value().strip() == "Juan"
    phone.click()
    phone.press_sequentially("\U0001F4DE123abc", delay=80)  # human speed: at 5 ms the caret jumps after the emoji is stripped (probe 2026-11-09)
    assert phone.input_value() == "123"
    location.type("<img src=x onerror=alert(1)>", delay=5)
    assert "<" not in location.input_value() and ">" not in location.input_value()
    name.fill("")
    name.type("A" * 300, delay=0)
    location.fill("")
    location.type("B" * 300, delay=0)
    assert len(name.input_value()) == 100
    assert len(location.input_value()) == 120


def test_map_provides_clear_close_save_draft_and_complete(engineer_selection):
    """Qase #111 (fixed), V13/V14 button set: Clear resets Selected to 0, Close discards, Save Draft keeps the
    selection to resume later, Complete applies it."""
    es = _open_map_ready(engineer_selection)
    for label in ("Clear", "Close", "Save Draft", "Complete"):
        expect(_overlay(es).get_by_role("button", name=label, exact=True)).to_be_visible()
    es.candidate_cards().first.click()
    _overlay(es).get_by_role("button", name="Clear", exact=True).click()
    expect(es.map_selected_required_text()).to_have_text("Selected 0 / Required 1")
    es.candidate_cards().first.click()
    es.close_map()
    expect(engineer_selection.root.get_by_text("Selected:", exact=False)).to_have_text("Selected: 0 · Required: 1")
    _open_map_ready(engineer_selection)
    es.candidate_cards().first.click()
    _overlay(es).get_by_role("button", name="Save Draft", exact=True).click()
    expect(engineer_selection.root).to_contain_text("Draft selection saved (1 engineer)")
    es.open_map()
    expect(_overlay(es)).to_contain_text("Resuming your saved draft selection.")
    expect(es.map_selected_required_text()).to_have_text("Selected 1 / Required 1")
    es.complete_map()
    expect(engineer_selection.root.get_by_text("Selected:", exact=False)).to_have_text("Selected: 1 · Required: 1")


def test_error_state_offers_retry_and_manual_add_on_load_failure(quotation_page):
    """OP-29 AC #7 (Qase #108, fixed): if the candidate data fails to load, MAP shows a clear message with Retry and
    'Add engineer manually'; Retry reloads the list. The catalog is requested when the Site is selected, so the
    route is installed before reloading the app."""
    page = quotation_page.page
    # the app keeps the employees catalog in memory for the whole session: reload so the blocked request is made again
    page.route("**/api/amxcpcatalog/employees*", lambda route: route.abort())
    page.reload()
    wo = quotation_page.create_quotation().wo_snapshot()
    wo.field("Customer").select_option(index=1)
    expect(wo.field("Site Name").locator("option")).not_to_have_count(1)
    try:
        wo.field("Site Name").select_option(index=1)
        page.wait_for_timeout(1500)
        quotation_page.fse_arrangement().open_fse_select_tab()
        es = quotation_page.engineer_selection().open_map()
        overlay = _overlay(es)
        expect(overlay).to_contain_text("Couldn’t load the engineer list.")
        expect(overlay.get_by_role("button", name="Add engineer manually")).to_be_visible()
        page.unroute("**/api/amxcpcatalog/employees*")
        overlay.get_by_role("button", name="Retry", exact=True).click()
        es.candidate_cards().first.wait_for(timeout=15000)
        assert es.candidate_cards().count() >= 1
        es.close_map()
    finally:
        try:
            page.unroute("**/api/amxcpcatalog/employees*")
        except Exception:
            pass
        overlay = page.locator("div.fixed.inset-0")
        if overlay.count() > 0 and overlay.last.is_visible():
            overlay.last.get_by_role("button", name=loc.MAP_CLOSE_BUTTON_TEXT, exact=True).click()
        quotation_page.close_form()


def test_long_search_text_stays_inside_the_map_side_panel(engineer_selection):
    """Layout check: a 100-character search text without spaces (the field's maximum) must not push the 'N matches
    for ...' and 'No matching engineer for ...' messages outside their card. Measured, not eyeballed: each message's
    content width (scrollWidth) must fit its own box (clientWidth)."""
    es = _open_map_ready(engineer_selection)
    _search(es, "W" * 100)
    expect(_overlay(es)).to_contain_text("No matching engineer for")
    overflow = _overlay(es).evaluate("""o => [...o.querySelectorAll('span, p')]
        .filter(e => /^(0 matches for|No matching engineer for)/.test(e.innerText.trim()))
        .map(e => ({text: e.innerText.trim().slice(0, 30), scroll: e.scrollWidth, client: e.clientWidth}))
        .filter(m => m.scroll > m.client + 1)""")
    assert overflow == [], f"messages wider than their box: {overflow}"
