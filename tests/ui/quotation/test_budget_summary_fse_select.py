"""Quotation module -- Budget Summary of an FSE Select (Variable Rate) quotation and the Expense figures by role (OP-23 / HU-15; Qase suite "HU-15: BU and OEM view of the Budget Summary", cases FS* and EX13+).

HU-15 'Figures: FSE Select quotation': one block per selected engineer, in selection order (Service Fee "$100 x 8 h = $800", Overwork Service, Equipment, Travel Expenses, Miscellaneous, Total),
a "Final Total" row, the figures confirmed in the Budget Calculator (Quotation (Income) tab; the Expense tab only in the Expense column of BU and CEO), BU View with each engineer's name and OEM View with
"Engineer 1", "Engineer 2"... and only the Quotation column, an engineer whose calculator was not confirmed at $0, "No engineers selected yet - pick them with MAP in FSE Select." with no engineers,
and a footer Total that is the Final Total ("—" while no selected engineer has calculator figures).

The quotations are created through the API with the figures the screen sends when the Budget Calculator is confirmed (framework_api/services/quotation_setup.py: three_engineers()). Engineers are looked up by
name because the order of the blocks is its own check (FS1). Every role opens a quotation it signs (an approver gets HTTP 403 on any other since the QA build of 2026-10-23).
"""
import re

import pytest

from framework_api.services import quotation_setup as qs
from framework_ui.pages.quotation.components.budget_summary import number
from framework_ui.pages.quotation.quotation_page import QuotationPage

pytestmark = pytest.mark.ui

LINES = ["Service Fee", "Overwork Service", "Equipment", "Travel Expenses", "MISCELLANEOUS", "Total"]
SELECTION_ORDER = ["Pedro Aguilar", "Employee L01200", "Anna Lindqvist"]

# (rate, hours, service) / (ot rate, ot hours, ot service) / equipment / travel / misc / total -- per engineer and per calculator tab (what qs.three_engineers() sends)
EXPECTED = {
    "quotation": {"Pedro Aguilar": ((110, 24, 2640), (165, 4, 660), 250, 615, 60, 4225), "Employee L01200": ((110, 24, 2640), (0, 0, 0), 180, 880, 0, 3700),
                  "Anna Lindqvist": ((67, 40, 2680), (0, 0, 0), 100, 500, 20, 3300)},
    "expense": {"Pedro Aguilar": ((55, 24, 1320), (83, 4, 332), 0, 615, 0, 2267), "Employee L01200": ((50, 24, 1200), (0, 0, 0), 0, 880, 0, 2080),
                "Anna Lindqvist": ((30, 40, 1200), (0, 0, 0), 0, 420, 0, 1620)},
}
FINAL = {"quotation": 11225, "expense": 5967}
PLANNED = {"plannedCheckIn": "2026-10-19T15:09:00", "plannedCheckOut": "2026-10-22T15:09:00"}


def with_select(extra, **select):
    return {**extra, "select": {**extra["select"], **select}}


def fee(text):
    """'$110 × 24 h = $2640' -> (110, 24, 2640)"""
    m = re.fullmatch(r"\$([\d.,]+) × ([\d.,]+) h = \$([\d.,]+)", text.strip())
    assert m, f"not a 'rate × hours = total' line: {text!r}"
    return tuple(number(g) for g in m.groups())


def figures(block, column):
    """The six lines of a block as (service fee, overwork, equipment, travel, misc, total) numbers; column 0 = Quotation, 1 = Expense."""
    lines = block["lines"]
    cell = lambda label: lines[label][column]
    return (fee(cell("Service Fee")), fee(cell("Overwork Service")), number(cell("Equipment")), number(cell("Travel Expenses")), number(cell("MISCELLANEOUS")), number(cell("Total")))


@pytest.fixture(scope="module")
def three():
    return with_select(qs.three_engineers(), **PLANNED)


@pytest.fixture(scope="module")
def quotes(make_draft, make_quotation, make_waiting_for_bu, three):
    return {"AM": make_draft("FS", extra=three)[0], "FPM": make_quotation("FS", ["FPM"], title_prefix="HU15", extra=three)[0],
            "BU": make_waiting_for_bu("FS", extra=three)[0], "CEO": make_waiting_for_bu("FS", extra=three, route=("FPM", "CEO"))[0]}


