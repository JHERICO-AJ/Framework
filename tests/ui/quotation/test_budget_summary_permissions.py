"""Quotation module -- Budget Summary, roles and permissions (OP-23 / HU-15; Qase suite "HU-15: BU and OEM view of the Budget Summary", cases PR*).

Observed on the QA build of 2026-10-23: the Budget Summary button is in the footer for every role that can open a quotation (AM, FPM/FSM, BU, CEO and the
approvers the system assigns by amount); the panel opens for all of them. The form itself is editable only for the AM while the quotation is a Draft, Returned or
Rejected; whoever is the approver sees the amounts read-only. (Who edits the Diagnosis is covered by HU-22 cases 1214-1216, and the server's refusals by
tests/api/quotation/test_budget_summary_permissions_api.py.)

Amounts that make the system add a default approver: about $150,000 adds the default BU, about $600,000 the default CEO. With no approver chosen the default FPM/FSM gets it.
"""
import pytest

from framework_ui.pages.quotation.quotation_page import QuotationPage

pytestmark = pytest.mark.ui

LABOR = ("Labor Costs", "Labor Cost / Hour")
LABOR_FOR_BU_RANGE = 4474       # total about $149,978 -> the default BU is added on Submit
LABOR_FOR_CEO_RANGE = 18537     # total about $599,994 -> the default CEO is added on Submit


@pytest.fixture(scope="module")
def draft(make_draft):
    return make_draft("PERM")[0]


@pytest.fixture(scope="module")
def awaiting_fpm(make_quotation):
    return make_quotation("PERM", ["FPM"], title_prefix="HU15")[0]


@pytest.fixture(scope="module")
def returned(make_quotation, quotation_api):
    qid = make_quotation("PERM", ["FPM"], title_prefix="HU15")[0]
    assert quotation_api["FPM"].approve(qid, "FPM approves").status_code == 200
    return qid


@pytest.fixture(scope="module")
def rejected(make_quotation, quotation_api):
    qid = make_quotation("PERM", ["FPM"], title_prefix="HU15")[0]
    assert quotation_api["FPM"].reject(qid, "FPM rejects").status_code == 200
    return qid


def _awaiting(make_quotation, quotation_api, route_with_fpm, arrangement=None):
    """FPM/FSM approves, the AM sends it on: now it waits for the next signer."""
    qid = make_quotation("PERM", route_with_fpm, arrangement=arrangement, title_prefix="HU15")[0]
    assert quotation_api["FPM"].approve(qid, "FPM approves").status_code == 200
    assert quotation_api["AM"].submit(qid).status_code == 200
    return qid


@pytest.fixture(scope="module")
def awaiting_bu(make_quotation, quotation_api):
    return _awaiting(make_quotation, quotation_api, ["FPM", "BU"])


@pytest.fixture(scope="module")
def awaiting_ceo(make_quotation, quotation_api):
    return _awaiting(make_quotation, quotation_api, ["FPM", "CEO"])


@pytest.fixture(scope="module")
def returned_for_bu(awaiting_bu):
    return awaiting_bu          # waiting for the BU after the AM sent it on


@pytest.fixture(scope="module")
def default_fpm(make_quotation):
    return make_quotation("PERM", [], title_prefix="HU15")[0]


@pytest.fixture(scope="module")
def default_bu(make_quotation, quotation_api):
    return _awaiting(make_quotation, quotation_api, ["FPM"], {"laborCostHour": LABOR_FOR_BU_RANGE})


@pytest.fixture(scope="module")
def default_ceo(make_quotation, quotation_api):
    return _awaiting(make_quotation, quotation_api, ["FPM"], {"laborCostHour": LABOR_FOR_CEO_RANGE})


def open_as(role_page, role, quotation_id):
    return QuotationPage(role_page(role)).open_by_link(quotation_id)


def assert_panel_opens(qp):
    bs = qp.budget_summary()
    assert bs.has_button(), "the Budget Summary button must be in the footer"
    bs.open()
    assert bs.is_open() and bs.lines(), "the panel must open and show the figures"


# ================================================================================================ the button, per role
@pytest.mark.parametrize("state", ["draft", "awaiting_fpm", "returned", "rejected"])
def test_the_am_sees_the_button_and_opens_the_panel_in_every_state(role_page, request, state):
    """Qase HU15-PR1 (Draft), PR2 (waiting for the FPM/FSM), PR3 (Returned), PR4 (Rejected)"""
    assert_panel_opens(open_as(role_page, "AM", request.getfixturevalue(state)))


@pytest.mark.parametrize("role, state", [("FPM", "awaiting_fpm"), ("BU", "awaiting_bu"), ("CEO", "awaiting_ceo")])
def test_the_approvers_see_the_button_and_open_the_panel_on_their_turn(role_page, request, role, state):
    """Qase HU15-PR5 (FPM/FSM), PR6 (BU), PR7 (CEO)"""
    assert_panel_opens(open_as(role_page, role, request.getfixturevalue(state)))


@pytest.mark.parametrize("role, state", [("DEFAULT_FPM", "default_fpm"), ("DEFAULT_BU", "default_bu"), ("DEFAULT_CEO", "default_ceo")])
def test_the_approvers_the_system_assigns_see_the_button_and_open_the_panel(role_page, request, role, state):
    """Qase HU15-PR8 (default FPM/FSM), PR9 (default BU), PR10 (default CEO)"""
    assert_panel_opens(open_as(role_page, role, request.getfixturevalue(state)))


