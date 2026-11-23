"""Quotation module -- the history of a quotation, server side (OP-13 / HU-06; Qase suite "HU-06: Quotation state-transition logging and audit trail", cases QH-API*).

Only the HU-06 text decides what must happen: what is recorded (Created, Submitted, Approved, Rejected, each with the actor's name and role, the date, the reason of decisions and the status
right after), nothing recorded when an action fails or is only a save, and an immutable history ("there is no UI or API to edit or delete an entry").
Observed on the QA build of 2026-10-27:
  GET /api/quotations/{id}/events -> a list of {id, eventType, occurredAt, actorEmail, actorName, actorRole, comment, statusAfter} in the order they happened;
  GET /api/quotations/{id}/events/{eventId} -> one of them; PUT, PATCH, POST and DELETE on both paths -> 405 (Allow: GET, HEAD); no login -> 401; an id that does not exist -> 404.
Not tested here, because the story does not say: who may read the history besides the AM (today the FPM/FSM, BU and CEO get 200 on the AM's quotations: a question for the developer).
Each test creates the quotation it needs (titles start with 'Workflow Progress test HU06-') and compares the history with what the same API says about the quotation.
"""
import re

import pytest
import requests

from framework_api.services.quotation_service import QuotationService

pytestmark = pytest.mark.api

FIELDS = {"id", "eventType", "occurredAt", "actorEmail", "actorName", "actorRole", "comment", "statusAfter"}
ACTIONS = {"Created", "Submitted", "Approved", "Rejected"}
ISO_UTC = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?Z$")
UNKNOWN_ID = "00000000-0000-0000-0000-000000000000"


def events_of(api_roles, quotation_id, role="AM"):
    response = api_roles[role].get(f"/api/quotations/{quotation_id}/events")
    assert response.status_code == 200, f"{response.status_code} {response.text[:200]}"
    return response.json()


def status_of(api_roles, quotation_id):
    return api_roles["AM"].get(f"/api/quotations/{quotation_id}").json()["status"]


def put_same_body(api_roles, quotation_id, **changes):
    am = api_roles["AM"]
    body = am.get(f"/api/quotations/{quotation_id}").json()
    body.update(changes)
    return am.session.put(f"{am.base_url}/api/quotations/{quotation_id}", json=body, timeout=90)


@pytest.fixture(scope="module")
def journey(api_roles, quotation_api, make_draft):
    """A quotation taken step by step, noting the status the system reports right after every action: create, submit, FPM/FSM approves (route FPM+BU), the AM sends it on, BU rejects."""
    from framework_api.services.quotation_setup import create_and_submit
    qid, quote_no = create_and_submit(api_roles["AM"], api_roles, "h6api", ["FPM", "BU"], title_prefix="HU06", submit=False)
    seen = [("Created", status_of(api_roles, qid))]
    assert quotation_api["AM"].submit(qid).status_code == 200
    seen.append(("Submitted", status_of(api_roles, qid)))
    assert quotation_api["FPM"].approve(qid, "FPM recommends it.").status_code == 200
    seen.append(("Approved", status_of(api_roles, qid)))
    assert quotation_api["AM"].submit(qid).status_code == 200
    seen.append(("Submitted", status_of(api_roles, qid)))
    assert quotation_api["BU"].reject(qid, "BU does not agree with the scope.").status_code == 200
    seen.append(("Rejected", status_of(api_roles, qid)))
    return qid, quote_no, seen


# ================================================================================================================ what is recorded
def test_every_event_has_the_story_fields_in_the_order_they_happened(api_roles, journey):
    """Qase QH-API1 -- id, action, date, actor's name and role, reason and status after; the dates never go back."""
    events = events_of(api_roles, journey[0])
    assert [set(e) for e in events] == [FIELDS] * len(events)
    assert all(e["eventType"] in ACTIONS and ISO_UTC.match(e["occurredAt"]) and e["actorName"] and e["actorRole"] for e in events), events
    dates = [e["occurredAt"] for e in events]
    assert dates == sorted(dates), dates


