"""Quotation module -- Budget Summary, opening and layout of the panel (OP-23 / HU-15; Qase suite "HU-15: BU and OEM view of the Budget Summary", cases OL*).

HU-15 'Opening and layout': the footer button opens the panel above the footer and then reads 'Hide Budget Summary'; clicking it again, 'Close', Esc or a click
outside the footer hide it without reloading the form; Esc in a form field and Esc or a click outside while a modal is open do not hide it; three read-only
cards; two tabs (BU View first, the last one is kept while the page stays open, a reload goes back to BU View); both tabs show the same figures and switching
tabs changes nothing; the panel loads no data of its own.

Quotations are created through the API: a Draft (the AM can edit it) and a submitted one (to open as the approvers). Opened by their own link.
"""
import re
import time

import pytest
from playwright.sync_api import expect

from framework_ui.pages.quotation.quotation_page import QuotationPage

pytestmark = pytest.mark.ui

FORM_MARKER = "WO Snapshot"


@pytest.fixture(scope="module")
def draft(make_draft):
    return make_draft("PANEL")


@pytest.fixture(scope="module")
def pending(make_waiting_for_bu):
    return make_waiting_for_bu("PANEL", title_prefix="HU15", route=("FPM", "BU", "CEO"))


def open_draft(role_page, draft):
    return QuotationPage(role_page("AM")).open_by_link(draft[0])


def form_is_open(page):
    return page.get_by_text(FORM_MARKER, exact=True).count() == 1


# ================================================================================================ open and hide
def test_the_button_opens_the_panel_above_the_footer_and_then_reads_hide(role_page, draft):
    """Qase HU15-OL1"""
    qp = open_draft(role_page, draft)
    bs = qp.budget_summary()
    assert bs.has_button() and bs.button_text() == "Budget Summary" and not bs.is_open()
    bs.open()
    assert bs.is_open() and bs.button_text() == "Hide Budget Summary"
    panel, button = bs.box_of_panel_and_button()
    assert panel["y"] + panel["height"] <= button["y"] + 2, "the panel must sit above the footer"


def test_clicking_the_button_again_hides_the_panel_without_reloading_the_form(role_page, draft):
    """Qase HU15-OL2 -- a value typed and not saved is still there afterwards."""
    qp = open_draft(role_page, draft)
    page, bs = qp.page, qp.budget_summary()
    qp.wo_snapshot().field("OEM Name").fill("Typed and not saved")
    bs.open()
    bs.button().first.click()
    page.wait_for_timeout(400)
    assert not bs.is_open() and bs.button_text() == "Budget Summary"
    assert form_is_open(page) and qp.wo_snapshot().field("OEM Name").input_value() == "Typed and not saved"


def test_the_close_button_hides_the_panel(role_page, draft):
    """Qase HU15-OL3"""
    qp = open_draft(role_page, draft)
    bs = qp.budget_summary().open()
    bs.close_with_button()
    assert not bs.is_open() and form_is_open(qp.page)


def test_esc_hides_the_panel(role_page, draft):
    """Qase HU15-OL4"""
    qp = open_draft(role_page, draft)
    bs = qp.budget_summary().open()
    qp.page.keyboard.press("Escape")
    qp.page.wait_for_timeout(400)
    assert not bs.is_open() and form_is_open(qp.page)


def test_a_click_outside_the_footer_hides_the_panel(role_page, draft):
    """Qase HU15-OL5"""
    qp = open_draft(role_page, draft)
    bs = qp.budget_summary().open()
    qp.page.get_by_text(re.compile(r"^QUOTATION \(WO\)", re.I)).first.click()
    qp.page.wait_for_timeout(400)
    assert not bs.is_open() and form_is_open(qp.page)


def test_a_click_inside_the_footer_keeps_the_panel_open(role_page, draft):
    """Qase HU15-OL6"""
    qp = open_draft(role_page, draft)
    bs = qp.budget_summary().open()
    qp.page.get_by_text(re.compile(r"^total$", re.I)).last.click()   # CSS shows it in capitals; the DOM text is "Total"
    qp.page.wait_for_timeout(400)
    assert bs.is_open()


@pytest.mark.parametrize("field", ["textarea", "input[placeholder='Enter OEM name']"])
def test_esc_in_a_form_field_does_not_hide_the_panel(role_page, draft, field):
    """Qase HU15-OL7 -- the focus is in a form field outside the panel (a text area, a text input)."""
    qp = open_draft(role_page, draft)
    bs = qp.budget_summary().open()
    qp.page.evaluate("(sel) => document.querySelector(sel).focus()", field)
    qp.page.keyboard.press("Escape")
    qp.page.wait_for_timeout(400)
    assert bs.is_open()


@pytest.mark.parametrize("action", ["esc", "click_outside"])
def test_esc_and_a_click_outside_do_not_hide_the_panel_while_a_modal_is_open(role_page, make_draft, action):
    """Qase HU15-OL8 -- the 'Saving quotation...' modal of Submit is held for 4 s by delaying the request; Esc, then a click outside the footer."""
    qid, _ = make_draft("PANELMODAL")
    qp = QuotationPage(role_page("AM")).open_by_link(qid)
    page, bs = qp.page, qp.budget_summary().open()

    def slow(route):
        page.wait_for_timeout(4000)
        route.continue_()

    page.route("**/api/quotations/*/submit", slow)
    try:
        page.get_by_role("button", name="Submit Quotation", exact=True).click()
        page.wait_for_timeout(800)
        expect(page.get_by_text(re.compile("Saving quotation"))).to_be_visible()
        if action == "esc":
            page.keyboard.press("Escape")
        else:
            page.mouse.click(300, 600)
        page.wait_for_timeout(500)
        assert page.get_by_text(re.compile("Saving quotation")).count() > 0, "the modal must still be open at the moment of the check"
        assert bs.is_open(), f"{action}: the panel must stay open while a modal is open"
    finally:
        page.wait_for_timeout(4500)
        page.unroute("**/api/quotations/*/submit")


