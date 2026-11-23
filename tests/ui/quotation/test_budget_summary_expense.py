"""Quotation module -- Budget Summary, Expense visibility by role, Flat Rate (OP-23 / HU-15; Qase suite "HU-15: BU and OEM view of the Budget Summary", cases EX*).

HU-15 'Expense visibility': BU and CEO see the "Expense" column in BU View; for AM and FPM/FSM the column is not displayed at all (not masked) and the Quotation/Revenue
figures stay visible; no role ever sees an Expense column in OEM View. In Flat Rate the BU/CEO Expense column holds a placeholder in every figure line (no estimated cost yet).
The roles open the quotation on their own turn: AM and FPM/FSM on one waiting for the FPM/FSM, BU and CEO on ones waiting for them.
"""
import pytest

from framework_ui.pages.quotation.quotation_page import QuotationPage

pytestmark = pytest.mark.ui

QUOTE_COLUMNS = ["Description", "Quotation/Revenue"]
FIRST_FIGURE_LABEL = "Type of Work"          # GSP #, Quote# and Available date come before it; the first two differ per quotation


@pytest.fixture(scope="module")
def awaiting_fpm(make_quotation):
    return make_quotation("EXP", ["FPM"], title_prefix="HU15")[0]


def _awaiting_next(make_quotation, quotation_api, second):
    qid = make_quotation("EXP", ["FPM", second], title_prefix="HU15")[0]
    assert quotation_api["FPM"].approve(qid, "FPM approves").status_code == 200
    assert quotation_api["AM"].submit(qid).status_code == 200
    return qid


@pytest.fixture(scope="module")
def awaiting_bu(make_quotation, quotation_api):
    return _awaiting_next(make_quotation, quotation_api, "BU")


@pytest.fixture(scope="module")
def awaiting_ceo(make_quotation, quotation_api):
    return _awaiting_next(make_quotation, quotation_api, "CEO")


@pytest.fixture(scope="module")
def sheets(role_page, awaiting_fpm, awaiting_bu, awaiting_ceo):
    """{(role, tab): (header, [(section, label, quotation, expense)...])} -- every role reads the sheet of a quotation that is its turn, in both tabs."""
    quotations = {"AM": awaiting_fpm, "FPM": awaiting_fpm, "BU": awaiting_bu, "CEO": awaiting_ceo}
    out = {}
    for role, qid in quotations.items():
        bs = QuotationPage(role_page(role)).open_by_link(qid).budget_summary().open()
        for tab in ("BU View", "OEM View"):
            bs.select_tab(tab)
            out[(role, tab)] = (bs.header(), [(ln.section, ln.label, ln.quotation, ln.expense) for ln in bs.lines()])
    return out


def figures(lines):
    """The figure lines from Type of Work on, as (section, label, quotation)."""
    labels = [ln[1] for ln in lines]
    return [(s, label, q) for s, label, q, _ in lines[labels.index(FIRST_FIGURE_LABEL):]]


@pytest.mark.parametrize("role", ["BU", "CEO"])
def test_bu_and_ceo_see_the_expense_column_in_bu_view(sheets, role):
    """Qase HU15-EX1 (BU), EX2 (CEO)"""
    header, lines = sheets[(role, "BU View")]
    assert header == QUOTE_COLUMNS + ["Expense"], header
    figure_lines = [ln for ln in lines if ln[3]]
    assert figure_lines, "the Expense column must hold a value in the figure lines"


@pytest.mark.parametrize("role", ["AM", "FPM"])
def test_am_and_fpm_do_not_get_an_expense_column_in_bu_view(sheets, role):
    """Qase HU15-EX3 (AM), EX4 (FPM/FSM) -- the column is not displayed at all (not masked)."""
    header, lines = sheets[(role, "BU View")]
    assert header == QUOTE_COLUMNS, header
    assert all(ln[3] is None for ln in lines), "no line may have an Expense cell"


@pytest.mark.parametrize("role", ["AM", "FPM", "CEO"])
def test_every_role_sees_the_same_quotation_figures_as_the_bu(sheets, role):
    """Qase HU15-EX5 (AM), EX6 (FPM/FSM), EX7 (CEO) -- hiding or showing the Expense column never changes the Quotation/Revenue figures."""
    assert figures(sheets[(role, "BU View")][1]) == figures(sheets[("BU", "BU View")][1])


@pytest.mark.parametrize("role", ["AM", "FPM", "BU", "CEO"])
def test_no_role_ever_sees_an_expense_column_in_oem_view(sheets, role):
    """Qase HU15-EX8 (AM), EX9 (FPM/FSM), EX10 (BU), EX11 (CEO)"""
    header, lines = sheets[(role, "OEM View")]
    assert header is None, "OEM View has no header row"
    assert all(ln[3] is None for ln in lines), "OEM View must have no Expense cell"


def test_the_ceo_expense_column_matches_the_bu_expense_column(sheets):
    """Qase HU15-EX12 -- same Expense cells, line by line, for the CEO and the BU (Flat Rate placeholders)."""
    assert [ln[3] for ln in figures_with_expense(sheets[("CEO", "BU View")][1])] == [ln[3] for ln in figures_with_expense(sheets[("BU", "BU View")][1])]


def figures_with_expense(lines):
    labels = [ln[1] for ln in lines]
    return lines[labels.index(FIRST_FIGURE_LABEL):]
