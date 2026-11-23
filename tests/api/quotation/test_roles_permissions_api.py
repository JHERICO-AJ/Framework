"""Quotation module -- roles and permissions, database and server side (HU-25; Qase suite "HU-25: Quotation roles and permissions", cases RL-DB* and RL-API*).

Only the HU-25 text decides what must happen: each AM sees only the quotations they are responsible for; the approvers (FPM/FSM, BU, CEO) see the Pending approval list and open quotations
read-only; a user with no Quotation role gets nothing; "any action the user's role doesn't allow is rejected by the server (403, QUOTATION_FORBIDDEN), not only hidden on screen";
only the responsible AM (and ADMIN) can access a quotation's history. ADMIN is out of scope (the developer said it is future work: no requirement yet).
The second AM is the AM2 account of .env; the quotations of the "other AM" are created with it (titles start with 'Workflow Progress test HU25-'), so no real data of anyone is changed.
Observed on the QA build of 2026-10-29: the lists answer 200 only to the AM (list) or the approvers (pending-approval), 403 QUOTATION_FORBIDDEN to everyone else; the refusals of a quotation of
another AM answer 403 with a message and NO error code; the approvers on the route can read the events (history) of the AM's quotations.
"""
import pytest
import requests
from psycopg2.extras import RealDictCursor

from framework_api.services import quotation_setup as qs
from framework_api.services.quotation_service import QuotationService
from shared.config.settings import BASE_URL

pytestmark = pytest.mark.api

CLOSED = ("Approved",)          # what Historical Quotes lists; everything else (also OemRejected, back with the AM to rework) is Quotes in Progress
NOT_ALLOWED = "Not authorized for this Quotation action."
OWNER_ONLY_VIEW = "Only the responsible AM or an approver on this quotation's current route can view it."
OWNER_ONLY_EDIT = "Only the AM responsible for this quotation can edit or submit it."
REASON_NO_CODE = "Defect: the refusal answers 403 with a message but no error code; the story says 403, QUOTATION_FORBIDDEN"
SUBMIT_BODY = {"approverOverrideAcknowledged": False}


def code(r):
    try:
        return (r.json().get("details") or {}).get("code")
    except ValueError:
        return None


def forbidden(r):
    return r.status_code == 403 and code(r) == "QUOTATION_FORBIDDEN"


def put(session, quotation_id, body):
    return session.session.put(f"{session.base_url}{QuotationService.PATH}/{quotation_id}", json=body, timeout=session.timeout)


def list_all(session, path, **params):
    """Every item of a paged list (pageSize 100 is the server's maximum)."""
    items, page = [], 1
    while True:
        r = session.get(path, page=page, pageSize=100, **params)
        assert r.status_code == 200, f"{path}: {r.status_code} {r.text[:200]}"
        body = r.json()
        items += body["items"]
        if not body["hasNextPage"]:
            return items, body["totalCount"]
        page += 1


def create_payload(title):
    return {"quoteNo": "FSX00000000", **qs.CUSTOMER, "title": title, **qs.SITE, "typeOfWork": "Commissioning", "units": 0, "arrangementType": "Arrangement", "source": "MANUAL",
            "arrangement": qs.ARRANGEMENT, "attachments": [], "approvers": []}


@pytest.fixture(scope="module")
def am(api_roles):
    return api_roles["AM"]


@pytest.fixture(scope="module")
def am2(api_other):
    return api_other["AM2"]


@pytest.fixture(scope="module")
def norole(api_other):
    return api_other["NOROLE"]


@pytest.fixture(scope="module")
def am2_draft(am2, api_roles):
    """A Draft of the other AM (route FPM/FSM)."""
    return qs.create_draft(am2, api_roles, "ROLES-D", title_prefix="HU25")


@pytest.fixture(scope="module")
def am2_awaiting(am2, api_roles):
    """A quotation of the other AM waiting on FPM/FSM, then BU."""
    return qs.create_and_submit(am2, api_roles, "ROLES-A", ["FPM", "BU"], title_prefix="HU25")


@pytest.fixture(scope="module")
def am_draft(am, api_roles):
    return qs.create_draft(am, api_roles, "ROLES-AMD", title_prefix="HU25")   # not the same tag as am2_draft: two titles made in the same second were refused (HTTP 400)


