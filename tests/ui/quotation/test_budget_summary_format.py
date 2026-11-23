"""Quotation module -- Budget Summary, number format and validations on screen (OP-23 / HU-15; Qase suite "HU-15: BU and OEM view of the Budget Summary", cases FV*).

HU-15 'Validations, format and messages': amounts show a '$' and no decimals; the inputs do not accept decimals; a value loaded with decimals (an AMXCP customer rate or a
restored draft) is rounded to the nearest whole number (.5 rounds up); no calculated figure shows decimals; the thousands separator follows the browser language
(English '$1,200' and '$12,000', German '$1.200' and '$12.000', Spanish of Spain '$1200' and '$12.000', which is expected); if the quotation fails to load the page shows its
own error and the Budget Summary is not available. The server side of the whole-number rule is in tests/api/quotation/test_budget_summary_api.py.
"""
import json
import re

import pytest

from framework_api.services import quotation_setup as qs
from playwright.sync_api import expect

from framework_ui.pages.auth.login_page import LoginPage
from framework_ui.pages.quotation.components.budget_summary import number
from framework_ui.pages.quotation.quotation_page import QuotationPage
from shared.config.credentials import load_role_credentials
from shared.config.settings import BASE_URL

pytestmark = pytest.mark.ui

SOW, LABOR, ONSITE, REIMB = "Statement of Work (SOW)", "Labor Cost", "Onsite Support Costs", "Reimbursable Costs"
STATEMENT, LABOR_COSTS = "Statement of FSE Resource", "Labor Costs"

NUMERIC_FIELDS = [(STATEMENT, "Support Engineers"), (STATEMENT, "Working Hour / Tech Day"), (STATEMENT, "Estimated Working Days"), (LABOR_COSTS, "Labor Cost / Hour"),
                  (LABOR_COSTS, "Labor Over Cost / Hour"), (ONSITE, "Hotel Cost"), (ONSITE, "Per Diem / Person"), (ONSITE, "Travel / Drive Time"),
                  (REIMB, "Air Transportation"), (REIMB, "Car Expense"), (REIMB, "Material Expense"), (REIMB, "Equipment Rental"), (REIMB, "Miscellaneous")]

SEPARATORS = dict(supportEngineers=2, workingHourTechDay=8, estimatedWorkingDays=1, totalOverHoursTech=0, laborCostHour=100, laborOverCostHour=150, hotelCost=1200, perDiem=100,
                  travelDriveTime=0, airTransportation=12000, carExpense=500, materialExpense=0, equipmentRental=0, miscellaneous=0)
ODD = dict(supportEngineers=3, workingHourTechDay=9, estimatedWorkingDays=3, totalOverHoursTech=1, laborCostHour=33, laborOverCostHour=47, hotelCost=101, perDiem=17,
           travelDriveTime=7, airTransportation=999, carExpense=333, materialExpense=77, equipmentRental=55, miscellaneous=11)


def group_digits(n, locale):
    """How the browser writes a whole number: English '1,200'; German '1.200'; Spanish of Spain groups only from 5 digits ('1200', '12.000')."""
    if locale == "en-US":
        return f"{n:,}"
    if locale == "de-DE":
        return f"{n:,}".replace(",", ".")
    if locale == "es-ES":
        return f"{n:,}".replace(",", ".") if n >= 10000 else str(n)
    raise ValueError(locale)


@pytest.fixture(scope="module")
def quotes(make_waiting_for_bu):
    return {"separators": make_waiting_for_bu("SEP", arrangement=SEPARATORS, title_prefix="HU15-FV"),
            "odd": make_waiting_for_bu("ODD", arrangement=ODD, title_prefix="HU15-FV"),
            "select": make_waiting_for_bu("SEL", title_prefix="HU15-FV", extra=qs.three_engineers())}


@pytest.fixture(scope="module")
def locale_page(_role_browser):
    """locale_page('de-DE') -> a page signed in as the BU approver whose browser language is that locale (one login per locale)."""
    pages = {}

    def get(locale):
        if locale not in pages:
            creds = load_role_credentials("BU")
            page = _role_browser.new_isolated_page(locale=locale)
            LoginPage(page).login(creds["email"], creds["password"], method="native")
            page.wait_for_url(lambda url: "/login" not in url, timeout=20000)
            pages[locale] = page
        return pages[locale]
    return get


def sheet_in(locale_page, locale, quote):
    return QuotationPage(locale_page(locale)).open_by_link(quote[0]).budget_summary().open()