@pytest.fixture(scope="module")
def sheets(role_page, quotes):
    """{(role, tab): select_sheet()} plus {(role, 'footer'): text} and {(role, 'cards'): {...}}, each role reading a quotation it signs."""
    out = {}
    for role, qid in quotes.items():
        bs = QuotationPage(role_page(role)).open_by_link(qid).budget_summary()
        out[(role, "footer")] = bs.footer_total()
        bs.open()
        out[(role, "cards")] = bs.cards()
        for tab in ("BU View", "OEM View"):
            bs.select_tab(tab)
            out[(role, tab)] = bs.select_sheet()
    return out


def by_name(sheet):
    return {b["name"]: b for b in sheet["blocks"]}


# ================================================================================================ the sheet
def test_the_sheet_has_one_block_per_engineer_with_the_lines_of_the_story(sheets):
    """Qase HU15-FS1 -- BU View shows each engineer's name."""
    blocks = sheets[("AM", "BU View")]["blocks"]
    assert sorted(b["name"] for b in blocks) == sorted(SELECTION_ORDER)
    for b in blocks:
        assert list(b["lines"]) == LINES, b


def test_the_blocks_follow_the_selection_order(make_draft, role_page, three):
    """Qase HU15-FS2 -- 'one block per selected engineer, in selection order' (six identical quotations: by chance all of them in order has a 1 in 64 probability)."""
    page = role_page("AM")
    for i in range(6):
        qid = make_draft(f"ORDER{i}", extra=three)[0]
        names = [b["name"] for b in QuotationPage(page).open_by_link(qid).budget_summary().open().select_sheet()["blocks"]]
        assert names == SELECTION_ORDER, f"quotation {i + 1}: {names}"


@pytest.mark.parametrize("role", ["AM", "FPM", "BU", "CEO"])
def test_each_block_shows_the_figures_of_the_quotation_income_tab(sheets, role):
    """Qase HU15-FS3 (AM), FS4 (FPM/FSM), FS5 (BU), FS6 (CEO) -- Service Fee and Overwork Service as 'rate × hours = total', and the Total of each engineer."""
    blocks = by_name(sheets[(role, "BU View")])
    for name, expected in EXPECTED["quotation"].items():
        assert figures(blocks[name], 0) == expected, name


@pytest.mark.parametrize("role", ["AM", "BU"])
def test_the_final_total_adds_up_the_total_of_every_engineer(sheets, role):
    """Qase HU15-FS7 (AM), FS8 (BU)"""
    sheet = sheets[(role, "BU View")]
    assert number(sheet["final"][0]) == FINAL["quotation"] == sum(number(b["lines"]["Total"][0]) for b in sheet["blocks"])


@pytest.mark.parametrize("role", ["AM", "FPM", "BU", "CEO"])
def test_the_footer_total_is_the_final_total(sheets, role):
    """Qase HU15-FS9 (AM), FS10 (FPM/FSM), FS11 (BU), FS12 (CEO)"""
    assert number(sheets[(role, "footer")]) == FINAL["quotation"]


@pytest.mark.parametrize("role", ["AM", "FPM", "BU", "CEO"])
def test_the_oem_view_has_only_the_quotation_column_and_numbered_engineers(sheets, role):
    """Qase HU15-FS13 (AM), FS14 (FPM/FSM), FS15 (BU), FS16 (CEO) -- 'Engineer 1', 'Engineer 2'..., never the real names, and no Expense column for any role."""
    sheet = sheets[(role, "OEM View")]
    assert sheet["header"] == ["", "", "Quotation"] and not sheet["has_expense"]
    assert [b["name"] for b in sheet["blocks"]] == ["Engineer 1", "Engineer 2", "Engineer 3"]
    assert all(v[1] is None for b in sheet["blocks"] for v in b["lines"].values())


def test_the_oem_view_shows_the_same_figures_as_the_bu_view(sheets):
    """Qase HU15-FS17 -- same quotation figures, block by block."""
    bu, oem = sheets[("AM", "BU View")], sheets[("AM", "OEM View")]
    assert [figures(b, 0) for b in bu["blocks"]] == [figures(b, 0) for b in oem["blocks"]]
    assert bu["final"] == oem["final"]


def test_the_cards_show_the_planned_check_in_and_check_out_with_the_time_and_the_engineers(sheets):
    """Qase HU15-FS18 -- FSE Select: the dates are MM/dd/yyyy h:mm AM/PM."""
    cards = sheets[("AM", "cards")]
    assert cards["EST. START TIME"] == "10/19/2026 3:09 PM" and cards["EST. END TIME"] == "10/22/2026 3:09 PM" and cards["SUPPORT ENGINEERS"] == "3"


