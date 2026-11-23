"""Quotation module -- who can change a quotation, on the server (OP-23 / HU-15; Qase suite "HU-15: BU and OEM view of the Budget Summary", cases PR-API*).

Observed on the QA build of 2026-10-23, PUT /api/quotations/{id} (the call Save Draft makes on an existing quotation):
  - the AM can update a Draft, a Returned or a Rejected quotation (200) and not one that is Awaiting an approver (400 QUOTATION_NOT_EDITABLE);
  - FPM/FSM, BU and CEO never update a quotation through this call, not even when it is their turn (403 QUOTATION_FORBIDDEN);
  - no login at all -> 401.
The Diagnosis rule ("Only the Level 1 (FPM/FSM) approver can edit the Diagnosis") is already covered by HU-22 cases API5 and API6.
Also observed 2026-10-23: every role that can open a quotation receives the Expense figures of each engineer (GET returns the 'expense' and the 'quotation' set), only the AM can upload an
attachment (the others get 403 QUOTATION_FORBIDDEN), and a FPM/FSM, BU or CEO approval that carries extra fields answers 200 and ignores them: the criterion says such a change 'must be rejected',
so PR-API17 to PR-API19 are strict xfails (open defect).
"""
import io

import pytest

from framework_api.client.role_session import anonymous_post  # noqa: F401  (kept for symmetry with the other API modules)
from framework_api.services import quotation_setup as qs
from framework_api.services.quotation_service import QuotationService

pytestmark = pytest.mark.api

NOT_EDITABLE_TEXT = "Only Draft, Returned or Rejected quotations can be updated. Awaiting and finalized quotes are workflow-owned."   # exact text of the HU-15 criterion
FORBIDDEN_TEXT = "Not authorized for this Quotation action."


def get_body(quotation_api, quotation_id):
    r = quotation_api["AM"].client.get(f"{QuotationService.PATH}/{quotation_id}")
    assert r.status_code == 200, f"{r.status_code} {r.text[:200]}"
    return r.json()


def put(session, quotation_id, body):
    return session.session.put(f"{session.base_url}{QuotationService.PATH}/{quotation_id}", json=body, timeout=session.timeout)


def code(r):
    return (r.json().get("details") or {}).get("code")


@pytest.fixture(scope="module")
def draft(make_draft):
    return make_draft("PERM-API")[0]


@pytest.fixture(scope="module")
def awaiting_fpm(make_quotation):
    return make_quotation("PERM-API", ["FPM"], title_prefix="HU15")[0]


@pytest.fixture(scope="module")
def awaiting_bu(make_quotation, quotation_api):
    qid = make_quotation("PERM-API", ["FPM", "BU"], title_prefix="HU15")[0]
    assert quotation_api["FPM"].approve(qid, "FPM approves").status_code == 200       # the FPM/FSM decision returns it to the AM ...
    assert quotation_api["AM"].submit(qid).status_code == 200                           # ... who sends it on to the BU
    return qid


@pytest.fixture(scope="module")
def rejected(make_quotation, quotation_api):
    qid = make_quotation("PERM-API", ["FPM"], title_prefix="HU15")[0]
    assert quotation_api["FPM"].reject(qid, "FPM rejects").status_code == 200
    return qid


@pytest.fixture(scope="module")
def returned(make_quotation, quotation_api):
    qid = make_quotation("PERM-API", ["FPM"], title_prefix="HU15")[0]
    assert quotation_api["FPM"].approve(qid, "FPM approves").status_code == 200
    return qid


# ================================================================================================ the AM
@pytest.mark.parametrize("state", ["draft", "rejected", "returned"])
def test_the_am_can_update_a_draft_returned_or_rejected_quotation(api_roles, quotation_api, request, state):
    """Qase HU15-PR-API1 (Draft), PR-API2 (Rejected), PR-API3 (Returned)"""
    qid = request.getfixturevalue(state)
    body = get_body(quotation_api, qid)
    r = put(api_roles["AM"], qid, body)
    assert r.status_code == 200, f"{state}: {r.status_code} {r.text[:200]}"