def row(db_conn, quotation_id):
    with db_conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute('SELECT "EstadoCotizacion", "Version", "FechaActualizacion", "CreadoPorEmail", "Title" FROM quotation."Quotation" WHERE "Id" = %s', (quotation_id,))
        quotation = dict(cur.fetchone())
        cur.execute('SELECT COUNT(*) c FROM quotation."QuotationEvent" WHERE "QuotationId" = %s', (quotation_id,))
        quotation["events"] = cur.fetchone()["c"]
        cur.execute('SELECT "Orden", "Estado" FROM quotation."Approvers" WHERE "QuotationId" = %s ORDER BY "Orden"', (quotation_id,))
        quotation["approvers"] = [tuple(r.values()) for r in cur.fetchall()]
    return quotation


def db_ids(db_conn, where, params):
    with db_conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(f'SELECT "Id"::text id FROM quotation."Quotation" WHERE {where}', params)
        return {r["id"].lower() for r in cur.fetchall()}


# ===================================================================================================== DATABASE (RL-DB*)

@pytest.mark.parametrize("who", ["AM", "AM2"])
def test_the_counts_of_the_lists_of_an_am_are_the_quotations_of_that_am_in_the_database(who, api_roles, api_other, db_conn):
    """Qase RL-DB1 (AM) and RL-DB2 (AM2) -- Quotes in Progress and Historical Quotes hold exactly what the database says that AM is responsible for."""
    session = api_roles["AM"] if who == "AM" else api_other["AM2"]
    email = session.email.lower()
    with db_conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute('SELECT COUNT(*) FILTER (WHERE "EstadoCotizacion" NOT IN %s) open_, COUNT(*) FILTER (WHERE "EstadoCotizacion" IN %s) closed_ '
                    'FROM quotation."Quotation" WHERE lower("CreadoPorEmail") = %s', (CLOSED, CLOSED, email))
        expected = cur.fetchone()
    in_progress = session.get("/api/quotations", page=1, pageSize=1, includeClosed="false").json()["totalCount"]
    historical = session.get("/api/quotations", page=1, pageSize=1, includeClosed="true").json()["totalCount"]
    assert (in_progress, historical) == (expected["open_"], expected["closed_"])


@pytest.mark.parametrize("who", ["AM", "AM2"])
def test_no_quotation_of_another_am_is_in_the_lists_of_an_am(who, api_roles, api_other, db_conn, am2_draft, am_draft):
    """Qase RL-DB3 -- every id in both lists is one of the AM's own in the database, and every own quotation is there."""
    session = api_roles["AM"] if who == "AM" else api_other["AM2"]
    own = db_ids(db_conn, 'lower("CreadoPorEmail") = %s', (session.email.lower(),))
    seen = set()
    for closed in ("false", "true"):
        items, _ = list_all(session, "/api/quotations", includeClosed=closed)
        seen |= {str(i["id"]).lower() for i in items}
    assert seen == own, f"foreign: {len(seen - own)}, missing: {len(own - seen)}"


@pytest.mark.parametrize("role", ["FPM", "BU", "CEO"])
def test_the_pending_approval_list_is_the_quotations_that_wait_on_that_approver(role, api_roles, db_conn):
    """Qase RL-DB4 (FPM/FSM), RL-DB5 (BU), RL-DB6 (CEO) -- the list holds the quotations whose current pending approver is this user, no more and no less."""
    email = api_roles[role].email.lower()
    with db_conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute('''SELECT q."Id"::text id FROM quotation."Quotation" q WHERE q."EstadoCotizacion" = 'Awaiting' AND EXISTS (
                         SELECT 1 FROM quotation."Approvers" a WHERE a."QuotationId" = q."Id" AND lower(a."Email") = %s AND a."Estado" = 'Pending'
                           AND a."Orden" = (SELECT MIN(b."Orden") FROM quotation."Approvers" b WHERE b."QuotationId" = q."Id" AND b."Estado" = 'Pending'))''', (email,))
        expected = {r["id"].lower() for r in cur.fetchall()}
    items, total = list_all(api_roles[role], "/api/quotations/pending-approval")
    assert {str(i["id"]).lower() for i in items} == expected and total == len(expected)