def test_the_four_actions_are_recorded_in_order(api_roles, journey):
    """Qase QH-API2 -- Created, Submitted, Approved, Submitted again, Rejected."""
    assert [e["eventType"] for e in events_of(api_roles, journey[0])] == ["Created", "Submitted", "Approved", "Submitted", "Rejected"]


def test_every_event_keeps_the_status_right_after_its_action(api_roles, journey):
    """Qase QH-API3 -- the status after each event is the status the system reported right after that action."""
    assert [(e["eventType"], e["statusAfter"]) for e in events_of(api_roles, journey[0])] == journey[2]


def test_the_actor_name_and_role_are_the_ones_who_acted(api_roles, journey):
    """Qase QH-API4 -- the AM created and submitted, the FPM/FSM approved, the BU rejected."""
    actors = [(e["eventType"], e["actorName"], e["actorRole"]) for e in events_of(api_roles, journey[0])]
    assert actors == [("Created", "Jherico Ascencio", "AM"), ("Submitted", "Jherico Ascencio", "AM"), ("Approved", "QA Jhe FPM", "FPM_FSM"),
                      ("Submitted", "Jherico Ascencio", "AM"), ("Rejected", "QA Jhe BU", "BU")], actors


def test_only_the_decisions_have_a_reason(api_roles, journey):
    """Qase QH-API5 -- Created and Submitted have no reason; Approved and Rejected keep exactly what was written."""
    reasons = [(e["eventType"], e["comment"]) for e in events_of(api_roles, journey[0])]
    assert reasons == [("Created", None), ("Submitted", None), ("Approved", "FPM recommends it."), ("Submitted", None), ("Rejected", "BU does not agree with the scope.")], reasons


def test_saving_the_draft_again_records_nothing(api_roles, make_draft):
    """Qase QH-API6 -- the first save records Created; later saves of the same draft record nothing."""
    qid, _ = make_draft("h6apisave", title_prefix="HU06")
    assert [e["eventType"] for e in events_of(api_roles, qid)] == ["Created"]
    for suffix in (" .", " .."):
        response = put_same_body(api_roles, qid, title=api_roles["AM"].get(f"/api/quotations/{qid}").json()["title"] + suffix)
        assert response.status_code == 200, f"{response.status_code} {response.text[:200]}"
    assert [e["eventType"] for e in events_of(api_roles, qid)] == ["Created"]


def test_a_decision_out_of_turn_records_nothing(api_roles, quotation_api, make_quotation):
    """Qase QH-API7 -- the BU decides while the turn is the FPM/FSM's: the system refuses and the history is the same."""
    qid, _ = make_quotation("h6apiturn", ["FPM", "BU"], title_prefix="HU06")
    before = events_of(api_roles, qid)
    for call in (quotation_api["BU"].approve, quotation_api["BU"].reject):
        assert call(qid, "Out of turn.").status_code >= 400
    assert events_of(api_roles, qid) == before


def test_a_rejection_without_a_reason_records_nothing(api_roles, quotation_api, make_quotation):
    """Qase QH-API8 -- a decision that the system refuses because it is incomplete leaves no event."""
    qid, _ = make_quotation("h6apinoreason", ["FPM"], title_prefix="HU06")
    before = events_of(api_roles, qid)
    assert quotation_api["FPM"].reject(qid).status_code >= 400
    assert events_of(api_roles, qid) == before and status_of(api_roles, qid) == "Awaiting"


def test_an_edit_of_an_approved_quotation_records_nothing(api_roles):
    """Qase QH-API9 -- the system refuses to edit an Approved quotation and its history is the same."""
    approved = next((i for i in api_roles["AM"].get("/api/quotations", page=1, pageSize=1, includeClosed="true").json()["items"] if i["status"] == "Approved"), None)
    if approved is None:
        pytest.skip("needs an Approved quotation of the AM")
    before = events_of(api_roles, approved["id"])
    response = put_same_body(api_roles, approved["id"])
    assert response.status_code == 400, f"{response.status_code} {response.text[:200]}"
    assert events_of(api_roles, approved["id"]) == before