# ================================================================================================ the three cards
def test_the_panel_shows_three_read_only_cards(role_page, draft):
    """Qase HU15-OL9"""
    qp = open_draft(role_page, draft)
    bs = qp.budget_summary().open()
    assert set(bs.cards()) >= {"EST. START TIME", "EST. END TIME", "SUPPORT ENGINEERS"}
    assert bs.input_count() == 0, "the cards cannot be edited: the panel has no input"


def test_the_flat_rate_cards_show_the_fse_arrangement_dates_and_the_engineers(role_page, draft):
    """Qase HU15-OL10 -- dates as MM/dd/yyyy."""
    cards = open_draft(role_page, draft).budget_summary().open().cards()
    assert cards["EST. START TIME"] == "10/01/2026" and cards["EST. END TIME"] == "10/01/2026" and cards["SUPPORT ENGINEERS"] == "2"


def test_a_card_changes_with_the_form_without_reloading(role_page, make_draft):
    """Qase HU15-OL11 -- Support Engineers typed in FSE Arrangement shows in the card while the panel is open, and after closing and reopening it."""
    qid, _ = make_draft("PANELLIVE")
    qp = QuotationPage(role_page("AM")).open_by_link(qid)
    bs = qp.budget_summary().open()
    field = qp.fse_arrangement().field("Statement of FSE Resource", "Support Engineers")
    field.fill("5")
    qp.page.wait_for_timeout(600)
    assert bs.is_open() and bs.cards()["SUPPORT ENGINEERS"] == "5"
    bs.close_with_button()
    field.fill("4")
    qp.page.wait_for_timeout(400)
    assert bs.open().cards()["SUPPORT ENGINEERS"] == "4"


def test_an_empty_date_shows_a_dash(role_page, make_draft):
    """Qase HU15-OL12 -- a quotation with no Est. Start / End Time."""
    qid, _ = make_draft("PANELNODATE", arrangement={"estimacionStartTime": None, "estimacionEndTime": None})
    cards = QuotationPage(role_page("AM")).open_by_link(qid).budget_summary().open().cards()
    assert cards["EST. START TIME"] == "—" and cards["EST. END TIME"] == "—", cards


# ================================================================================================ the tabs
def test_both_tabs_are_shown_below_the_cards(role_page, draft):
    """Qase HU15-OL13"""
    qp = open_draft(role_page, draft)
    qp.budget_summary().open()
    assert qp.page.get_by_role("button", name="BU View", exact=True).count() == 1 and qp.page.get_by_role("button", name="OEM View", exact=True).count() == 1


@pytest.mark.parametrize("role", ["AM", "FPM", "BU", "CEO"])
def test_bu_view_is_selected_the_first_time_for_every_role(role_page, db_conn, pending, role):
    """Qase HU15-OL14"""
    qp = QuotationPage(role_page(role)).open_by_link(pending[0])
    assert qp.budget_summary().open().active_tab() == "BU View"


def test_the_last_tab_is_kept_while_the_page_stays_open_and_a_reload_selects_bu_view(role_page, pending):
    """Qase HU15-OL15 and HU15-OL16"""
    qp = QuotationPage(role_page("AM")).open_by_link(pending[0])
    bs = qp.budget_summary().open()
    bs.select_tab("OEM View")
    assert bs.active_tab() == "OEM View"
    bs.close_with_button()
    bs.open()
    assert bs.active_tab() == "OEM View", "closing and reopening keeps the last selected tab"
    qp.page.reload()
    qp.page.get_by_text(FORM_MARKER, exact=True).wait_for(timeout=20000)
    assert qp.budget_summary().open().active_tab() == "BU View", "a reload selects BU View again"


# ================================================================================================ the panel changes and loads nothing
def test_switching_tabs_does_not_change_or_save_any_value(role_page, api_roles, make_draft):
    """Qase HU15-OL17 -- the quotation as the server has it, and the footer total, are the same before and after switching tabs."""
    qid, _ = make_draft("PANELSWITCH")
    qp = QuotationPage(role_page("AM")).open_by_link(qid)
    bs = qp.budget_summary().open()
    before = api_roles["AM"].get(f"/api/quotations/{qid}").json()
    total_before = bs.footer_total()
    for tab in ("OEM View", "BU View", "OEM View", "BU View"):
        bs.select_tab(tab)
    after = api_roles["AM"].get(f"/api/quotations/{qid}").json()
    assert after["updatedAt"] == before["updatedAt"] and after["totalAmount"] == before["totalAmount"] and after["arrangement"] == before["arrangement"]
    assert bs.footer_total() == total_before


def test_the_panel_makes_no_request_of_its_own(role_page, pending):
    """Qase HU15-OL18 -- opening the panel, switching tabs and closing it send no request to the server."""
    qp = QuotationPage(role_page("BU")).open_by_link(pending[0])
    requests = []
    qp.page.on("request", lambda r: requests.append(r.url) if "/api/" in r.url else None)
    bs = qp.budget_summary().open()
    bs.select_tab("OEM View")
    bs.select_tab("BU View")
    bs.close_with_button()
    qp.page.wait_for_timeout(500)
    assert not requests, f"the Budget Summary must use the quotation already loaded: {requests}"