def test_refused_changes_of_another_am_leave_the_database_as_it_was(am, am2_draft, am2_awaiting, db_conn):
    """Qase RL-DB7 -- status, version, date of update, number of history events and approvers of the quotations of the other AM are the same after the AM tried to change them."""
    before = {qid: row(db_conn, qid) for qid in (am2_draft[0], am2_awaiting[0])}
    for qid in before:
        put(am, qid, {"title": "HACKED by the other AM"})
        am.post(f"/api/quotations/{qid}/submit", json=SUBMIT_BODY)
        am.post(f"/api/quotations/{qid}/approve", json={"comment": "x"})
        am.post(f"/api/quotations/{qid}/reject", json={"comment": "x"})
    assert {qid: row(db_conn, qid) for qid in before} == before


@pytest.mark.parametrize("who", ["FPM", "BU", "CEO", "NOROLE"])
def test_a_refused_creation_creates_nothing_in_the_database(who, api_roles, api_other, db_conn):
    """Qase RL-DB8 -- the number of quotations is the same after a user who is not an AM tries to create one."""
    session = api_roles[who] if who in api_roles else api_other[who]
    count = lambda: len(db_ids(db_conn, "TRUE", ()))
    before = count()
    r = session.post("/api/quotations", json=create_payload(f"HU25 refused creation {who}"))
    assert forbidden(r), f"{r.status_code} {r.text[:200]}"
    assert count() == before


def test_a_quotation_belongs_to_the_am_who_created_it(am2_draft, am_draft, am, am2, db_conn):
    """Qase RL-DB9 -- the owner stored in the database is the account that created the quotation."""
    assert row(db_conn, am2_draft[0])["CreadoPorEmail"].lower() == am2.email.lower()
    assert row(db_conn, am_draft[0])["CreadoPorEmail"].lower() == am.email.lower()


def test_the_decision_of_an_approver_does_not_change_the_owner(api_roles, quotation_api, make_quotation, db_conn):
    """Qase RL-DB10 -- after the FPM/FSM edits the diagnosis and approves, the quotation is still the AM's."""
    qid, _ = make_quotation("ROLES-OWN", ["FPM"], title_prefix="HU25")
    r = quotation_api["FPM"].approve(qid, "FPM edits and approves", diagnosis={"cause": "Cause edited by the FPM/FSM", "notes": "Notes edited by the FPM/FSM"})
    assert r.status_code == 200, f"{r.status_code} {r.text[:200]}"
    assert row(db_conn, qid)["CreadoPorEmail"].lower() == api_roles["AM"].email.lower()


# ===================================================================================================== SERVER (RL-API*)

def test_the_am_cannot_use_the_pending_approval_list(am):
    """Qase RL-API1 -- 403 QUOTATION_FORBIDDEN."""
    r = am.get("/api/quotations/pending-approval", page=1, pageSize=1)
    assert forbidden(r), f"{r.status_code} {r.text[:200]}"


@pytest.mark.parametrize("who", ["FPM", "BU", "CEO", "NOROLE"])
@pytest.mark.parametrize("closed", ["false", "true"])
def test_who_is_not_an_am_cannot_use_the_lists_of_the_am(who, closed, api_roles, api_other):
    """Qase RL-API2 (FPM/FSM), RL-API3 (BU), RL-API4 (CEO), RL-API5 (no role) -- Quotes in Progress and Historical Quotes answer 403 QUOTATION_FORBIDDEN."""
    session = api_roles[who] if who in api_roles else api_other[who]
    r = session.get("/api/quotations", page=1, pageSize=1, includeClosed=closed)
    assert forbidden(r), f"{r.status_code} {r.text[:200]}"


def test_a_user_with_no_role_cannot_use_the_pending_approval_list(norole):
    """Qase RL-API6 -- 403 QUOTATION_FORBIDDEN."""
    r = norole.get("/api/quotations/pending-approval", page=1, pageSize=1)
    assert forbidden(r), f"{r.status_code} {r.text[:200]}"