# ================================================================================================ amounts: dollar sign, no decimals, thousands separator
@pytest.mark.parametrize("locale", ["en-US", "de-DE", "es-ES"])
def test_amounts_are_shown_with_the_thousands_separator_of_the_browser_language(locale_page, quotes, locale):
    """Qase HU15-FV3 (English), HU15-FV4 (German) and HU15-FV5 (Spanish of Spain)."""
    bs = sheet_in(locale_page, locale, quotes["separators"])
    assert bs.line(ONSITE, "Hotel Cost").quotation == "$" + group_digits(1200, locale)
    assert bs.line(REIMB, "Air Transportation (2 tickets)").quotation == "$" + group_digits(12000, locale)
    total = number(bs.line(None, "Total Cost").quotation)
    assert bs.line(None, "Total Cost").quotation == "$" + group_digits(total, locale)
    assert bs.footer_total() == "$" + group_digits(total, locale)


def test_amounts_have_a_dollar_sign_and_no_decimals(locale_page, quotes):
    """Qase HU15-FV1 -- in English every amount is '$' + digits and thousands commas, never '.dd'."""
    bs = sheet_in(locale_page, "en-US", quotes["odd"])
    amounts = [ln for ln in bs.lines() if ln.quotation.startswith("$")]
    assert len(amounts) >= 12
    for ln in amounts:
        assert re.fullmatch(r"\$\d{1,3}(,\d{3})*", ln.quotation), f"{ln.label}: {ln.quotation!r}"
    assert re.fullmatch(r"\$\d{1,3}(,\d{3})*", bs.footer_total())


def test_no_calculated_figure_shows_decimals(locale_page, quotes):
    """Qase HU15-FV2 -- odd inputs (3 engineers, 9 h/day, 3 days, $33, $47...): every figure of the sheet is a whole number."""
    bs = sheet_in(locale_page, "en-US", quotes["odd"])
    for ln in bs.lines():
        if ln.spans_both:
            continue
        assert re.fullmatch(r"\$?\d{1,3}(,\d{3})*", ln.quotation), f"{ln.label}: {ln.quotation!r}"


# ================================================================================================ the inputs do not accept decimals
@pytest.fixture(scope="module")
def draft_for_inputs(make_draft):
    return make_draft("FVINPUT")


@pytest.mark.parametrize("section, label", NUMERIC_FIELDS)
def test_the_numeric_inputs_do_not_accept_decimals(role_page, draft_for_inputs, section, label):
    """Qase HU15-FV6 -- typing 7.5, 7,5 or 1050.75 never leaves a decimal point or comma in the field."""
    qp = QuotationPage(role_page("AM")).open_by_link(draft_for_inputs[0])
    field = qp.fse_arrangement().field(section, label)
    for typed in ("7.5", "7,5", "1050.75"):
        field.click()
        field.press("Control+A")
        field.press("Delete")
        field.type(typed, delay=10)
        assert re.fullmatch(r"\d*", field.input_value()), f"{label}: typed {typed!r}, the field holds {field.input_value()!r}"


def test_the_units_input_does_not_accept_decimals(role_page, draft_for_inputs):
    """Qase HU15-FV6 (Units, in WO Snapshot)."""
    qp = QuotationPage(role_page("AM")).open_by_link(draft_for_inputs[0])
    units = qp.wo_snapshot().field("Units")
    units.click()
    units.press("Control+A")
    units.type("5.5", delay=10)
    assert re.fullmatch(r"\d*", units.input_value()), units.input_value()


# ================================================================================================ rounding of values loaded with decimals
def test_a_customer_rate_with_decimals_is_rounded_to_the_nearest_whole_number(role_page):
    """Qase HU15-FV7 -- the AMXCP rate of Northwind Utilities is $138.50 per hour: the form and the sheet show $139 (.5 rounds up)."""
    qp = QuotationPage(role_page("AM")).open(refresh=True).create_quotation()
    wo = qp.wo_snapshot()
    wo.field("Customer").select_option(label="Northwind Utilities")
    expect(wo.field("Site Name").locator("option")).not_to_have_count(1)
    wo.field("Site Name").select_option(index=1)
    qp.page.wait_for_timeout(2000)
    assert qp.fse_arrangement().field(LABOR_COSTS, "Labor Cost / Hour").input_value() == "139"
    assert qp.budget_summary().open().line(LABOR, "Labor Cost/Hr").quotation == "$139"


