"""Quotation module -- Budget Summary, Flat Rate figures (OP-23 / HU-15; Qase suite "HU-15: BU and OEM view of the Budget Summary", cases FR*).

What the sheet must show and how it is calculated comes from the HU-15 text ("Figures: Flat Rate quotation"). The expected figures are
computed here from the quotation's inputs with the story's formulas (the `oracle`), never copied from the screen:
  Since the build of 2026-11-09 (the fix of defect #82 / OP-59, asked by QA and the client) the over hours are typed by the user and ADDED to the regular hours:
  Total Working Hour/Tech = hours/day x days + Total Over Hour/Tech      Total Man Working Hours = Total Working Hour/Tech x engineers
  Labor = engineers x (hours/day x days x rate + Total Over Hour/Tech x over rate)
  Onsite = Hotel + Per Diem x engineers x days + Travel hours x $3        Reimbursable = sum of its five fields        Total Cost = the three subtotals

Quotations are created and submitted through the API (no browser) with chosen FSE Arrangement values, and opened as the BU approver, who sees
the Expense column ('N/D' in Flat Rate). The thousands separator depends on the browser language, so amounts are compared as numbers.
"""
import re

import pytest

from framework_ui.pages.quotation.components.budget_summary import number
from framework_ui.pages.quotation.quotation_page import QuotationPage
from shared.datasource.quotation_db_source import get_quotation_id  # noqa: F401  (kept for the sibling modules)

pytestmark = pytest.mark.ui


def scenario(engineers, hours, days, rate, over_rate, hotel=0, per_diem=0, travel=0, air=0, car=0, material=0, equipment=0, misc=0):
    return dict(supportEngineers=engineers, workingHourTechDay=hours, estimatedWorkingDays=days, totalOverHoursTech=max(hours - 8, 0), laborCostHour=rate,
                laborOverCostHour=over_rate, hotelCost=hotel, perDiem=per_diem, travelDriveTime=travel, airTransportation=air, carExpense=car,
                materialExpense=material, equipmentRental=equipment, miscellaneous=misc)


SCENARIOS = {
    "story_example": scenario(2, 10, 5, 50, 75, hotel=1000, per_diem=100, travel=4, air=3000, car=500, material=200, equipment=300, misc=100),
    "eight_hours": scenario(3, 8, 4, 40, 60, hotel=800, per_diem=80, air=1200, car=300, misc=50),
    "under_eight": scenario(1, 6, 5, 100, 150, hotel=500, per_diem=60, travel=3),
    "twelve_hours": scenario(2, 12, 3, 60, 90, hotel=900, per_diem=120, travel=10, air=2000, car=400, material=100, equipment=200),
    "one_engineer_travel": scenario(1, 9, 2, 45, 70, travel=10),
    "minimal_costs": scenario(1, 8, 1, 1, 0),
}
STORY_EXTRA = {"unitInfo": "Hithium 5.016MWh BESS", "units": 54, "siteLocation": "3609 N SH 60 HWY, East Bernard, Texas 77435-5105", "typeOfWork": "Commissioning"}


def oracle(a):
    over = a["totalOverHoursTech"]
    wh = a["workingHourTechDay"] * a["estimatedWorkingDays"] + over
    man = wh * a["supportEngineers"]
    labor = a["supportEngineers"] * (a["workingHourTechDay"] * a["estimatedWorkingDays"] * a["laborCostHour"] + over * a["laborOverCostHour"])
    onsite = a["hotelCost"] + a["perDiem"] * a["supportEngineers"] * a["estimatedWorkingDays"] + a["travelDriveTime"] * 3
    reimb = a["airTransportation"] + a["carExpense"] + a["materialExpense"] + a["equipmentRental"] + a["miscellaneous"]
    return dict(wh=wh, over=over, man=man, labor=labor, onsite=onsite, reimb=reimb, total=labor + onsite + reimb)


