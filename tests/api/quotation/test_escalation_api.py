"""Quotation module -- Escalation of the quotation across approval levels, server side (OP-32 / HU-21; Qase suite "HU-21: Escalation of the quotation across approval levels", cases API*).

Only the HU-21 text decides what must happen. The system answers (observed on the QA build of 2026-10-25):
  GET  /api/quotations/{id}                 -> status, workflowStage, totalAmount and the approvers (order, role FPM_FSM | BU | CEO, status Pending | Approved | Rejected, isAutoAssigned)
  GET  /api/quotations?page=..&pageSize=..  -> the AM's list, each row with status, workflowStage, waitingOnName and waitingOnRole
  GET  /api/quotations/pending-approval     -> what each approver has in front of them
  GET  /api/quotations/{id}/events          -> the history: eventType, actorName, actorRole, comment, occurredAt, statusAfter
  PUT  /api/quotations/{id}                 -> the AM's save; after the first decision a change of the approvers is refused (APPROVAL_ROUTE_FROZEN)
Internal names that the screen translates: the status 'Awaiting' is shown as 'Submitted'; the stages 'Quoting' and 'Vendor Reviewing' are shown as 'Quoting' / 'OEM Review' in the list; the tests
check what the story fixes (who has the quotation, the order, the added approvers, Returned / Rejected, the history) and not those internal words.
Not testable (they need the OEM to decide): 'Rejected by OEM', the stage 'Ready for Client', the status 'Approved'; and the atomic save of the decision, because the system cannot be made to fail on demand.
Run the UI and the API suites one at a time: both ask the system for the next Quote # and can get the same suggestion.
"""
import copy
import re

import pytest

from framework_api.client.role_session import RoleApiSession
from framework_api.services import quotation_setup as qs
from framework_api.services.quotation_service import QuotationService
from shared.config.credentials import load_role_credentials

pytestmark = pytest.mark.api

REC = "Reviewed for the escalation tests."
FROZEN_MESSAGE = "The approval route is locked after the first decision and cannot be changed."
NOT_CURRENT_MESSAGE = "Only the approver currently pending on this quotation can decide."
LEVEL = {"FPM_FSM": 0, "BU": 1, "CEO": 2}


def hotel_for(total):
    return {"hotelCost": 1050 + (total - 8410)}


def body_of(quotation_api, qid):
    r = quotation_api["AM"].client.get(f"/api/quotations/{qid}")
    assert r.status_code == 200, f"{r.status_code} {r.text[:200]}"
    return r.json()


def route(body):
    """[(role, status, isAutoAssigned)] in route order."""
    return [(a["role"], a["status"], a["isAutoAssigned"]) for a in sorted(body["approvers"], key=lambda a: a["order"])]


def roles_of(body):
    return [r[0] for r in route(body)]


def pending_ids(api_roles, role):
    r = api_roles[role].get("/api/quotations/pending-approval", page=1, pageSize=100)
    assert r.status_code == 200, f"{r.status_code} {r.text[:200]}"
    return {i["id"] for i in r.json()["items"]}


def who_has_it(api_roles, qid, roles=("FPM", "BU", "CEO")):
    return [role for role in roles if qid in pending_ids(api_roles, role)]


def list_row(api_roles, qid):
    r = api_roles["AM"].get("/api/quotations", page=1, pageSize=100, includeClosed="false")
    assert r.status_code == 200, f"{r.status_code} {r.text[:200]}"
    return next(i for i in r.json()["items"] if i["id"] == qid)


def events_of(api_roles, qid):
    r = api_roles["AM"].get(f"/api/quotations/{qid}/events")
    assert r.status_code == 200, f"{r.status_code} {r.text[:200]}"
    return r.json()


def put(session, qid, body):
    return session.session.put(f"{session.base_url}{QuotationService.PATH}/{qid}", json=body, timeout=60)


def code(r):
    return (r.json().get("details") or {}).get("code")


def ok(r):
    assert r.status_code == 200, f"{r.status_code} {r.text[:200]}"


@pytest.fixture(scope="module")
def default_api():
    sessions = {}
    for role in ("FPM", "BU", "CEO"):
        creds = load_role_credentials(f"DEFAULT_{role}")
        if creds is None:
            pytest.skip(f"QUOTATION_DEFAULT_{role}_* not set in .env")
        sessions[role] = QuotationService(RoleApiSession(creds["email"], creds["password"]))
    return sessions


def make(make_quotation, tag, route_, total=None):
    return make_quotation(tag, route_, arrangement=hotel_for(total) if total else None, title_prefix="HU21-API")[0]