def test_a_submit_of_a_quotation_that_cannot_be_submitted_records_nothing(api_roles, quotation_api, make_quotation):
    """Qase QH-API10 -- the AM sends again a quotation that already waits on its approver: the system refuses and the history is the same."""
    qid, _ = make_quotation("h6apiresubmit", ["FPM"], title_prefix="HU06")
    before = events_of(api_roles, qid)
    assert quotation_api["AM"].submit(qid).status_code >= 400
    assert events_of(api_roles, qid) == before


# ================================================================================================================ immutability
def test_two_rejections_by_the_same_approver_are_two_events(api_roles, quotation_api, make_quotation):
    """Qase QH-API11 -- the second rejection is a new event; the first one is still there with its own reason and date."""
    qid, _ = make_quotation("h6apitwice", ["FPM"], title_prefix="HU06")
    assert quotation_api["FPM"].reject(qid, "First rejection.").status_code == 200
    first = events_of(api_roles, qid)
    assert quotation_api["AM"].submit(qid).status_code == 200
    assert quotation_api["FPM"].reject(qid, "Second rejection.").status_code == 200
    after = events_of(api_roles, qid)
    assert after[:len(first)] == first
    assert [e["comment"] for e in after if e["eventType"] == "Rejected"] == ["First rejection.", "Second rejection."]


def test_a_new_submit_adds_an_event_and_changes_no_old_one(api_roles, quotation_api, make_quotation):
    """Qase QH-API12 -- after a rejection the AM sends it again: one more event, the old ones untouched."""
    qid, _ = make_quotation("h6apiadd", ["FPM"], title_prefix="HU06")
    assert quotation_api["FPM"].reject(qid, "Please check the total.").status_code == 200
    before = events_of(api_roles, qid)
    assert quotation_api["AM"].submit(qid).status_code == 200
    after = events_of(api_roles, qid)
    assert after[:len(before)] == before and [e["eventType"] for e in after[len(before):]] == ["Submitted"]


@pytest.mark.parametrize("verb", ["put", "patch", "post", "delete"])
def test_no_event_can_be_changed_or_deleted_through_the_history_path(api_roles, journey, verb):
    """Qase QH-API13 -- PUT, PATCH, POST and DELETE on the history and on one of its events are refused with HTTP 405 and nothing changes."""
    am, qid = api_roles["AM"], journey[0]
    before = events_of(api_roles, qid)
    for path in (f"/api/quotations/{qid}/events", f"/api/quotations/{qid}/events/{before[0]['id']}"):
        response = getattr(am.session, verb)(am.base_url + path, json={"comment": "changed", "eventType": "Rejected"}, timeout=60)
        assert response.status_code == 405, f"{verb.upper()} {path}: {response.status_code} {response.text[:120]}"
    assert events_of(api_roles, qid) == before


def test_the_history_of_a_quotation_cannot_be_read_without_a_login(journey):
    """Qase QH-API14 -- with no session the system answers HTTP 401."""
    from shared.config.settings import BASE_URL
    assert requests.get(f"{BASE_URL.rstrip('/')}/api/quotations/{journey[0]}/events", timeout=60).status_code == 401


def test_the_history_of_a_quotation_that_does_not_exist_is_not_found(api_roles):
    """Qase QH-API15 -- an id that no quotation has: HTTP 404."""
    assert api_roles["AM"].get(f"/api/quotations/{UNKNOWN_ID}/events").status_code == 404


@pytest.mark.parametrize("role", ["FPM", "BU", "CEO"])
def test_only_the_responsible_am_can_read_the_history_of_a_quotation(api_roles, journey, role):
    """Qase QH-API16 -- an approver of the route (FPM/FSM, BU, CEO) cannot read the history of the quotation of the AM: HTTP 403 (the history is read by the responsible AM and the ADMIN;
    fixed in the build of 2026-11-09, OP-169 / Qase #202); the AM still reads it."""
    response = api_roles[role].get(f"/api/quotations/{journey[0]}/events")
    assert response.status_code == 403, f"{role}: HTTP {response.status_code} {response.text[:200]}"
    assert api_roles["AM"].get(f"/api/quotations/{journey[0]}/events").status_code == 200