def restore_draft_with(page, updates):
    """Types a value in a blank form, edits the draft the browser keeps (quotation_current:*) so that it holds `updates`, reloads and restores it with Current Quote.
    Returns the values the form shows."""
    qp = QuotationPage(page).open(refresh=True).create_quotation()
    qp.fse_arrangement().field(LABOR_COSTS, "Labor Cost / Hour").fill("77")
    page.wait_for_timeout(1500)
    key = next(k for k in page.evaluate("() => Object.keys(localStorage)") if k.startswith("quotation_current:"))
    data = json.loads(page.evaluate("(k) => localStorage.getItem(k)", key))
    data["formData"].update(updates)
    page.evaluate("([k, v]) => localStorage.setItem(k, v)", [key, json.dumps(data)])
    page.reload()
    page.wait_for_timeout(2500)
    page.get_by_role("button", name="Current Quote").click()
    page.get_by_text("WO Snapshot", exact=True).wait_for(timeout=20000)
    qp = QuotationPage(page)
    fse = qp.fse_arrangement()
    got = {"hours": fse.field(STATEMENT, "Working Hour / Tech Day").input_value(), "labor": fse.field(LABOR_COSTS, "Labor Cost / Hour").input_value(),
           "hotel": fse.field(ONSITE, "Hotel Cost").input_value(), "per_diem": fse.field(ONSITE, "Per Diem / Person").input_value(),
           "engineers": fse.field(STATEMENT, "Support Engineers").input_value(), "days": fse.field(STATEMENT, "Estimated Working Days").input_value(),
           "units": qp.wo_snapshot().field("Units").input_value()}
    qp.close_form()
    return got


def test_a_restored_draft_with_decimals_has_its_amounts_and_hours_rounded(role_page):
    """Qase HU15-FV8 -- the draft kept in the browser holds decimals; restored with Current Quote, .5 rounds up and below .5 rounds down."""
    got = restore_draft_with(role_page("AM"), dict(workingHoursPerTechDay=7.5, laborCostPerHour=50.5, hotelCost=1050.4, perDiem=99.6))
    assert (got["hours"], got["labor"], got["hotel"], got["per_diem"]) == ("8", "51", "1050", "100"), got


def test_a_restored_draft_with_decimals_has_its_counts_rounded(role_page):
    """Qase HU15-FV10 -- Support Engineers 2.5 -> 3, Estimated Working Days 2.4 -> 2, Units 5.5 -> 6."""
    got = restore_draft_with(role_page("AM"), dict(supportEngineers=2.5, estimatedWorkingDays=2.4, units=5.5))
    assert (got["engineers"], got["days"], got["units"]) == ("3", "2", "6"), got


# ================================================================================================ the quotation fails to load
def test_when_the_quotation_fails_to_load_the_page_shows_its_error_and_no_budget_summary(role_page, make_draft):
    """Qase HU15-FV9 -- the request that loads the quotation is cut: the quotation page shows its own error and the footer button does not exist."""
    qid, _ = make_draft("FVLOAD")
    page = role_page("AM")
    quotation_url = re.compile(r"/api/quotations/[0-9a-f-]{36}$")
    page.route("**/api/**", lambda route: route.abort() if (route.request.method == "GET" and quotation_url.search(route.request.url.split("?")[0])) else route.continue_())
    try:
        page.goto(f"{BASE_URL}/quotation/{qid}")
        expect(page.get_by_text("Could not connect to the server", exact=False).first).to_be_visible(timeout=20000)
        assert page.get_by_text("WO Snapshot", exact=True).count() == 0
        assert page.get_by_role("button", name=re.compile("Budget Summary")).count() == 0, "the Budget Summary must not be available"
    finally:
        page.unroute("**/api/**")


# ================================================================================================ the same format rules in an FSE Select sheet
@pytest.mark.parametrize("locale", ["en-US", "de-DE", "es-ES"])
def test_the_fse_select_sheet_uses_the_thousands_separator_of_the_browser_language(locale_page, quotes, locale):
    """Qase HU15-FV13 (English), FV14 (German), FV15 (Spanish of Spain) -- Service Fee '$110 x 24 h = $2,640', the engineer Total, the Final Total and the footer Total."""
    bs = sheet_in(locale_page, locale, quotes["select"])
    sheet = bs.select_sheet()
    block = {b["name"]: b for b in sheet["blocks"]}["Pedro Aguilar"]
    assert block["lines"]["Service Fee"][0] == f"$110 × 24 h = ${group_digits(2640, locale)}"
    assert block["lines"]["Total"][0] == "$" + group_digits(4225, locale)
    assert sheet["final"][0] == "$" + group_digits(11225, locale)
    assert bs.footer_total() == "$" + group_digits(11225, locale)


def test_every_amount_of_the_fse_select_sheet_has_a_dollar_sign_and_no_decimals_and_hours_have_none(locale_page, quotes):
    """Qase HU15-FV16 -- in English: '$' + digits with commas for amounts, none for the hours of 'rate × hours = total', and no decimal point anywhere."""
    bs = sheet_in(locale_page, "en-US", quotes["select"])
    sheet = bs.select_sheet()
    cells = [v[0] for b in sheet["blocks"] for v in b["lines"].values()] + [sheet["final"][0], bs.footer_total()]
    for text in cells:
        assert re.fullmatch(r"\$\d{1,3}(,\d{3})*( × \d+ h = \$\d{1,3}(,\d{3})*)?", text) or re.fullmatch(r"\$\d{1,3}(,\d{3})* × \d+ h = \$\d{1,3}(,\d{3})*", text), text