# ================================================================================================ the full path, step by step
@pytest.fixture(scope="module")
def path(api_roles, quotation_api, make_quotation):
    qid = make(make_quotation, "PATH", ["FPM", "BU", "CEO"])
    s = {"id": qid, "submitted": dict(row=list_row(api_roles, qid), has=who_has_it(api_roles, qid), body=body_of(quotation_api, qid))}
    ok(quotation_api["FPM"].approve(qid, REC))
    s["returned"] = dict(row=list_row(api_roles, qid), has=who_has_it(api_roles, qid), body=body_of(quotation_api, qid))
    ok(quotation_api["AM"].submit(qid))
    s["bu_turn"] = dict(row=list_row(api_roles, qid), has=who_has_it(api_roles, qid), body=body_of(quotation_api, qid))
    ok(quotation_api["BU"].approve(qid, REC))
    s["ceo_turn"] = dict(row=list_row(api_roles, qid), has=who_has_it(api_roles, qid), body=body_of(quotation_api, qid))
    ok(quotation_api["CEO"].approve(qid, REC))
    s["oem"] = dict(row=list_row(api_roles, qid), has=who_has_it(api_roles, qid), body=body_of(quotation_api, qid))
    s["events"] = events_of(api_roles, qid)
    return s


def test_the_fpm_fsm_has_the_quotation_first(path):
    """Qase HU21-API1 -- route FPM/FSM, BU, CEO: after the submit only the FPM/FSM has it."""
    s = path["submitted"]
    assert s["has"] == ["FPM"] and s["row"]["waitingOnName"] == "QA Jhe FPM" and s["row"]["waitingOnRole"] == "FPM_FSM", s


def test_each_approver_has_one_level_and_the_levels_go_in_order(path):
    """Qase HU21-API2 -- every approver has one of the levels FPM/FSM, BU, CEO, each once, in that order."""
    roles = roles_of(path["submitted"]["body"])
    assert roles == ["FPM_FSM", "BU", "CEO"] and [LEVEL[r] for r in roles] == sorted(LEVEL[r] for r in roles), roles


def test_only_one_approver_has_the_quotation_at_a_time_all_along_the_route(path):
    """Qase HU21-API3 -- FPM/FSM, then BU, then CEO, then nobody inside (the OEM): never two at once."""
    assert [path[k]["has"] for k in ("submitted", "returned", "bu_turn", "ceo_turn", "oem")] == [["FPM"], [], ["BU"], ["CEO"], []]
    assert path["oem"]["row"]["waitingOnRole"] == "OEM", path["oem"]["row"]


def test_a_decision_out_of_turn_is_refused_and_nothing_changes(quotation_api, make_quotation):
    """Qase HU21-API4 -- the CEO approves and the BU rejects while the FPM/FSM has the quotation: refused, nobody decided."""
    qid = make(make_quotation, "OOT", ["FPM", "BU", "CEO"])
    for role, call in (("CEO", quotation_api["CEO"].approve), ("BU", quotation_api["BU"].reject)):
        r = call(qid, "too early")
        assert r.status_code == 400 and code(r) == "NOT_CURRENT_APPROVER" and r.json()["message"] == NOT_CURRENT_MESSAGE, f"{role}: {r.status_code} {r.text[:200]}"
    assert route(body_of(quotation_api, qid)) == [("FPM_FSM", "Pending", False), ("BU", "Pending", False), ("CEO", "Pending", False)]


def test_the_levels_keep_their_order_even_if_the_am_added_the_bu_first(quotation_api, make_quotation):
    """Qase HU21-API5 -- route sent as BU, FPM/FSM: the system stores FPM/FSM first."""
    qid = make(make_quotation, "WORD", ["BU", "FPM"])
    assert roles_of(body_of(quotation_api, qid)) == ["FPM_FSM", "BU"]


def test_without_a_fpm_fsm_the_route_starts_at_the_next_level(api_roles, quotation_api, make_quotation):
    """Qase HU21-API6 -- route with only the BU: nobody is added in front, and the BU has it."""
    qid = make(make_quotation, "BUONLY", ["BU"])
    assert route(body_of(quotation_api, qid)) == [("BU", "Pending", False)] and who_has_it(api_roles, qid) == ["BU"]


