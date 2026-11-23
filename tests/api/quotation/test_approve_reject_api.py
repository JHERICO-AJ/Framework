"""Quotation module -- Approve or reject a quotation, API layer (OP-31 / HU-22; Qase suite "HU-22: Approve or reject a quotation", cases API1-API26).

Calls the server directly (no browser): POST /api/quotations/{id}/approve | reject with {"comment": "...", "diagnosis": {...}}, as each
role (AM, FPM/FSM, BU, CEO test accounts). Quotations are created and submitted through the API too (tests/api/quotation/support.py).
The UI tests of the same story are in tests/ui/quotation/test_approve_reject.py; these check that the SERVER enforces the rules and not only the screen.

What the server answers was observed on the QA build of 2026-10-21 (HU-22 does not define the server's responses): 401 without login;
403 QUOTATION_FORBIDDEN for the AM; 400 NOT_CURRENT_APPROVER outside the turn; 400 DIAGNOSIS_EDIT_NOT_ALLOWED for BU/CEO; 400 with the
messages asserted below for the comment and the Diagnosis limits; 404 for an unknown quotation. Messages are matched by their key phrase.
Quotations are shared through module-scoped fixtures: pending_* are never decided, the others are decided once and read by several tests.
"""
import uuid

import pytest

from framework_api.client.role_session import anonymous_post
from shared.datasource.quotation_db_source import (
    get_approver_decisions_by_quote_no, get_events_by_quote_no, get_quotation_state)

pytestmark = pytest.mark.api

REC = "Reviewed and agreed, the scope and cost are correct."
REQUIRED = "A reason/comment is required"
TOO_LONG = "at most 1000 characters"
NO_EMOJI = "cannot contain emoji"
NOT_AWAITING = "Only quotations awaiting approval can be approved or rejected"


def message(response):
    try:
        return response.json().get("message", "")
    except ValueError:
        return response.text


def code(response):
    try:
        return (response.json().get("details") or {}).get("code")
    except ValueError:
        return None


def events(db_conn, quote_no, kind=None):
    rows = get_events_by_quote_no(db_conn, quote_no)
    return [e for e in rows if kind is None or e["EventType"] == kind]


def nothing_decided(db_conn, quote_no):
    state = get_quotation_state(db_conn, quote_no)
    return state["EstadoCotizacion"] == "Awaiting" and not events(db_conn, quote_no, "Approved") and not events(db_conn, quote_no, "Rejected")


# ------------------------------------------------------------------------------------------------ quotations that are never decided
@pytest.fixture(scope="module")
def pending_fpm(make_quotation):
    return make_quotation("PF", ["FPM"])


@pytest.fixture(scope="module")
def pending_bu(make_quotation):
    return make_quotation("PB", ["BU"])


@pytest.fixture(scope="module")
def pending_ceo(make_quotation):
    return make_quotation("PC", ["CEO"])


# ================================================================================================ access and permissions
def test_a_decision_without_logging_in_is_refused(db_conn, pending_fpm):
    """Qase API1"""
    qid, quote = pending_fpm
    r = anonymous_post(f"/api/quotations/{qid}/approve", json={"comment": REC})
    assert r.status_code == 401
    assert nothing_decided(db_conn, quote)


def test_the_am_cannot_approve(db_conn, quotation_api, pending_fpm):
    """Qase API2"""
    qid, quote = pending_fpm
    r = quotation_api["AM"].approve(qid, REC)
    assert r.status_code == 403 and code(r) == "QUOTATION_FORBIDDEN", f"{r.status_code} {r.text[:200]}"
    assert nothing_decided(db_conn, quote)


def test_the_am_cannot_reject(db_conn, quotation_api, pending_fpm):
    """Qase API3"""
    qid, quote = pending_fpm
    r = quotation_api["AM"].reject(qid, REC)
    assert r.status_code == 403 and code(r) == "QUOTATION_FORBIDDEN", f"{r.status_code} {r.text[:200]}"
    assert nothing_decided(db_conn, quote)


def test_an_approver_who_is_not_in_the_route_cannot_decide(db_conn, quotation_api, pending_fpm):
    """Qase API4 -- the BU approver is not a signer of this quotation."""
    qid, quote = pending_fpm
    r = quotation_api["BU"].approve(qid, REC)
    assert r.status_code == 400 and code(r) == "NOT_CURRENT_APPROVER", f"{r.status_code} {r.text[:200]}"
    assert nothing_decided(db_conn, quote)


@pytest.mark.parametrize("role", ["BU", "CEO"])
def test_bu_and_ceo_cannot_edit_the_diagnosis_when_deciding(db_conn, quotation_api, pending_bu, pending_ceo, role):
    """Qase API5 (BU) and API6 (CEO) -- only the Level 1 (FPM/FSM) approver can edit the Diagnosis."""
    qid, quote = pending_bu if role == "BU" else pending_ceo
    r = quotation_api[role].approve(qid, REC, diagnosis={"cause": f"{role} wrote this"})
    assert r.status_code == 400 and code(r) == "DIAGNOSIS_EDIT_NOT_ALLOWED", f"{r.status_code} {r.text[:200]}"
    assert nothing_decided(db_conn, quote)