SOW, LABOR, ONSITE, REIMB = "Statement of Work (SOW)", "Labor Cost", "Onsite Support Costs", "Reimbursable Costs"
EXPECTED_LINES = [
    ("", "GSP #"), ("", "Quote#"), ("", "Available date"),
    (SOW, "Type of Work"), (SOW, "Site"), (SOW, "City & State"), (SOW, "Unit Info"), (SOW, "Units"), (SOW, "Technician Needs"),
    (SOW, "Working Hour/Tech/Day"), (SOW, "Estimated Working Days"), (SOW, "Total Working Hour/Tech"), (SOW, "Total Over Hour/Tech (if any)"),
    (SOW, "Total Man Working Hours"),
    (LABOR, "Labor Cost/Hr"), (LABOR, "Labor Cost/Over Hr (if any)"), (LABOR, "Subtotal"),
    (ONSITE, "Hotel Cost"), (ONSITE, "Per Diem"), (ONSITE, "Travel & Drive Time"), (ONSITE, "Subtotal"),
    (REIMB, "Air Transportation (2 tickets)"), (REIMB, "Car Expense (rental, gas, toll)"), (REIMB, "Material Expense"), (REIMB, "Equipment Rental"),
    (REIMB, "Miscellaneous"), (REIMB, "Subtotal"),
    ("", "Total Cost"),
]
TEXT_LINES = [("", "GSP #"), ("", "Quote#"), ("", "Available date"), (SOW, "Type of Work"), (SOW, "Site"), (SOW, "City & State"), (SOW, "Unit Info")]
COUNT_AND_HOUR_LINES = [(SOW, "Units"), (SOW, "Technician Needs"), (SOW, "Working Hour/Tech/Day"), (SOW, "Estimated Working Days"),
                        (SOW, "Total Working Hour/Tech"), (SOW, "Total Over Hour/Tech (if any)"), (SOW, "Total Man Working Hours"), (ONSITE, "Travel & Drive Time")]
AMOUNT_LINES = [(LABOR, "Labor Cost/Hr"), (LABOR, "Labor Cost/Over Hr (if any)"), (LABOR, "Subtotal"), (ONSITE, "Hotel Cost"), (ONSITE, "Per Diem"), (ONSITE, "Subtotal"),
                (REIMB, "Air Transportation (2 tickets)"), (REIMB, "Car Expense (rental, gas, toll)"), (REIMB, "Material Expense"), (REIMB, "Equipment Rental"),
                (REIMB, "Miscellaneous"), (REIMB, "Subtotal"), ("", "Total Cost")]


def find(lines, section, label):
    hits = [ln for ln in lines if ln.label == label and ln.section == section]
    assert len(hits) == 1, f"expected one '{label}' line in {section!r}, found {len(hits)}"
    return hits[0]


def value(lines, section, label):
    return number(find(lines, section, label).quotation)


@pytest.fixture(scope="module")
def quotes(make_waiting_for_bu):
    made = {}
    for name, arrangement in SCENARIOS.items():
        extra = STORY_EXTRA if name == "story_example" else None
        made[name] = make_waiting_for_bu(name, arrangement=arrangement, title_prefix="HU15-FR", extra=extra)
    return made


@pytest.fixture(scope="module")
def sheets(role_page, quotes):
    """Per scenario, the BU approver's Budget Summary read from the screen: {'bu': {header, lines, total}, 'oem': {header, lines}}."""
    out = {}
    page = role_page("BU")
    for name, (qid, quote_no) in quotes.items():
        qp = QuotationPage(page).open_by_link(qid)
        bs = qp.budget_summary().open()
        bu = dict(header=bs.header(), lines=bs.lines(), total=bs.footer_total(), cards=bs.cards())
        bs.select_tab("OEM View")
        oem = dict(header=bs.header(), lines=bs.lines())
        out[name] = dict(bu=bu, oem=oem, quote_no=quote_no)
    return out


# ================================================================================================ the lines of the sheet
def test_the_sheet_shows_every_line_of_the_story_in_order(sheets):
    """Qase HU15-FR1"""
    lines = sheets["story_example"]["bu"]["lines"]
    assert [(ln.section, ln.label) for ln in lines] == EXPECTED_LINES


def test_the_bu_view_header_is_description_quotation_and_expense_for_bu(sheets):
    """Qase HU15-FR2"""
    assert sheets["story_example"]["bu"]["header"] == ["Description", "Quotation/Revenue", "Expense"]


def test_the_header_lines_show_gsp_quote_number_and_available_date(sheets):
    """Qase HU15-FR3 -- the Available date is FSE Arrangement's Est. Start Time (MM/dd/yyyy)."""
    s = sheets["story_example"]
    lines = s["bu"]["lines"]
    assert re.fullmatch(r"Q\d{11}", find(lines, "", "GSP #").quotation)
    assert find(lines, "", "Quote#").quotation == s["quote_no"]
    assert find(lines, "", "Available date").quotation == "10/01/2026"