def test_approvers_of_the_same_level_review_in_the_order_the_am_added_them(api_roles, quotation_api, default_api):
    """Qase HU21-API7 -- two BU approvers: the first one added has it, the second one only after."""
    default_bu = default_api["BU"].client
    approvers = [{"workflowStage": "", "order": 0, "role": "BU", "userId": api_roles["BU"].user_id, "userName": "QA Jhe BU", "email": api_roles["BU"].email, "status": "Pending", "isAutoAssigned": False},
                 {"workflowStage": "", "order": 1, "role": "BU", "userId": default_bu.user_id, "userName": "QA Default BU", "email": default_bu.email, "status": "Pending", "isAutoAssigned": False}]
    qid, _ = qs.create_and_submit(api_roles["AM"], api_roles, "SAMELVL", ["BU"], title_prefix="HU21-API", extra={"approvers": approvers})
    assert list_row(api_roles, qid)["waitingOnName"] == "QA Jhe BU"
    ok(quotation_api["BU"].approve(qid, REC))
    assert list_row(api_roles, qid)["waitingOnName"] == "QA Default BU"


# ================================================================================================ the amount rule
AMOUNT_ROUTES = [
    ("API8", 99999, ["FPM"], [("FPM_FSM", False)]),
    ("API9", 100000, ["FPM"], [("FPM_FSM", False), ("BU", True)]),
    ("API10", 499999, ["FPM"], [("FPM_FSM", False), ("BU", True)]),
    ("API11", 500000, ["FPM"], [("FPM_FSM", False), ("BU", True)]),
    ("API12", 500001, ["FPM"], [("FPM_FSM", False), ("CEO", True)]),
    ("API13", 8410, [], [("FPM_FSM", True)]),
    ("API14", 150000, [], [("BU", True)]),
    ("API15", 600000, [], [("CEO", True)]),
    ("API16", 600000, ["FPM", "BU"], [("FPM_FSM", False), ("BU", False), ("CEO", True)]),
    ("API17", 150000, ["FPM", "BU"], [("FPM_FSM", False), ("BU", False)]),
    ("API18", 8410, ["FPM", "BU"], [("FPM_FSM", False), ("BU", False)]),
]


@pytest.mark.parametrize("key, total, route_, expected", AMOUNT_ROUTES, ids=[f"{k}-{t}-{'_'.join(r) or 'no_approver'}" for k, t, r, _ in AMOUNT_ROUTES])
def test_the_amount_rule_adds_the_missing_level_and_only_that_one(quotation_api, make_quotation, key, total, route_, expected):
    """Qase HU21-API8 ($99,999), API9 ($100,000), API10 ($499,999), API11 ($500,000 exactly: only the BU; the CEO starts at $500,001 -- OP-112 fix, QA decision 2026-11-11), API12 ($500,001), API13 (no approver, below $100,000: default FPM/FSM), API14 (no approver, $150,000: only the BU),
    API15 (no approver, $600,000: only the CEO), API16 ($600,000 with the BU chosen by the AM: the CEO is added), API17 ($150,000 with a BU already there: none added), API18 (nobody removed below $100,000)."""
    qid = make(make_quotation, f"AMT{total}", route_, total)
    body = body_of(quotation_api, qid)
    assert body["totalAmount"] == total, body["totalAmount"]
    assert [(role, auto) for role, _, auto in route(body)] == expected, route(body)


# ================================================================================================ returned, rejected, never approved
def test_the_fpm_fsm_approval_returns_the_quotation_to_the_am_even_when_it_is_the_only_approver(api_roles, quotation_api, make_quotation):
    """Qase HU21-API19 -- status Returned and it is with the AM."""
    qid = make(make_quotation, "L1ONLY", ["FPM"])
    ok(quotation_api["FPM"].approve(qid, REC))
    assert body_of(quotation_api, qid)["status"] == "Returned"
    row = list_row(api_roles, qid)
    assert row["waitingOnRole"] == "AM" and who_has_it(api_roles, qid) == [], row


def test_after_the_new_submit_the_next_approver_has_it_and_the_fpm_fsm_approval_is_kept(path):
    """Qase HU21-API20 -- the FPM/FSM stays Approved, the BU is Pending and has it."""
    s = path["bu_turn"]
    assert route(s["body"]) == [("FPM_FSM", "Approved", False), ("BU", "Pending", False), ("CEO", "Pending", False)] and s["row"]["waitingOnRole"] == "BU", s


def test_the_returned_quotation_is_with_the_am_and_nobody_else(path):
    """Qase HU21-API21"""
    s = path["returned"]
    assert s["body"]["status"] == "Returned" and s["row"]["waitingOnRole"] == "AM" and s["has"] == [], s


def test_internal_approvals_never_mark_the_quotation_as_approved(path):
    """Qase HU21-API22 -- after the FPM/FSM, the BU and the CEO approved: every approver is Approved, the quotation is not, and it waits on the OEM."""
    s = path["oem"]
    assert [st for _, st, _ in route(s["body"])] == ["Approved"] * 3, route(s["body"])
    assert s["body"]["status"] != "Approved" and s["row"]["waitingOnRole"] == "OEM", s