@pytest.mark.parametrize("who", ["FPM", "BU", "CEO", "NOROLE"])
def test_who_is_not_an_am_cannot_create_save_or_submit_a_quotation(who, api_roles, api_other, am_draft):
    """Qase RL-API7 (FPM/FSM), RL-API8 (BU), RL-API9 (CEO), RL-API10 (no role) -- create, save (PUT) and submit answer 403 QUOTATION_FORBIDDEN."""
    session = api_roles[who] if who in api_roles else api_other[who]
    body = api_roles["AM"].get(f"/api/quotations/{am_draft[0]}").json()
    answers = {"create": session.post("/api/quotations", json=create_payload(f"HU25 refused {who}")), "save": put(session, am_draft[0], body),
               "submit": session.post(f"/api/quotations/{am_draft[0]}/submit", json=SUBMIT_BODY)}
    assert all(forbidden(r) for r in answers.values()), {k: (r.status_code, code(r)) for k, r in answers.items()}


def test_a_user_with_no_role_cannot_approve_or_reject(norole, am2_awaiting):
    """Qase RL-API11 -- 403 QUOTATION_FORBIDDEN for both decisions."""
    for action in ("approve", "reject"):
        r = norole.post(f"/api/quotations/{am2_awaiting[0]}/{action}", json={"comment": "x"})
        assert forbidden(r), f"{action}: {r.status_code} {r.text[:200]}"


def test_an_am_cannot_approve_or_reject_not_even_the_own_quotation(am, make_quotation):
    """Qase RL-API12 -- 403 QUOTATION_FORBIDDEN, on a quotation of the AM that waits on an approver."""
    qid, _ = make_quotation("ROLES-AMOWN", ["FPM"], title_prefix="HU25")
    for action in ("approve", "reject"):
        r = am.post(f"/api/quotations/{qid}/{action}", json={"comment": "x"})
        assert forbidden(r), f"{action}: {r.status_code} {r.text[:200]}"


@pytest.mark.parametrize("who", ["AM", "NOROLE", "CEO"])
@pytest.mark.parametrize("which", ["draft", "awaiting"])
def test_whoever_is_not_the_owner_or_on_the_route_cannot_read_a_quotation(who, which, api_roles, api_other, am2_draft, am2_awaiting):
    """Qase RL-API13 (other AM), RL-API14 (no role), RL-API15 (CEO, not on the route) -- 403 and not a single field of the quotation in the answer."""
    session = api_roles[who] if who in api_roles else api_other[who]
    qid = (am2_draft if which == "draft" else am2_awaiting)[0]
    r = session.get(f"/api/quotations/{qid}")
    assert r.status_code == 403 and r.json().get("message") == OWNER_ONLY_VIEW, f"{r.status_code} {r.text[:200]}"
    assert not ({"title", "quoteNo", "approvers", "arrangement"} & set(r.json()))


@pytest.mark.parametrize("what", ["read", "history", "save", "submit"])
def test_the_refusals_for_a_quotation_of_another_am_carry_the_error_code_of_the_story(what, am, am2_draft):
    """Qase RL-API16 -- read, history, save and submit of a quotation of another AM: 403 and the code QUOTATION_FORBIDDEN of the story."""
    qid = am2_draft[0]
    r = {"read": lambda: am.get(f"/api/quotations/{qid}"), "history": lambda: am.get(f"/api/quotations/{qid}/events"), "save": lambda: put(am, qid, {"title": "x"}),
         "submit": lambda: am.post(f"/api/quotations/{qid}/submit", json=SUBMIT_BODY)}[what]()
    assert forbidden(r), f"{r.status_code} {r.text[:200]}"


def test_the_other_am_cannot_save_or_submit_a_quotation_of_the_am(am2, am_draft):
    """Qase RL-API17 -- the second AM tries the quotations of the first (the same refusal in the other direction): 403 and the quotation does not change."""
    body = am2.get(f"/api/quotations/{am_draft[0]}")
    assert body.status_code == 403
    assert put(am2, am_draft[0], {"title": "HACKED by AM2"}).status_code == 403
    assert am2.post(f"/api/quotations/{am_draft[0]}/submit", json=SUBMIT_BODY).status_code == 403