def test_the_statement_of_work_shows_the_quotation_data(sheets):
    """Qase HU15-FR4 -- type of work, site, city and state (without ZIP code), unit info and units come from the quotation."""
    lines = sheets["story_example"]["bu"]["lines"]
    assert find(lines, SOW, "Type of Work").quotation == "Commissioning"
    assert find(lines, SOW, "Site").quotation == "Valle Verde"
    assert find(lines, SOW, "City & State").quotation == "East Bernard, Texas"
    assert find(lines, SOW, "Unit Info").quotation == "Hithium 5.016MWh BESS"
    assert value(lines, SOW, "Units") == 54


@pytest.mark.parametrize("name", list(SCENARIOS))
def test_the_sheet_repeats_the_arrangement_inputs(sheets, name):
    """Qase HU15-FR5 -- technician needs, hours per day, days and rates are the FSE Arrangement values."""
    a, lines = SCENARIOS[name], sheets[name]["bu"]["lines"]
    assert value(lines, SOW, "Technician Needs") == a["supportEngineers"]
    assert value(lines, SOW, "Working Hour/Tech/Day") == a["workingHourTechDay"]
    assert value(lines, SOW, "Estimated Working Days") == a["estimatedWorkingDays"]
    assert value(lines, LABOR, "Labor Cost/Hr") == a["laborCostHour"]
    assert value(lines, LABOR, "Labor Cost/Over Hr (if any)") == a["laborOverCostHour"]
    assert value(lines, ONSITE, "Hotel Cost") == a["hotelCost"]
    assert value(lines, ONSITE, "Per Diem") == a["perDiem"]
    assert value(lines, ONSITE, "Travel & Drive Time") == a["travelDriveTime"]
    for label, key in [("Air Transportation (2 tickets)", "airTransportation"), ("Car Expense (rental, gas, toll)", "carExpense"), ("Material Expense", "materialExpense"),
                       ("Equipment Rental", "equipmentRental"), ("Miscellaneous", "miscellaneous")]:
        assert value(lines, REIMB, label) == a[key], label


# ================================================================================================ the calculations
@pytest.mark.parametrize("name", list(SCENARIOS))
def test_total_working_hours_are_hours_per_day_times_days_plus_the_over_hours(sheets, name):
    """Qase HU15-FR6 -- since the fix of #82 the over hours are added: 10 h/day, 5 days and 2 over hours -> 52 h."""
    assert value(sheets[name]["bu"]["lines"], SOW, "Total Working Hour/Tech") == oracle(SCENARIOS[name])["wh"]


@pytest.mark.parametrize("name", list(SCENARIOS))
def test_total_over_hours_are_the_ones_typed_in_the_form(sheets, name):
    """Qase HU15-FR7 -- the sheet shows the Total Over Hours / Tech typed in the form (0 when none is typed)."""
    assert value(sheets[name]["bu"]["lines"], SOW, "Total Over Hour/Tech (if any)") == oracle(SCENARIOS[name])["over"]


@pytest.mark.parametrize("name", list(SCENARIOS))
def test_total_man_working_hours_are_total_working_hours_times_engineers(sheets, name):
    """Qase HU15-FR8 -- engineers x Total Working Hour/Tech, which already holds the over hours."""
    assert value(sheets[name]["bu"]["lines"], SOW, "Total Man Working Hours") == oracle(SCENARIOS[name])["man"]


@pytest.mark.parametrize("name", list(SCENARIOS))
def test_the_labor_subtotal_charges_overtime_at_the_overtime_rate_only(sheets, name):
    """Qase HU15-FR9 -- engineers x (hours/day x days x rate + over hours x over rate): 10 h/day, 5 days, 2 engineers, $50/h, $75/over h and 2 over hours -> $5,300."""
    assert value(sheets[name]["bu"]["lines"], LABOR, "Subtotal") == oracle(SCENARIOS[name])["labor"]


def test_the_labor_subtotal_of_the_example_is_5300(sheets):
    """Qase HU15-FR9 (the example of the story, with the 2 over hours typed in the form)."""
    assert value(sheets["story_example"]["bu"]["lines"], LABOR, "Subtotal") == 5300


@pytest.mark.parametrize("name", list(SCENARIOS))
def test_the_onsite_subtotal_adds_hotel_per_diem_for_each_person_day_and_travel_at_3_dollars_an_hour(sheets, name):
    """Qase HU15-FR10"""
    assert value(sheets[name]["bu"]["lines"], ONSITE, "Subtotal") == oracle(SCENARIOS[name])["onsite"]


@pytest.mark.parametrize("name", list(SCENARIOS))
def test_the_reimbursable_subtotal_is_the_sum_of_its_five_fields(sheets, name):
    """Qase HU15-FR11"""
    assert value(sheets[name]["bu"]["lines"], REIMB, "Subtotal") == oracle(SCENARIOS[name])["reimb"]