@pytest.fixture(scope="module", params=["FPM", "BU", "CEO"])
def rejected(request, api_roles, quotation_api, make_quotation):
    level = request.param
    qid = make(make_quotation, f"REJ{level}", ["FPM", "BU", "CEO"])
    if level in ("BU", "CEO"):
        ok(quotation_api["FPM"].approve(qid, REC)); ok(quotation_api["AM"].submit(qid))
    if level == "CEO":
        ok(quotation_api["BU"].approve(qid, REC))
    ok(quotation_api[level].reject(qid, f"{level} rejects it."))
    s = {"level": level, "id": qid, "role": {"FPM": "FPM_FSM", "BU": "BU", "CEO": "CEO"}[level]}
    s["rejected"] = dict(body=body_of(quotation_api, qid), row=list_row(api_roles, qid), has=who_has_it(api_roles, qid))
    s["out_of_turn"] = [quotation_api[r].approve(qid, "no turn") for r in ("FPM", "BU", "CEO") if r != level]
    ok(quotation_api["AM"].submit(qid))
    s["again"] = dict(body=body_of(quotation_api, qid), row=list_row(api_roles, qid), has=who_has_it(api_roles, qid), events=events_of(api_roles, qid))
    return s


def test_a_rejection_by_an_internal_level_returns_the_quotation_to_the_am(rejected):
    """Qase HU21-API23 (FPM/FSM), API24 (BU), API25 (CEO) -- status Rejected, with the AM; the approvers before stay Approved, the one that rejected is Rejected, the next ones Pending."""
    s = rejected["rejected"]
    assert s["body"]["status"] == "Rejected" and s["row"]["waitingOnRole"] == "AM", s
    order = LEVEL[rejected["role"]]
    expected = ["Approved" if LEVEL[r] < order else "Rejected" if LEVEL[r] == order else "Pending" for r in ("FPM_FSM", "BU", "CEO")]
    assert [st for _, st, _ in route(s["body"])] == expected, route(s["body"])


def test_the_next_levels_do_not_receive_the_rejected_quotation(rejected):
    """Qase HU21-API26 (FPM/FSM), API27 (BU), API28 (CEO) -- nobody has it, and a decision by any other approver is refused."""
    assert rejected["rejected"]["has"] == [], rejected["rejected"]["has"]
    assert all(r.status_code == 400 for r in rejected["out_of_turn"]), [r.status_code for r in rejected["out_of_turn"]]


def test_when_the_am_submits_again_the_quotation_goes_back_to_the_approver_who_rejected_it(rejected):
    """Qase HU21-API29 (FPM/FSM), API30 (BU), API31 (CEO) -- that approver is Pending again and has it; the earlier approvals stay Approved."""
    s = rejected["again"]
    order = LEVEL[rejected["role"]]
    expected = ["Approved" if LEVEL[r] < order else "Pending" for r in ("FPM_FSM", "BU", "CEO")]
    assert [st for _, st, _ in route(s["body"])] == expected, route(s["body"])
    assert s["has"] == [rejected["level"]] and s["body"]["status"] == "Awaiting", s


# ================================================================================================ submitting again after changes
def test_after_the_first_decision_a_change_of_the_route_is_refused(api_roles, quotation_api, make_quotation):
    """Qase HU21-API32 -- the AM drops the BU from a Returned quotation: HTTP 400 APPROVAL_ROUTE_FROZEN and the route stays."""
    qid = make(make_quotation, "FROZEN", ["FPM", "BU"])
    ok(quotation_api["FPM"].approve(qid, REC))
    body = body_of(quotation_api, qid)
    changed = copy.deepcopy(body)
    changed["approvers"] = [a for a in changed["approvers"] if a["role"] != "BU"]
    r = put(api_roles["AM"], qid, changed)
    assert r.status_code == 400 and code(r) == "APPROVAL_ROUTE_FROZEN" and r.json()["message"] == FROZEN_MESSAGE, f"{r.status_code} {r.text[:200]}"
    assert roles_of(body_of(quotation_api, qid)) == ["FPM_FSM", "BU"]


def test_after_the_first_decision_the_am_can_still_save_the_rest_of_the_quotation(api_roles, quotation_api, make_quotation):
    """Qase HU21-API33 -- a save that keeps the route and changes the amount is accepted and the new amount is stored."""
    qid = make(make_quotation, "EDITOK", ["FPM"])
    ok(quotation_api["FPM"].approve(qid, REC))
    body = body_of(quotation_api, qid)
    body["arrangement"]["hotelCost"] = 1050 + 3000
    ok(put(api_roles["AM"], qid, body))
    assert body_of(quotation_api, qid)["totalAmount"] == 8410 + 3000