def test_a_user_without_a_quotation_role_cannot_open_a_quotation_or_see_the_button(role_page, draft):
    """Qase HU15-PR11 -- needs QUOTATION_NOROLE_EMAIL / QUOTATION_NOROLE_PASSWORD in .env (skipped until the account exists).
    Observed 2026-10-23: the screen only says that no Quotation role is assigned; opening a quotation by its link shows the same message and no form."""
    from shared.config.settings import BASE_URL
    page = role_page("NOROLE")
    page.goto(f"{BASE_URL}/quotation/{draft}", timeout=60000)
    page.get_by_text("No Quotation role is assigned to your account.", exact=False).wait_for(timeout=30000)
    assert page.get_by_text("Quotation access requires an AM, FPM/FSM, BU, or CEO role assignment.", exact=False).count() == 1
    assert page.get_by_text("WO Snapshot", exact=True).count() == 0, "the form must not open"
    assert not QuotationPage(page).budget_summary().has_button()


# ================================================================================================ who edits what, by state
@pytest.mark.parametrize("state", ["draft", "returned", "rejected"])
def test_the_am_can_edit_the_amounts_of_a_draft_returned_or_rejected_quotation(role_page, request, state):
    """Qase HU15-PR12 (Draft), PR13 (Returned), PR14 (Rejected)"""
    qp = open_as(role_page, "AM", request.getfixturevalue(state))
    assert qp.wo_snapshot().field("OEM Name").is_editable()
    assert qp.fse_arrangement().field(*LABOR).is_editable()


def test_the_am_sees_a_quotation_waiting_for_an_approver_read_only(role_page, awaiting_fpm):
    """Qase HU15-PR15"""
    qp = open_as(role_page, "AM", awaiting_fpm)
    assert not qp.wo_snapshot().field("OEM Name").is_editable()
    assert not qp.fse_arrangement().field(*LABOR).is_editable()


@pytest.mark.parametrize("role, state", [("FPM", "awaiting_fpm"), ("BU", "awaiting_bu"), ("CEO", "awaiting_ceo")])
def test_an_approver_cannot_edit_the_amounts_on_their_turn(role_page, request, role, state):
    """Qase HU15-PR16 (FPM/FSM), PR17 (BU), PR18 (CEO)"""
    qp = open_as(role_page, role, request.getfixturevalue(state))
    assert not qp.wo_snapshot().field("OEM Name").is_editable()
    assert not qp.fse_arrangement().field(*LABOR).is_editable()


def test_opening_the_panel_does_not_make_anything_editable_for_an_approver(role_page, awaiting_bu):
    """Qase HU15-PR19"""
    qp = open_as(role_page, "BU", awaiting_bu)
    bs = qp.budget_summary().open()
    assert bs.input_count() == 0
    assert not qp.fse_arrangement().field(*LABOR).is_editable()


# ================================================================================================ read-only panel for everyone, and approvers out of turn
@pytest.mark.parametrize("role, state", [("AM", "draft"), ("AM", "awaiting_fpm"), ("FPM", "awaiting_fpm"), ("CEO", "awaiting_ceo"),
                                         ("DEFAULT_FPM", "default_fpm"), ("DEFAULT_BU", "default_bu"), ("DEFAULT_CEO", "default_ceo")])
def test_the_panel_has_nothing_to_edit_for_any_role(role_page, request, role, state):
    """Qase HU15-PR20 (AM Draft), PR21 (AM waiting), PR22 (FPM/FSM), PR23 (CEO), PR24 (default FPM/FSM), PR25 (default BU), PR26 (default CEO)"""
    qp = open_as(role_page, role, request.getfixturevalue(state))
    bs = qp.budget_summary().open()
    assert bs.input_count() == 0, "the Budget Summary panel must have no inputs, text areas or selects"


@pytest.mark.parametrize("state", ["returned", "rejected"])
def test_the_fpm_cannot_edit_anything_after_their_decision(role_page, request, state):
    """Qase HU15-PR27 (Returned), PR28 (Rejected) -- the quotation went back to the AM, so the FPM/FSM who decided sees the amounts and the Diagnosis read-only."""
    qp = open_as(role_page, "FPM", request.getfixturevalue(state))
    assert not qp.wo_snapshot().field("OEM Name").is_editable()
    assert not qp.fse_arrangement().field(*LABOR).is_editable()
    for label in ("SIGNAL", "TRIGGER", "CAUSE", "NOTES"):
        assert not qp.diagnosis_field(label).is_editable(), f"{label} must be read-only once the quotation is back with the AM"


# ================================================================================================ criteria 2 and 4 of the story, read literally
@pytest.mark.parametrize("role, state, has_expense", [("DEFAULT_BU", "default_bu", True), ("DEFAULT_CEO", "default_ceo", True), ("DEFAULT_FPM", "default_fpm", False)])
def test_a_default_approver_sees_the_same_sheet_as_any_user_with_their_role(role_page, request, role, state, has_expense):
    """Qase HU15-PR29 (default BU sees Expense), PR30 (default CEO sees Expense), PR31 (default FPM/FSM does not)"""
    bs = open_as(role_page, role, request.getfixturevalue(state)).budget_summary().open()
    assert ("Expense" in bs.header()) is has_expense, bs.header()


@pytest.mark.parametrize("state", ["awaiting_fpm", "returned_for_bu"])
def test_the_form_has_no_save_or_submit_button_for_the_am_while_it_is_not_editable(role_page, request, state):
    """Qase HU15-PR32 -- 'in any other status the form must be read-only' and, per the developer, 'Save isn't shown'."""
    page = open_as(role_page, "AM", request.getfixturevalue(state)).page
    assert page.get_by_role("button", name="Save Draft").count() == 0
    assert page.get_by_role("button", name="Submit Quotation").count() == 0
