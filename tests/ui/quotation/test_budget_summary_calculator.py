"""Quotation module -- Budget Summary and the Budget Calculator (OP-23 / HU-15; Qase suite "HU-15: BU and OEM view of the Budget Summary", cases CA*).

Only what HU-15 says about the calculator: 'The figures must be the ones confirmed in the Budget Calculator (CALCULATE)'; 'An engineer whose calculator hasn't been confirmed must show all figures as $0';
the footer Total is the Final Total ('—' while no selected engineer has calculator figures); 'Amounts and hours must be whole numbers. The inputs must not accept decimals'.
How the calculator itself calculates is another story (HU-12) and is not tested here.
"""
import pytest

from framework_api.services import quotation_setup as qs
from framework_ui.pages.quotation.components.budget_summary import number
from framework_ui.pages.quotation.quotation_page import QuotationPage

pytestmark = pytest.mark.ui

PEDRO = dict(rate=110, hours=24, ot_rate=165, ot_hours=4, equipment=250, travel=615, misc=60)       # Total 4,225
EMPLOYEE = dict(rate=110, hours=24, equipment=180, travel=880)                                          # Total 3,700
ZERO = ((0, 0, 0), (0, 0, 0), 0, 0, 0, 0)


def fee(text):
    import re
    m = re.fullmatch(r"\$([\d.,]+) × ([\d.,]+) h = \$([\d.,]+)", text.strip())
    assert m, text
    return tuple(number(g) for g in m.groups())


def block_figures(block):
    lines = block["lines"]
    cell = lambda label: lines[label][0]
    return (fee(cell("Service Fee")), fee(cell("Overwork Service")), number(cell("Equipment")), number(cell("Travel Expenses")), number(cell("MISCELLANEOUS")), number(cell("Total")))


@pytest.fixture()
def unconfirmed(make_draft):
    """A fresh Draft with two engineers selected and no calculator figures."""
    return make_draft("CALC", extra=qs.select_extra(("Pedro Aguilar", None, None), ("Employee L01200", None, None)))[0]


def sheet_by_name(page_obj):
    bs = page_obj.budget_summary()
    bs.open()
    sheet = {b["name"]: b for b in bs.select_sheet()["blocks"]}
    final = bs.select_sheet()["final"][0]
    bs.close_with_button()
    return sheet, final


def test_the_sheet_shows_the_figures_confirmed_in_the_calculator(role_page, unconfirmed):
    """Qase HU15-CA1 -- engineers with no figures show $0 and the footer Total a dash; after the AM confirms the calculator the sheet shows the figures and the footer Total is the Final Total, with no reload."""
    qp = QuotationPage(role_page("AM")).open_by_link(unconfirmed)
    bs = qp.budget_summary()
    assert bs.footer_total() == "—"
    before, _ = sheet_by_name(qp)
    assert all(block_figures(b) == ZERO for b in before.values())
    calc = qp.budget_calculator().open()
    calc.select_engineer("Pedro Aguilar").fill_figures(**PEDRO)
    calc.confirm()
    after, final = sheet_by_name(qp)
    assert block_figures(after["Pedro Aguilar"]) == ((110, 24, 2640), (165, 4, 660), 250, 615, 60, 4225)
    assert block_figures(after["Employee L01200"]) == ZERO, "an engineer whose calculator was not confirmed stays at $0"
    assert number(final) == 4225 and number(bs.footer_total()) == 4225


def test_with_both_engineers_confirmed_the_final_total_and_the_footer_add_them_up(role_page, unconfirmed):
    """Qase HU15-CA2"""
    qp = QuotationPage(role_page("AM")).open_by_link(unconfirmed)
    calc = qp.budget_calculator().open()
    calc.select_engineer("Pedro Aguilar").fill_figures(**PEDRO)
    calc.select_engineer("Employee L01200").fill_figures(**EMPLOYEE)
    calc.confirm()
    sheet, final = sheet_by_name(qp)
    assert block_figures(sheet["Pedro Aguilar"])[-1] == 4225 and block_figures(sheet["Employee L01200"]) == ((110, 24, 2640), (0, 0, 0), 180, 880, 0, 3700)
    assert number(final) == 7925 and number(qp.budget_summary().footer_total()) == 7925


NUMBER_INPUTS = ["hourly rate", "total hours", "overtime rate", "overtime hours", "equipment qty", "equipment price", "flight", "car rental", "hotel", "meals", "gas", "parking", "toll", "other travel",
                 "miscellaneous qty", "miscellaneous price"]


@pytest.mark.parametrize("index, name", list(enumerate(NUMBER_INPUTS)))
def test_the_calculator_inputs_do_not_accept_decimals(role_page, unconfirmed, index, name):
    """Qase HU15-CA3 -- 'The inputs must not accept decimals': typing 7.5, 7,5 or 1050.75 never leaves a decimal point or comma in the field."""
    import re
    qp = QuotationPage(role_page("AM")).open_by_link(unconfirmed)
    field = qp.budget_calculator().open().numbers().nth(index)
    for typed in ("7.5", "7,5", "1050.75"):
        field.click()
        field.press("Control+A")
        field.press("Delete")
        field.type(typed, delay=10)
        assert re.fullmatch(r"\d*", field.input_value()), f"{name}: typed {typed!r}, the field holds {field.input_value()!r}"