@pytest.mark.parametrize("key, new_total, expected", [("API34", 107410, [("FPM_FSM", "Approved", False), ("BU", "Pending", True)]), ("API35", 600000, [("FPM_FSM", "Approved", False), ("CEO", "Pending", True)])])
def test_a_new_amount_adds_the_missing_level_on_the_new_submit_and_keeps_the_approval(api_roles, quotation_api, make_quotation, key, new_total, expected):
    """Qase HU21-API34 (the amount goes up to $107,410: the BU is added), API35 ($600,000: only the CEO) -- the FPM/FSM approval is kept."""
    qid = make(make_quotation, f"UP{new_total}", ["FPM"])
    ok(quotation_api["FPM"].approve(qid, REC))
    body = body_of(quotation_api, qid)
    body["arrangement"].update(hotel_for(new_total))
    ok(put(api_roles["AM"], qid, body))
    ok(quotation_api["AM"].submit(qid))
    assert route(body_of(quotation_api, qid)) == expected, route(body_of(quotation_api, qid))


def test_a_lower_amount_does_not_remove_a_level_that_was_added(api_roles, quotation_api, make_quotation):
    """Qase HU21-API36 -- the BU added at $150,000 is still in the route after the amount drops below $100,000."""
    qid = make(make_quotation, "DOWN", ["FPM"], 150000)
    assert roles_of(body_of(quotation_api, qid)) == ["FPM_FSM", "BU"]
    ok(quotation_api["FPM"].approve(qid, REC))
    body = body_of(quotation_api, qid)
    body["arrangement"].update(hotel_for(8410))
    ok(put(api_roles["AM"], qid, body))
    ok(quotation_api["AM"].submit(qid))
    after = body_of(quotation_api, qid)
    assert after["totalAmount"] == 8410 and route(after) == [("FPM_FSM", "Approved", False), ("BU", "Pending", True)], route(after)
    assert list_row(api_roles, qid)["waitingOnRole"] == "BU"


# ================================================================================================ the history (events)
def test_every_submit_and_decision_is_recorded_in_order_with_the_person_the_level_and_the_outcome(path):
    """Qase HU21-API37 -- Created, Submitted, Approved (FPM/FSM), Submitted, Approved (BU), Approved (CEO), each with who did it, their level, the new status and the date."""
    ev = path["events"]
    assert [e["eventType"] for e in ev] == ["Created", "Submitted", "Approved", "Submitted", "Approved", "Approved"], [e["eventType"] for e in ev]
    assert [(e["actorName"], e["actorRole"]) for e in ev] == [("Jherico Ascencio", "AM"), ("Jherico Ascencio", "AM"), ("QA Jhe FPM", "FPM_FSM"), ("Jherico Ascencio", "AM"), ("QA Jhe BU", "BU"), ("QA Jhe CEO", "CEO")]
    assert all(re.match(r"\d{4}-\d{2}-\d{2}T", e["occurredAt"]) for e in ev)
    assert [e["occurredAt"] for e in ev] == sorted(e["occurredAt"] for e in ev), "the events are in time order"


def test_the_approvals_keep_the_recommendation_and_the_new_status(path):
    """Qase HU21-API38 -- each approval has the recommendation; the status after the FPM/FSM is Returned and after the others it stays in review."""
    approvals = [e for e in path["events"] if e["eventType"] == "Approved"]
    assert [e["comment"] for e in approvals] == [REC] * 3, approvals
    assert [e["statusAfter"] for e in approvals][0] == "Returned" and all(e["statusAfter"] != "Approved" for e in approvals), approvals


def test_a_rejection_is_recorded_with_the_person_the_level_the_reason_and_the_new_status(rejected):
    """Qase HU21-API39 (FPM/FSM), API40 (BU), API41 (CEO) -- followed by the AM's new submit."""
    ev = rejected["again"]["events"]
    rej = [e for e in ev if e["eventType"] == "Rejected"]
    assert len(rej) == 1 and rej[0]["actorRole"] == rejected["role"] and rej[0]["comment"] == f"{rejected['level']} rejects it." and rej[0]["statusAfter"] == "Rejected", rej
    assert ev[-1]["eventType"] == "Submitted" and ev[-1]["actorRole"] == "AM" and ev[-2]["eventType"] == "Rejected", [e["eventType"] for e in ev]