# ================================================================================================ Expense by role
@pytest.mark.parametrize("role", ["BU", "CEO"])
def test_bu_and_ceo_see_the_expense_tab_figures_of_each_engineer(sheets, role):
    """Qase HU15-EX13 (BU), EX14 (CEO) -- the Expense column of BU View holds the Expense tab of the Budget Calculator, with the same line format."""
    sheet = sheets[(role, "BU View")]
    assert sheet["header"] == ["", "", "Quotation", "Expense"] and sheet["has_expense"]
    blocks = by_name(sheet)
    for name, expected in EXPECTED["expense"].items():
        assert figures(blocks[name], 1) == expected, name
    assert number(sheet["final"][1]) == FINAL["expense"]


@pytest.mark.parametrize("role", ["AM", "FPM"])
def test_am_and_fpm_do_not_get_an_expense_column_in_fse_select(sheets, role):
    """Qase HU15-EX15 (AM), EX16 (FPM/FSM) -- not displayed at all, and the Quotation figures stay."""
    sheet = sheets[(role, "BU View")]
    assert sheet["header"] == ["", "", "Quotation"] and not sheet["has_expense"]
    assert all(v[1] is None for b in sheet["blocks"] for v in b["lines"].values()) and sheet["final"][1] is None


@pytest.mark.parametrize("role", ["FPM", "BU", "CEO"])
def test_every_role_sees_the_same_quotation_figures_as_the_am(sheets, role):
    """Qase HU15-EX17 (FPM/FSM), EX18 (BU), EX19 (CEO)"""
    reference = {n: figures(b, 0) for n, b in by_name(sheets[("AM", "BU View")]).items()}
    assert {n: figures(b, 0) for n, b in by_name(sheets[(role, "BU View")]).items()} == reference


# ================================================================================================ the Budget Calculator
def open_calculator(page):
    page.get_by_role("button", name=re.compile("^Calculate$", re.I)).click()
    modal = page.locator("div.fixed.inset-0").last
    modal.get_by_text(re.compile(r"^budget calculator$", re.I)).wait_for(timeout=15000)   # the DOM text is mixed case, CSS shows capitals
    return modal


def calculator_tabs(modal):
    return modal.evaluate("m => Array.from(m.querySelectorAll('button')).map(b => b.innerText.trim()).filter(t => /Quotation|Expense|Income/i.test(t))")


@pytest.mark.skip(reason="NOT APPLICABLE FOR NOW (2026-11-12): the developer removed the Expense tab of the Budget Calculator (Jira OP-131 / Qase #160: 'The expense fields have been removed for now'). The stories HU-15 AC11 and HU-12 AC7 still ask for it: this test comes back when the tab does.")
def test_the_am_can_enter_the_expense_figures_in_the_calculator_of_a_draft(role_page, quotes):
    """Qase HU15-EX20"""
    page = QuotationPage(role_page("AM")).open_by_link(quotes["AM"]).page
    modal = open_calculator(page)
    tabs = calculator_tabs(modal)
    assert any(t.lower().startswith("expense") for t in tabs), f"tabs shown: {tabs}"


@pytest.mark.skip(reason="NOT APPLICABLE FOR NOW (2026-11-12): the developer removed the Expense tab of the Budget Calculator (Jira OP-131 / Qase #160: 'The expense fields have been removed for now'). The stories HU-15 AC11 and HU-12 AC7 still ask for it: this test comes back when the tab does.")
@pytest.mark.parametrize("role", ["FPM", "BU", "CEO"])
def test_the_approvers_see_the_expense_tab_of_the_calculator(role_page, quotes, role):
    """Qase HU15-EX21 (FPM/FSM), EX22 (BU), EX23 (CEO)"""
    page = QuotationPage(role_page(role)).open_by_link(quotes[role]).page
    tabs = calculator_tabs(open_calculator(page))
    assert any(t.lower().startswith("expense") for t in tabs), f"tabs shown: {tabs}"


@pytest.mark.parametrize("role", ["FPM", "BU", "CEO"])
def test_the_approvers_open_the_calculator_read_only(role_page, quotes, role):
    """Qase HU15-EX24 (FPM/FSM), EX25 (BU), EX26 (CEO) -- every value is read-only; the add-item buttons and Confirm are disabled (only the engineer selector, which changes what is shown, stays active)."""
    page = QuotationPage(role_page(role)).open_by_link(quotes[role]).page
    modal = open_calculator(page)
    editable = modal.evaluate("m => Array.from(m.querySelectorAll('input,textarea,select')).filter(e => !e.disabled && !e.readOnly).map(e => e.tagName)")
    assert editable == ["SELECT"], editable
    disabled = modal.evaluate("m => Array.from(m.querySelectorAll('button')).filter(b => b.disabled).map(b => b.innerText.trim())")
    assert disabled.count("+") == 2 and "Confirm" in disabled, disabled


