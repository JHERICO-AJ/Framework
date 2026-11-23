"""Quotation module -- FSE Arrangement (OP-20 / HU-09, Qase #875) and FSE Select (OP-28 / HU-10, Qase #893): what does NOT depend on the browser language, in 3 browser languages.
Separate file because it signs in with its own browser per language (the same pattern as test_budget_calculator.py) and cannot share a session with the
tests that use the quotation_page fixture."""
import re

import pytest
from playwright.sync_api import expect

from framework_api.services import quotation_setup as qs
from framework_ui.pages.auth.login_page import LoginPage
from framework_ui.pages.quotation.components import fse_arrangement_locators as loc
from framework_ui.pages.quotation.quotation_page import QuotationPage
from shared.config.credentials import load_role_credentials

pytestmark = pytest.mark.ui


def _type(page, field, text):
    field.click()
    page.keyboard.press("Control+A")
    page.keyboard.press("Delete")
    page.keyboard.type(text)
    return field.input_value()


@pytest.fixture(scope="module")
def am_in_language(_role_browser):
    """am_in_language('de-DE') -> a page signed in as the AM whose browser language is that locale (one login per locale)."""
    pages = {}

    def get(locale):
        if locale not in pages:
            creds = load_role_credentials("AM")
            page = _role_browser.new_isolated_page(locale=locale)
            LoginPage(page).login(creds["email"], creds["password"], method="native")
            page.wait_for_url(lambda url: "/login" not in url, timeout=20000)
            pages[locale] = page
        return pages[locale]
    return get


@pytest.mark.parametrize("locale", ["en-US", "de-DE", "es-ES"])
def test_date_picker_and_decimal_rule_do_not_depend_on_the_browser_language(am_in_language, make_draft, locale):
    """Qase #875 (automated in 3 browser languages, 2026-11-06). The date fields keep the MM/DD/YYYY placeholder and the English calendar whatever the
    browser language is, and typing a decimal separator (dot or comma) keeps no decimals in any language.
    NOT covered here, observed 2026-11-06: the thousands separator of the money totals DOES follow the browser language ($125,536 in en-US, $125.536 in
    de-DE and es-ES), see the question to the developer."""
    quotation_id, _ = make_draft("FSELOC", title_prefix="HU09")
    page = am_in_language(locale)
    fse = QuotationPage(page).open_by_link(quotation_id).fse_arrangement()
    start = fse.field(loc.SECTION_HEADING_STATEMENT, loc.LABEL_EST_START_TIME)
    assert start.get_attribute("placeholder") == "MM/DD/YYYY"
    start.click()
    expect(page.get_by_text("Today", exact=True)).to_be_visible()
    expect(page.get_by_text(re.compile(r"^(January|February|March|April|May|June|July|August|September|October|November|December) \d{4}$"))).to_be_visible()
    page.keyboard.press("Escape")
    for separator in (".", ","):
        assert not re.search(r"[.,]", _type(page, fse.field(loc.SECTION_HEADING_ONSITE, loc.LABEL_HOTEL_COST), f"2{separator}5")), f"{locale}: a decimal separator was kept"


@pytest.mark.parametrize("locale", ["en-US", "de-DE", "es-ES"])
def test_planned_check_in_out_format_does_not_depend_on_the_browser_language(am_in_language, make_draft, locale):
    """Qase #893 (HU-10, automated in 3 browser languages 2026-11-09): Planned Check-in/out keep the 'MM/DD/YYYY h:mm AA' placeholder, show their value in that
    format (month/day/year, 12-hour clock with AM/PM) and open the English calendar, whatever the browser language is."""
    engineers = list(qs.ENGINEERS)
    quotation_id, _ = make_draft("FSESELLOC", title_prefix="HU10-API", extra=qs.select_extra((engineers[0], None, None), (engineers[1], None, None)))
    page = am_in_language(locale)
    panel = QuotationPage(page).open_by_link(quotation_id).engineer_selection()
    for label in ("Planned Check-in", "Planned Check-out"):
        field = panel.field(label)
        assert field.get_attribute("placeholder") == "MM/DD/YYYY h:mm AA", f"{locale}: {label} placeholder"
        value = field.input_value()
        assert not value or re.fullmatch(r"\d{2}/\d{2}/\d{4} \d{1,2}:\d{2} (AM|PM)", value), f"{locale}: {label} shows {value!r}"
    panel.field("Planned Check-in").click()
    expect(page.get_by_text("Today", exact=True)).to_be_visible()
    expect(page.get_by_text(re.compile(r"^(January|February|March|April|May|June|July|August|September|October|November|December) \d{4}$"))).to_be_visible()
    page.keyboard.press("Escape")