def test_an_am_cannot_save_or_submit_a_quotation_of_another_am(am, am2_draft, am2_awaiting):
    """Qase RL-API18 -- 403 for save and submit, on a Draft and on a quotation that waits on an approver."""
    for qid in (am2_draft[0], am2_awaiting[0]):
        assert put(am, qid, {"title": "HACKED"}).status_code == 403
        assert am.post(f"/api/quotations/{qid}/submit", json=SUBMIT_BODY).status_code == 403


def test_an_am_cannot_approve_or_reject_a_quotation_of_another_am(am, am2_awaiting):
    """Qase RL-API19 -- 403 QUOTATION_FORBIDDEN."""
    for action in ("approve", "reject"):
        r = am.post(f"/api/quotations/{am2_awaiting[0]}/{action}", json={"comment": "x"})
        assert forbidden(r), f"{action}: {r.status_code} {r.text[:200]}"


def test_an_approver_on_the_route_can_read_but_not_change_the_quotation(api_roles, am2_awaiting):
    """Qase RL-API20 -- the FPM/FSM and the BU of the route read the quotation (200) and cannot save it (403 QUOTATION_FORBIDDEN), also when it is not their turn."""
    for role in ("FPM", "BU"):
        s = api_roles[role]
        assert s.get(f"/api/quotations/{am2_awaiting[0]}").status_code == 200
        r = put(s, am2_awaiting[0], {"title": "x"})
        assert forbidden(r), f"{role}: {r.status_code} {r.text[:200]}"


def test_an_approver_out_of_turn_cannot_decide(api_roles, am2_awaiting):
    """Qase RL-API21 -- the BU of the route, while the FPM/FSM is the one pending, and the CEO, who is not on the route: 400 NOT_CURRENT_APPROVER (the decision rule of HU-22)."""
    for role in ("BU", "CEO"):
        r = api_roles[role].post(f"/api/quotations/{am2_awaiting[0]}/approve", json={"comment": "x"})
        assert r.status_code == 400 and code(r) == "NOT_CURRENT_APPROVER", f"{role}: {r.status_code} {r.text[:200]}"


def test_the_pending_approval_list_holds_only_quotations_where_the_approver_is_on_the_route(api_roles, am2_awaiting):
    """Qase RL-API22 -- every quotation of the FPM/FSM list can be read by that FPM/FSM (200) and has the approver in its route."""
    s = api_roles["FPM"]
    items, _ = list_all(s, "/api/quotations/pending-approval")
    for item in items[:10]:
        body = s.get(f"/api/quotations/{item['id']}")
        assert body.status_code == 200
        assert s.email.lower() in [(a.get("email") or "").lower() for a in body.json()["approvers"]]


@pytest.mark.parametrize("role", ["FPM", "BU"])
def test_the_approvers_cannot_read_the_history_of_a_quotation(role, api_roles, am2_awaiting):
    """Qase RL-API23 (FPM/FSM), RL-API24 (BU) -- 'Only the responsible AM and ADMIN can access a quotation's history': 403 for an approver."""
    r = api_roles[role].get(f"/api/quotations/{am2_awaiting[0]}/events")
    assert r.status_code == 403, f"{r.status_code} {r.text[:120]}"


def test_the_responsible_am_can_read_the_history(am2, am2_awaiting):
    """Qase RL-API25 -- the AM of the quotation reads its history (200) and it starts with Created."""
    r = am2.get(f"/api/quotations/{am2_awaiting[0]}/events")
    assert r.status_code == 200 and r.json()[0]["eventType"] == "Created"


def test_the_other_am_and_the_users_with_no_role_cannot_read_the_history(am, norole, am2_awaiting):
    """Qase RL-API26 -- 403 for the other AM and for a user with no role."""
    for s in (am, norole):
        assert s.get(f"/api/quotations/{am2_awaiting[0]}/events").status_code == 403


def test_searching_for_the_number_of_another_am_finds_nothing(am, am2_draft):
    """Qase RL-API27 -- the search of both lists with the Quote # of a quotation of the other AM returns no row."""
    for closed in ("false", "true"):
        r = am.get("/api/quotations", page=1, pageSize=10, includeClosed=closed, search=am2_draft[1])
        assert r.status_code == 200 and r.json()["totalCount"] == 0, f"includeClosed={closed}: {r.text[:200]}"