@pytest.mark.parametrize("state", ["awaiting_fpm", "awaiting_bu"])
def test_the_am_cannot_update_a_quotation_that_is_awaiting_an_approver(api_roles, quotation_api, request, state):
    """Qase HU15-PR-API4 (waiting for the FPM/FSM), PR-API5 (waiting for the BU)"""
    qid = request.getfixturevalue(state)
    r = put(api_roles["AM"], qid, get_body(quotation_api, qid))
    assert r.status_code == 400 and code(r) == "QUOTATION_NOT_EDITABLE", f"{r.status_code} {r.text[:200]}"
    assert r.json()["message"] == NOT_EDITABLE_TEXT, r.json()["message"]


# ================================================================================================ everyone else
@pytest.mark.parametrize("role", ["FPM", "BU", "CEO"])
def test_the_approver_roles_cannot_update_a_draft(api_roles, quotation_api, draft, role):
    """Qase HU15-PR-API6 (FPM/FSM), PR-API7 (BU), PR-API8 (CEO)"""
    r = put(api_roles[role], draft, get_body(quotation_api, draft))
    assert r.status_code == 403 and code(r) == "QUOTATION_FORBIDDEN", f"{r.status_code} {r.text[:200]}"
    assert r.json()["message"] == FORBIDDEN_TEXT


def test_the_fpm_cannot_update_the_quotation_even_when_it_is_their_turn(api_roles, quotation_api, awaiting_fpm):
    """Qase HU15-PR-API9"""
    r = put(api_roles["FPM"], awaiting_fpm, get_body(quotation_api, awaiting_fpm))
    assert r.status_code == 403 and code(r) == "QUOTATION_FORBIDDEN", f"{r.status_code} {r.text[:200]}"


def test_the_bu_cannot_update_the_quotation_even_when_it_is_their_turn(api_roles, quotation_api, awaiting_bu):
    """Qase HU15-PR-API10"""
    r = put(api_roles["BU"], awaiting_bu, get_body(quotation_api, awaiting_bu))
    assert r.status_code == 403 and code(r) == "QUOTATION_FORBIDDEN", f"{r.status_code} {r.text[:200]}"


def test_an_update_with_no_login_is_refused(draft, quotation_api):
    """Qase HU15-PR-API11"""
    import requests
    from shared.config.settings import BASE_URL
    r = requests.put(f"{BASE_URL.rstrip('/')}{QuotationService.PATH}/{draft}", json=get_body(quotation_api, draft), timeout=30)
    assert r.status_code == 401, f"{r.status_code} {r.text[:200]}"


# ================================================================================================ the Expense figures reach every role (the column is only hidden on screen)
EXPENSE_TOTALS = {"Pedro Aguilar": 2267, "Employee L01200": 2080, "Anna Lindqvist": 1620}
QUOTATION_TOTALS = {"Pedro Aguilar": 4225, "Employee L01200": 3700, "Anna Lindqvist": 3300}


@pytest.fixture(scope="module")
def select_quotes(make_draft, make_quotation, make_waiting_for_bu):
    three = qs.three_engineers()
    return {"AM": make_draft("EXPAPI", extra=three)[0], "FPM": make_quotation("EXPAPI", ["FPM"], title_prefix="HU15", extra=three)[0],
            "BU": make_waiting_for_bu("EXPAPI", extra=three)[0], "CEO": make_waiting_for_bu("EXPAPI", extra=three, route=("FPM", "CEO"))[0]}


@pytest.mark.parametrize("role", ["AM", "FPM", "BU", "CEO"])
def test_every_role_receives_the_expense_figures_of_each_engineer(quotation_api, select_quotes, role):
    """Qase HU15-EX-API1 (AM), EX-API2 (FPM/FSM), EX-API3 (BU), EX-API4 (CEO) -- 'Hiding the column must be a display rule only, not a data restriction'."""
    body = get_body_as(quotation_api, role, select_quotes[role])
    sets = {e["contractorName"]: {c["tab"]: c["personalTotal"] for c in e["costs"]} for e in body["select"]["selectedEngineers"]}
    assert {n: v["expense"] for n, v in sets.items()} == EXPENSE_TOTALS, sets
    assert {n: v["quotation"] for n, v in sets.items()} == QUOTATION_TOTALS, sets


def get_body_as(quotation_api, role, quotation_id):
    r = quotation_api[role].client.get(f"{QuotationService.PATH}/{quotation_id}")
    assert r.status_code == 200, f"{r.status_code} {r.text[:200]}"
    return r.json()