@pytest.mark.parametrize("name", list(SCENARIOS))
def test_total_cost_is_the_sum_of_the_three_subtotals(sheets, name):
    """Qase HU15-FR12 -- it is the quoted price (Quotation/Revenue column)."""
    lines = sheets[name]["bu"]["lines"]
    total = value(lines, "", "Total Cost")
    assert total == oracle(SCENARIOS[name])["total"]
    assert total == value(lines, LABOR, "Subtotal") + value(lines, ONSITE, "Subtotal") + value(lines, REIMB, "Subtotal")


@pytest.mark.parametrize("name", list(SCENARIOS))
def test_the_footer_total_is_the_total_cost_in_flat_rate(sheets, name):
    """Qase HU15-FR13"""
    assert number(sheets[name]["bu"]["total"]) == oracle(SCENARIOS[name])["total"]


# ================================================================================================ the Expense column in Flat Rate (BU) -- its placeholder is checked by FR21 at the end of the file
def test_the_text_lines_span_both_columns(sheets):
    """Qase HU15-FR15 -- GSP #, Quote#, Available date, Type of Work, Site, City & State and Unit Info are not split into Quotation and Expense."""
    lines = sheets["story_example"]["bu"]["lines"]
    for section, label in TEXT_LINES:
        assert find(lines, section, label).spans_both, f"{label} must span both columns"


# ================================================================================================ number format
@pytest.mark.parametrize("name", ["story_example", "minimal_costs"])
def test_counts_and_hours_have_no_dollar_sign_and_amounts_have_one(sheets, name):
    """Qase HU15-FR16"""
    lines = sheets[name]["bu"]["lines"]
    for section, label in COUNT_AND_HOUR_LINES:
        assert "$" not in find(lines, section, label).quotation, label
    for section, label in AMOUNT_LINES:
        assert find(lines, section, label).quotation.startswith("$"), label


def test_empty_figures_show_zero_and_zero_dollars(sheets):
    """Qase HU15-FR17 -- a quotation with the minimum the server accepts (Labor Cost / Hour 1, since 2026-11-09 it must be greater than 0) and no other cost: the empty amounts show $0 and over hours show 0."""
    lines = sheets["minimal_costs"]["bu"]["lines"]
    assert find(lines, LABOR, "Labor Cost/Hr").quotation == "$1"
    assert find(lines, ONSITE, "Hotel Cost").quotation == "$0"
    assert find(lines, ONSITE, "Subtotal").quotation == "$0"
    assert find(lines, "", "Total Cost").quotation == "$8"
    assert find(lines, SOW, "Total Over Hour/Tech (if any)").quotation == "0"
    assert find(lines, ONSITE, "Travel & Drive Time").quotation == "0"


def test_an_empty_text_field_shows_an_empty_cell(sheets):
    """Qase HU15-FR18 -- Unit Info was never filled in for this quotation."""
    assert find(sheets["minimal_costs"]["bu"]["lines"], SOW, "Unit Info").quotation == ""


# ================================================================================================ the OEM View in Flat Rate
@pytest.mark.parametrize("name", ["story_example", "twelve_hours"])
def test_the_oem_view_has_no_header_row_and_no_expense_column(sheets, name):
    """Qase HU15-FR19"""
    oem = sheets[name]["oem"]
    assert oem["header"] is None, "the OEM sheet has no header row"
    assert all(ln.expense is None for ln in oem["lines"]), "the OEM sheet never shows the Expense column"


@pytest.mark.parametrize("name", list(SCENARIOS))
def test_the_oem_view_shows_the_same_lines_and_figures_as_the_bu_view(sheets, name):
    """Qase HU15-FR20"""
    bu, oem = sheets[name]["bu"]["lines"], sheets[name]["oem"]["lines"]
    assert [(ln.section, ln.label, ln.quotation) for ln in oem] == [(ln.section, ln.label, ln.quotation) for ln in bu]


# ================================================================================================ the placeholder of the Expense column (Qase #149 fixed: the AC now says N/A)
def test_the_expense_placeholder_uses_the_same_language_as_the_rest_of_the_screen(sheets):
    """Qase FR21 -- expected 'N/A' in every figure line of the Expense column."""
    lines = sheets["story_example"]["bu"]["lines"]
    for section, label in EXPECTED_LINES:
        if (section, label) in TEXT_LINES:
            continue
        assert find(lines, section, label).expense == "N/A", f"{label}: {find(lines, section, label).expense!r}"