@pytest.mark.parametrize("call", ["list", "pending", "create", "get", "approve"])
def test_without_a_login_every_call_answers_401(call, am2_draft):
    """Qase RL-API28 -- no session: 401 for the lists, the creation, the reading and the decision."""
    base = BASE_URL.rstrip("/")
    r = {"list": lambda: requests.get(f"{base}/api/quotations", params={"page": 1, "pageSize": 1}, timeout=60),
         "pending": lambda: requests.get(f"{base}/api/quotations/pending-approval", params={"page": 1, "pageSize": 1}, timeout=60),
         "create": lambda: requests.post(f"{base}/api/quotations", json=create_payload("HU25 no login"), timeout=60),
         "get": lambda: requests.get(f"{base}/api/quotations/{am2_draft[0]}", timeout=60),
         "approve": lambda: requests.post(f"{base}/api/quotations/{am2_draft[0]}/approve", json={"comment": "x"}, timeout=60)}[call]()
    assert r.status_code == 401


@pytest.mark.parametrize("who", ["FPM", "NOROLE"])
def test_the_refusal_has_the_shape_of_the_other_errors_and_no_data(who, api_roles, api_other):
    """Qase RL-API29 -- the 403 body has statusCode, message, details.code and traceId, and says nothing about quotations."""
    session = api_roles[who] if who in api_roles else api_other[who]
    r = session.get("/api/quotations", page=1, pageSize=1)
    body = r.json()
    assert r.status_code == 403 and {"statusCode", "message", "details", "traceId"} <= set(body) and body["message"] == NOT_ALLOWED
    assert "items" not in body


@pytest.mark.parametrize("call", ["filter-options", "next-quote-number"])
def test_a_user_with_no_role_cannot_use_the_helpers_of_the_module(call, norole):
    """Qase RL-API30 -- the filter lists and the next Quote # are refused (403 QUOTATION_FORBIDDEN) to a user with no Quotation role."""
    r = norole.get(f"/api/quotations/{call}", **({"customerId": 6, "customerName": "Andes Renewables SpA"} if call == "next-quote-number" else {}))
    assert forbidden(r), f"{r.status_code} {r.text[:120]}"


def test_the_filter_options_hold_only_values_of_the_quotations_the_user_can_see(am, norole):
    """Qase RL-API31 -- the OEMs and sites offered to a user with no role are not more than the AM's own."""
    own = am.get("/api/quotations/filter-options").json()
    other = norole.get("/api/quotations/filter-options")
    assert other.status_code != 200 or (len(other.json()["oems"]) <= len(own["oems"]) and len(other.json()["siteNames"]) <= len(own["siteNames"]))


# ===================================================================================================== what the AM can do (positive cases)

def test_the_am_can_create_a_draft_quotation(am, am_draft):
    """Qase RL-API32 -- the AM creates a quotation: it is a Draft and the AM can read it."""
    r = am.get(f"/api/quotations/{am_draft[0]}")
    assert r.status_code == 200 and r.json()["status"] == "Draft"


def test_the_am_can_save_a_draft(am, api_roles):
    """Qase RL-API33 -- the AM saves a Draft with a new title (PUT, 200) and reads the new title."""
    qid, _ = qs.create_draft(am, api_roles, "ROLES-SAVE", title_prefix="HU25")
    body = am.get(f"/api/quotations/{qid}").json()
    body["title"] = "Workflow Progress test HU25-ROLES-SAVE edited"
    assert put(am, qid, body).status_code == 200
    assert am.get(f"/api/quotations/{qid}").json()["title"] == body["title"]


def test_the_am_can_submit_a_quotation(am, api_roles):
    """Qase RL-API34 -- the AM submits a Draft (200) and it waits on the approver."""
    qid, _ = qs.create_and_submit(am, api_roles, "ROLES-SUBMIT", ["FPM"], title_prefix="HU25")
    assert am.get(f"/api/quotations/{qid}").json()["status"] == "Awaiting"


def test_the_am_finds_the_own_quotation_in_the_list(am, am_draft):
    """Qase RL-API35 -- searching the Quote # of an own quotation returns exactly that quotation in Quotes in Progress."""
    r = am.get("/api/quotations", page=1, pageSize=10, includeClosed="false", search=am_draft[1])
    assert r.status_code == 200 and [str(i["id"]).lower() for i in r.json()["items"]] == [am_draft[0].lower()]