# ================================================================================================ the recommendation (comment)
def test_approve_with_an_empty_comment_is_refused(db_conn, quotation_api, pending_fpm):
    """Qase API7"""
    qid, quote = pending_fpm
    r = quotation_api["FPM"].approve(qid, "")
    assert r.status_code == 400 and REQUIRED in message(r), f"{r.status_code} {r.text[:200]}"
    assert nothing_decided(db_conn, quote)


def test_approve_with_a_comment_of_only_spaces_is_refused(db_conn, quotation_api, pending_fpm):
    """Qase API8"""
    qid, quote = pending_fpm
    r = quotation_api["FPM"].approve(qid, "     ")
    assert r.status_code == 400 and REQUIRED in message(r), f"{r.status_code} {r.text[:200]}"
    assert nothing_decided(db_conn, quote)


def test_approve_without_a_comment_is_refused(db_conn, quotation_api, pending_fpm):
    """Qase API9"""
    qid, quote = pending_fpm
    r = quotation_api["FPM"].approve(qid)
    assert r.status_code == 400 and REQUIRED in message(r), f"{r.status_code} {r.text[:200]}"
    assert nothing_decided(db_conn, quote)


def test_reject_with_an_empty_comment_is_refused(db_conn, quotation_api, pending_fpm):
    """Qase API10"""
    qid, quote = pending_fpm
    r = quotation_api["FPM"].reject(qid, "")
    assert r.status_code == 400 and REQUIRED in message(r), f"{r.status_code} {r.text[:200]}"
    assert nothing_decided(db_conn, quote)


def test_a_comment_of_1001_characters_is_refused(db_conn, quotation_api, pending_fpm):
    """Qase API12"""
    qid, quote = pending_fpm
    r = quotation_api["FPM"].approve(qid, "a" * 1001)
    assert r.status_code == 400 and TOO_LONG in message(r), f"{r.status_code} {r.text[:200]}"
    assert nothing_decided(db_conn, quote)


def test_a_comment_with_an_emoji_is_refused(db_conn, quotation_api, pending_fpm):
    """Qase API13 -- the screen removes emoji as they are typed; the server refuses them if they arrive."""
    qid, quote = pending_fpm
    r = quotation_api["FPM"].approve(qid, "Great \U0001F600 job")
    assert r.status_code == 400 and NO_EMOJI in message(r), f"{r.status_code} {r.text[:200]}"
    assert nothing_decided(db_conn, quote)


def test_a_comment_of_exactly_1000_characters_is_accepted(db_conn, quotation_api, make_quotation):
    """Qase API11"""
    qid, quote = make_quotation("L1000", ["FPM"])
    r = quotation_api["FPM"].approve(qid, "a" * 1000)
    assert r.status_code == 200, f"{r.status_code} {r.text[:200]}"
    assert len(events(db_conn, quote, "Approved")[-1]["Comment"]) == 1000


def test_spaces_around_the_comment_are_removed_when_saving(db_conn, quotation_api, make_quotation):
    """Qase API14"""
    qid, quote = make_quotation("TRIM", ["FPM"])
    r = quotation_api["FPM"].approve(qid, "  Looks good  ")
    assert r.status_code == 200
    assert events(db_conn, quote, "Approved")[-1]["Comment"] == "Looks good"


def test_less_than_and_greater_than_are_saved_as_typed(db_conn, quotation_api, make_quotation):
    """Qase API15"""
    qid, quote = make_quotation("ANGLE", ["FPM"])
    r = quotation_api["FPM"].reject(qid, "<b>cost</b> > budget")
    assert r.status_code == 200
    assert events(db_conn, quote, "Rejected")[-1]["Comment"] == "<b>cost</b> > budget"


# ================================================================================================ status and outcome
@pytest.fixture(scope="module")
def approved(quotation_api, make_quotation):
    """Route FPM; the FPM/FSM approver approves through the API."""
    qid, quote = make_quotation("APP", ["FPM"])
    response = quotation_api["FPM"].approve(qid, "Approved by the API test")
    return dict(id=qid, quote=quote, response=response)


@pytest.fixture(scope="module")
def rejected(quotation_api, make_quotation):
    """Route FPM; the FPM/FSM approver rejects through the API."""
    qid, quote = make_quotation("REJ", ["FPM"])
    response = quotation_api["FPM"].reject(qid, "Rejected by the API test")
    return dict(id=qid, quote=quote, response=response)


def test_an_approval_by_the_fpm_approver_returns_the_quotation_to_the_am(db_conn, approved):
    """Qase API20"""
    assert approved["response"].status_code == 200
    assert get_quotation_state(db_conn, approved["quote"])["EstadoCotizacion"] == "Returned"
    ev = events(db_conn, approved["quote"], "Approved")[-1]
    assert ev["ActorRole"] == "FPM_FSM" and ev["Comment"] == "Approved by the API test" and ev["OccurredAt"] is not None
    row = [a for a in get_approver_decisions_by_quote_no(db_conn, approved["quote"]) if a["Rol"] == "FPM_FSM"][0]
    assert row["Estado"] == "Approved" and row["Comentario"] == "Approved by the API test"