# ================================================================================================ attachments: only the AM (the AM side is shown by the screen case FE8, so no file is uploaded here)
PDF = b"%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\ntrailer<</Root 1 0 R>>\n%%EOF"


def upload(session):
    return session.session.post(session.base_url + QuotationService.PATH + "/attachments", files={"file": ("hu15_api_check.pdf", io.BytesIO(PDF), "application/pdf")}, timeout=60)


@pytest.mark.parametrize("role", ["FPM", "BU", "CEO"])
def test_the_approver_roles_cannot_upload_an_attachment(api_roles, role):
    """Qase HU15-PR-API12 (FPM/FSM), PR-API13 (BU), PR-API14 (CEO) -- the AM can attach (HU-15 screen case FE8 does it), so this is a permission and not a broken endpoint."""
    r = upload(api_roles[role])
    assert r.status_code == 403 and code(r) == "QUOTATION_FORBIDDEN", f"{r.status_code} {r.text[:200]}"


# ================================================================================================ extra fields in an approval are not applied
REFUSAL = "An approver can only send a comment and, for FPM/FSM, the Diagnosis fields."   # the server answer since the build of 2026-11-09 (OP-136 / Qase #172 fixed)


def test_a_fpm_approval_that_carries_other_fields_is_refused_and_changes_nothing(quotation_api, make_quotation):
    """Qase HU15-PR-API15 -- the approval is refused (HTTP 400, nothing saved, still waiting); then the same approval with only the comment and the Diagnosis is accepted and saves the Diagnosis."""
    qid = make_quotation("EXTRA", ["FPM"], title_prefix="HU15")[0]
    before = get_body_as(quotation_api, "AM", qid)
    r = quotation_api["FPM"].approve(qid, "FPM approves", diagnosis={"cause": "Cause by FPM"}, title="CHANGED", totalAmount=1, arrangement={"laborCostHour": 999})
    assert r.status_code == 400 and REFUSAL in r.text, f"{r.status_code} {r.text[:300]}"
    after = get_body_as(quotation_api, "AM", qid)
    assert after["title"] == before["title"] and after["arrangement"]["laborCostHour"] == before["arrangement"]["laborCostHour"] and after["totalAmount"] == before["totalAmount"]
    assert after["status"] == before["status"] and after.get("cause") == before.get("cause")
    ok = quotation_api["FPM"].approve(qid, "FPM approves", diagnosis={"cause": "Cause by FPM"})
    assert ok.status_code == 200, f"{ok.status_code} {ok.text[:200]}"
    assert get_body_as(quotation_api, "AM", qid)["cause"] == "Cause by FPM"


def test_a_bu_approval_that_carries_other_fields_is_refused_and_changes_nothing(quotation_api, make_waiting_for_bu):
    """Qase HU15-PR-API16 -- same for the BU approver: HTTP 400, nothing saved, still waiting on the BU."""
    qid = make_waiting_for_bu("EXTRA")[0]
    before = get_body_as(quotation_api, "AM", qid)
    r = quotation_api["BU"].approve(qid, "BU approves", title="CHANGED", totalAmount=1)
    assert r.status_code == 400 and REFUSAL in r.text, f"{r.status_code} {r.text[:300]}"
    after = get_body_as(quotation_api, "AM", qid)
    assert after["title"] == before["title"] and after["totalAmount"] == before["totalAmount"] and after["status"] == before["status"]


@pytest.mark.parametrize("role", ["FPM", "BU", "CEO"])
def test_an_approval_that_carries_other_fields_is_rejected(quotation_api, make_quotation, make_waiting_for_bu, role):
    """Qase HU15-PR-API17 (FPM/FSM), PR-API18 (BU), PR-API19 (CEO)"""
    qid = make_quotation("EXTRAREJ", ["FPM"], title_prefix="HU15")[0] if role == "FPM" else make_waiting_for_bu("EXTRAREJ", route=("FPM", role))[0]
    r = quotation_api[role].approve(qid, f"{role} approves", title="CHANGED", totalAmount=1)
    assert 400 <= r.status_code < 500, f"{r.status_code} {r.text[:200]}"
