"""Quotation module -- the turn of the OEM, server side (OP-32 / HU-21; Qase suite "HU-21: Escalation of the quotation across approval levels", cases OEMAPI*).

The OEM is an external signer (role OEM, no user): it decides from the link of an email, so the tests cannot decide for it (see the internal QA note 'OEM_Guia_de_pruebas'). What they CAN check is
what everybody else may and may not do while the quotation waits on the OEM (observed on the QA build of 2026-10-26):
  PUT  /api/quotations/{id}                      -> 400 QUOTATION_NOT_EDITABLE "Only Draft, Returned, Rejected or OEM-rejected quotations can be updated. ..."
  POST /api/quotations/{id}/submit               -> 400 QUOTATION_NOT_EDITABLE "Only Draft, Returned, Rejected or OEM-rejected quotations can be submitted. ..."
  POST /api/quotations/{id}/approve | reject     -> 400 NOT_CURRENT_APPROVER "Only the approver currently pending on this quotation can decide." (FPM/FSM, BU, CEO)
  GET  /api/quotations/pending-approval          -> the quotation is in nobody's list
One quotation is shared by the whole module and nothing here changes it. Creating it sends ONE real email to the QA test mailbox (framework_api.services.quotation_setup.OEM_TEST_EMAIL).
Run the UI and the API suites one at a time: both ask the system for the next Quote # and can get the same suggestion.
"""
import pytest

from framework_api.services import quotation_setup as qs
from framework_api.services.quotation_service import QuotationService

pytestmark = pytest.mark.api

NOT_UPDATED = "Only Draft, Returned or Rejected quotations can be updated."  # until the 2026-11-09 build the text also said "or OEM-rejected"
NOT_SUBMITTED = "Only Draft, Returned or Rejected quotations can be submitted."
NOT_CURRENT = "Only the approver currently pending on this quotation can decide."


def body_of(api_roles, qid):
    r = api_roles["AM"].get(f"/api/quotations/{qid}")
    assert r.status_code == 200, f"{r.status_code} {r.text[:200]}"
    return r.json()


def events_of(api_roles, qid):
    r = api_roles["AM"].get(f"/api/quotations/{qid}/events")
    assert r.status_code == 200, f"{r.status_code} {r.text[:200]}"
    return r.json()


def code(r):
    return (r.json().get("details") or {}).get("code")


def message(r):
    return r.json().get("message") or r.json().get("error") or ""


def snapshot(api_roles, qid):
    b = body_of(api_roles, qid)
    return dict(status=b["status"], stage=b["workflowStage"], total=b["totalAmount"], notes=b.get("notes"),
                route=[(a["role"], a["status"]) for a in sorted(b["approvers"], key=lambda a: a["order"])], events=len(events_of(api_roles, qid)))


@pytest.fixture(scope="module")
def waiting(api_roles):
    """The id of a quotation that has passed every internal approval and waits on the OEM, and how it looks before the tests."""
    qid, quote_no = qs.create_waiting_on_oem(api_roles, "WAIT")
    row = next(i for i in api_roles["AM"].get("/api/quotations", page=1, pageSize=100, includeClosed="false").json()["items"] if i["id"] == qid)
    assert row["waitingOnRole"] == "OEM", row
    return dict(id=qid, quote_no=quote_no, before=snapshot(api_roles, qid))


def test_the_quotation_waits_on_the_oem_after_the_internal_route(api_roles, waiting):
    """Precondition of the OEMAPI cases: FPM/FSM, BU and CEO approved and only the OEM is pending."""
    assert waiting["before"]["status"] == "Awaiting" and waiting["before"]["stage"] == "Vendor Reviewing", waiting["before"]
    assert waiting["before"]["route"] == [("FPM_FSM", "Approved"), ("BU", "Approved"), ("CEO", "Approved"), ("OEM", "Pending")], waiting["before"]["route"]


def test_the_am_cannot_edit_the_quotation_while_it_waits_on_the_oem(api_roles, waiting):
    """Qase OEMAPI1 -- the AM's save is refused with QUOTATION_NOT_EDITABLE and nothing changes."""
    body = body_of(api_roles, waiting["id"])
    body["notes"] = "edit while waiting on the OEM"
    r = api_roles["AM"].session.put(f"{api_roles['AM'].base_url}{QuotationService.PATH}/{waiting['id']}", json=body, timeout=60)
    assert r.status_code == 400 and code(r) == "QUOTATION_NOT_EDITABLE" and message(r).startswith(NOT_UPDATED), f"{r.status_code} {r.text[:300]}"
    assert snapshot(api_roles, waiting["id"]) == waiting["before"]


def test_the_am_cannot_submit_the_quotation_again_while_it_waits_on_the_oem(api_roles, quotation_api, waiting):
    """Qase OEMAPI2 -- a new submit is refused with QUOTATION_NOT_EDITABLE and nothing changes (no second email to the OEM, no new history event)."""
    r = quotation_api["AM"].submit(waiting["id"])
    assert r.status_code == 400 and code(r) == "QUOTATION_NOT_EDITABLE" and message(r).startswith(NOT_SUBMITTED), f"{r.status_code} {r.text[:300]}"
    assert snapshot(api_roles, waiting["id"]) == waiting["before"]


@pytest.mark.parametrize("role", ["FPM", "BU", "CEO"])
@pytest.mark.parametrize("action", ["approve", "reject"])
def test_an_internal_approver_cannot_decide_when_the_turn_is_the_oems(api_roles, quotation_api, waiting, role, action):
    """Qase OEMAPI3 -- FPM/FSM, BU and CEO get NOT_CURRENT_APPROVER on approve and on reject and nothing changes."""
    r = getattr(quotation_api[role], action)(waiting["id"], "out of turn")
    assert r.status_code == 400 and code(r) == "NOT_CURRENT_APPROVER" and message(r) == NOT_CURRENT, f"{r.status_code} {r.text[:300]}"
    assert snapshot(api_roles, waiting["id"]) == waiting["before"]


@pytest.mark.parametrize("role", ["FPM", "BU", "CEO"])
def test_the_quotation_is_not_pending_for_the_internal_approvers_while_it_waits_on_the_oem(api_roles, waiting, role):
    """Qase OEMAPI4 -- the quotation is in none of the pending-approval lists of FPM/FSM, BU and CEO."""
    r = api_roles[role].get("/api/quotations/pending-approval", page=1, pageSize=100)
    assert r.status_code == 200, f"{r.status_code} {r.text[:200]}"
    assert waiting["id"] not in {i["id"] for i in r.json()["items"]}