@pytest.mark.parametrize("role", ["FPM", "BU", "CEO"])
def test_each_approver_can_approve_and_reject_when_it_is_their_turn(role, make_quotation, quotation_api):
    """Qase RL-API36 (FPM/FSM), RL-API37 (BU), RL-API38 (CEO) -- on their turn the approver approves one quotation and rejects another (200 each)."""
    approved, _ = make_quotation(f"ROLES-OK{role}", [role], title_prefix="HU25")
    rejected, _ = make_quotation(f"ROLES-NO{role}", [role], title_prefix="HU25")
    ok = quotation_api[role].approve(approved, "Approved with my role.")
    no = quotation_api[role].reject(rejected, "Rejected with my role.")
    assert (ok.status_code, no.status_code) == (200, 200), f"{ok.status_code} {ok.text[:120]} | {no.status_code} {no.text[:120]}"


def test_the_second_am_can_create_save_and_submit_own_quotations(am2, api_roles):
    """Qase RL-API39 -- the second AM does what the first one does: creates a Draft, saves it and submits another (200) and finds it in the own list."""
    draft, no = qs.create_draft(am2, api_roles, "ROLES-AM2OWN", title_prefix="HU25")
    body = am2.get(f"/api/quotations/{draft}").json()
    body["title"] = "Workflow Progress test HU25-ROLES-AM2OWN edited"
    assert put(am2, draft, body).status_code == 200
    sent, _ = qs.create_and_submit(am2, api_roles, "ROLES-AM2SENT", ["FPM"], title_prefix="HU25")
    assert am2.get(f"/api/quotations/{sent}").json()["status"] == "Awaiting"
    r = am2.get("/api/quotations", page=1, pageSize=10, includeClosed="false", search=no)
    assert [str(i["id"]).lower() for i in r.json()["items"]] == [draft.lower()]


# ------------------------------------------------------------------------------------------------ an approver on the route and a Draft (developer answer of 2026-11-05)
# The rule is "the responsible AM or somebody in the list of approvers of the quotation", not a special privilege of the FPM/FSM: the AM can add the approvers before submitting.

@pytest.fixture(scope="module")
def draft_with_bu_route(am, api_roles):
    """A Draft of the AM whose only approver is the BU (the FPM/FSM is NOT on the route)."""
    return qs.create_and_submit(am, api_roles, "ROLES-DBU", ["BU"], title_prefix="HU25", submit=False)


def test_the_fpm_on_the_route_can_read_a_draft_of_the_am(api_roles, am_draft):
    """Qase RL-API40 -- the FPM/FSM approver who is in the route of a Draft reads it (200, status Draft)."""
    r = api_roles["FPM"].get(f"/api/quotations/{am_draft[0]}")
    assert r.status_code == 200 and r.json()["status"] == "Draft", f"{r.status_code} {r.text[:200]}"


def test_the_fpm_on_the_route_cannot_change_or_submit_a_draft_of_the_am(api_roles, am_draft):
    """Qase RL-API41 -- reading is all the FPM/FSM can do with a Draft: save and submit are refused (403) and nothing changes."""
    fpm = api_roles["FPM"]
    body = api_roles["AM"].get(f"/api/quotations/{am_draft[0]}").json()
    assert put(fpm, am_draft[0], {**body, "title": "CHANGED by the FPM"}).status_code == 403
    assert fpm.post(f"/api/quotations/{am_draft[0]}/submit", json=SUBMIT_BODY).status_code == 403
    assert api_roles["AM"].get(f"/api/quotations/{am_draft[0]}").json()["title"] == body["title"]


def test_the_fpm_not_on_the_route_cannot_read_a_draft_of_the_am(api_roles, draft_with_bu_route):
    """Qase RL-API42 -- the route of this Draft is only the BU: the FPM/FSM is refused (403) and not a field of the quotation is in the answer."""
    r = api_roles["FPM"].get(f"/api/quotations/{draft_with_bu_route[0]}")
    assert r.status_code == 403 and r.json().get("message") == OWNER_ONLY_VIEW, f"{r.status_code} {r.text[:200]}"
    assert not ({"title", "quoteNo", "approvers", "arrangement"} & set(r.json()))