def test_the_am_can_edit_the_calculator_of_a_draft(role_page, quotes):
    """Qase HU15-EX27"""
    page = QuotationPage(role_page("AM")).open_by_link(quotes["AM"]).page
    modal = open_calculator(page)
    assert modal.evaluate("m => Array.from(m.querySelectorAll('input[type=number]')).filter(e => !e.disabled && !e.readOnly).length") >= 16
    assert modal.get_by_role("button", name="Confirm", exact=True).is_enabled()


# ================================================================================================ states without figures
@pytest.fixture(scope="module")
def empty_cases(make_draft):
    one = qs.select_extra(("Pedro Aguilar", None, None))
    mixed = qs.select_extra(("Pedro Aguilar", qs.engineer_cost("quotation", 110, 24, 165, 4, 615, 250, 60), None), ("Employee L01200", None, None))
    return {"none": make_draft("NONE", extra=qs.select_extra())[0], "unconfirmed": make_draft("UNCONF", extra=one)[0], "mixed": make_draft("MIXED", extra=mixed)[0]}


def read(role_page, qid):
    bs = QuotationPage(role_page("AM")).open_by_link(qid).budget_summary()
    footer = bs.footer_total()
    bs.button().first.click()
    bs.page.wait_for_timeout(1200)
    return bs, footer


def test_with_no_engineers_the_sheet_says_so_and_the_footer_total_is_a_dash(role_page, empty_cases):
    """Qase HU15-FS19"""
    bs, footer = read(role_page, empty_cases["none"])
    assert bs.empty_sheet_message() == "No engineers selected yet - pick them with MAP in FSE Select."
    assert bs.page.locator("table.table-fixed").count() == 0 and footer == "—"


def test_an_engineer_whose_calculator_was_not_confirmed_shows_every_figure_as_zero(role_page, empty_cases):
    """Qase HU15-FS20 -- and the footer Total stays a dash while no selected engineer has calculator figures."""
    bs, footer = read(role_page, empty_cases["unconfirmed"])
    sheet = bs.select_sheet()
    assert footer == "—"
    block = sheet["blocks"][0]
    assert figures(block, 0) == ((0, 0, 0), (0, 0, 0), 0, 0, 0, 0) and number(sheet["final"][0]) == 0


def test_with_one_confirmed_engineer_the_other_shows_zero_and_the_total_is_the_confirmed_one(role_page, empty_cases):
    """Qase HU15-FS21"""
    bs, footer = read(role_page, empty_cases["mixed"])
    blocks = by_name(bs.select_sheet())
    assert figures(blocks["Pedro Aguilar"], 0)[-1] == 4225 and figures(blocks["Employee L01200"], 0) == ((0, 0, 0), (0, 0, 0), 0, 0, 0, 0)
    assert number(footer) == 4225


def test_an_empty_date_shows_a_dash_in_the_cards_of_an_fse_select_quotation(make_draft, role_page):
    """Qase HU15-FS22 -- 'An empty date must show a dash': a quotation with engineers but no planned check-in or check-out."""
    qid = make_draft("NODATES", extra=qs.three_engineers())[0]
    bs = QuotationPage(role_page("AM")).open_by_link(qid).budget_summary().open()
    cards = bs.cards()
    assert cards["EST. START TIME"] == "—" and cards["EST. END TIME"] == "—" and cards["SUPPORT ENGINEERS"] == "3", cards


def test_the_cards_of_an_fse_select_quotation_change_with_the_form_without_reloading(make_draft, role_page, three):
    """Qase HU15-FS23 -- 'When a card value changes in the form, the card must show the new value without a page reload': Support Engineers typed in Engineer Selection while
    the panel is open, and again after closing and reopening it."""
    qid = make_draft("CARDLIVE", extra=three)[0]
    qp = QuotationPage(role_page("AM")).open_by_link(qid)
    bs = qp.budget_summary().open()
    assert bs.cards()["SUPPORT ENGINEERS"] == "3"
    field = qp.engineer_selection().field("Support Engineers")      # typed with fill(): a click on the + button would count as a click outside the footer and hide the panel
    field.fill("4")
    qp.page.wait_for_timeout(600)
    assert bs.is_open() and bs.cards()["SUPPORT ENGINEERS"] == "4"
    bs.close_with_button()
    field.fill("3")
    qp.page.wait_for_timeout(400)
    assert bs.open().cards()["SUPPORT ENGINEERS"] == "3"