def test_a_rejection_by_the_fpm_approver_returns_the_quotation_to_the_am(db_conn, rejected):
    """Qase API21"""
    assert rejected["response"].status_code == 200
    assert get_quotation_state(db_conn, rejected["quote"])["EstadoCotizacion"] == "Rejected"
    ev = events(db_conn, rejected["quote"], "Rejected")[-1]
    assert ev["ActorRole"] == "FPM_FSM" and ev["Comment"] == "Rejected by the API test"
    row = [a for a in get_approver_decisions_by_quote_no(db_conn, rejected["quote"]) if a["Rol"] == "FPM_FSM"][0]
    assert row["Estado"] == "Rejected" and row["Comentario"] == "Rejected by the API test"


def test_a_second_approval_of_an_already_decided_quotation_is_refused(db_conn, quotation_api, approved):
    """Qase API16"""
    r = quotation_api["FPM"].approve(approved["id"], "Second approval")
    assert r.status_code == 400 and NOT_AWAITING in message(r), f"{r.status_code} {r.text[:200]}"
    assert len(events(db_conn, approved["quote"], "Approved")) == 1


def test_a_rejection_after_an_approval_is_refused(db_conn, quotation_api, approved):
    """Qase API17"""
    r = quotation_api["FPM"].reject(approved["id"], "Changed my mind")
    assert r.status_code == 400 and NOT_AWAITING in message(r), f"{r.status_code} {r.text[:200]}"
    assert not events(db_conn, approved["quote"], "Rejected")


def test_an_approval_after_a_rejection_is_refused(db_conn, quotation_api, rejected):
    """Qase API18"""
    r = quotation_api["FPM"].approve(rejected["id"], "Changed my mind")
    assert r.status_code == 400 and NOT_AWAITING in message(r), f"{r.status_code} {r.text[:200]}"
    assert not events(db_conn, rejected["quote"], "Approved")


def test_a_decision_on_an_unknown_quotation_is_refused(quotation_api):
    """Qase API19"""
    r = quotation_api["FPM"].approve(str(uuid.uuid4()), REC)
    assert r.status_code == 404, f"{r.status_code} {r.text[:200]}"


# ================================================================================================ the Diagnosis section
DIAGNOSIS = {"signal": "Voltage drop on bus 2", "trigger": "Alarm 4012", "cause": "Loose terminal", "notes": "Bring torque wrench",
             "sopDescription": "1. Isolate. 2. Tighten."}


def test_the_fpm_approver_saves_the_five_diagnosis_fields_with_the_decision(db_conn, api_roles, quotation_api, make_quotation):
    """Qase API22"""
    qid, quote = make_quotation("DIAG", ["FPM"])
    r = quotation_api["FPM"].approve(qid, REC, diagnosis=DIAGNOSIS)
    assert r.status_code == 200, f"{r.status_code} {r.text[:200]}"
    saved = api_roles["AM"].get(f"/api/quotations/{qid}").json()
    for key, value in DIAGNOSIS.items():
        assert saved.get(key) == value, f"{key} must be saved with the decision: {saved.get(key)!r}"


@pytest.mark.parametrize("field, limit", [("signal", 200), ("trigger", 200), ("cause", 5000)])
def test_a_diagnosis_field_over_its_limit_is_refused(db_conn, quotation_api, pending_fpm, field, limit):
    """Qase API23 (SIGNAL 200), API24 (TRIGGER 200) and API25 (CAUSE 5000)."""
    qid, quote = pending_fpm
    r = quotation_api["FPM"].approve(qid, REC, diagnosis={field: "x" * (limit + 1)})
    assert r.status_code == 400, f"{r.status_code} {r.text[:200]}"
    assert "exceeds the maximum" in r.text and field in r.text
    assert nothing_decided(db_conn, quote)


def test_a_field_outside_the_diagnosis_sent_with_the_decision_is_refused(db_conn, api_roles, quotation_api, make_quotation):
    """Qase API26 -- the FPM/FSM approver can change only the Diagnosis: a WO title sent with the decision is refused (HTTP 400, "An approver can only send a comment and, for FPM/FSM, the
    Diagnosis fields." since the build of 2026-11-09; before it answered 200 and ignored it), the title does not change and nothing is decided."""
    qid, quote = make_quotation("EXTRA", ["FPM"])
    before = api_roles["AM"].get(f"/api/quotations/{qid}").json()["title"]
    r = quotation_api["FPM"].approve(qid, REC, title="CHANGED BY THE APPROVER")
    assert r.status_code == 400 and "can only send a comment" in r.text, f"{r.status_code} {r.text[:160]}"
    body = api_roles["AM"].get(f"/api/quotations/{qid}").json()
    assert body["title"] == before, f"the title must not change: {before!r} -> {body['title']!r}"
    assert body["status"] == "Awaiting" and nothing_decided(db_conn, quote)
