"""Quotation module -- Historical Quotes, server side (OP-12 / HU-05; Qase suite "HU-05: Quotation history view and filtering", cases HQ-API*).

Only the HU-05 text decides what must happen. The system answers (observed on the QA build of 2026-10-26):
  GET /api/quotations?page=&pageSize=&includeClosed=true|false&oemName=&siteName=&typeOfWork=&search=   -> {items, totalCount, pageNumber, pageSize, totalPages, hasPreviousPage, hasNextPage}
      includeClosed=true is the Historical Quotes tab (the quotations in a final status), false is "Quotes in Progress"
  GET /api/quotations/filter-options -> {oems, siteNames, typeOfWork, workflowStages, statuses, sources}
A request for the historical list by a user who is not the AM is refused with HTTP 403 (QUOTATION_FORBIDDEN).
Not testable here: the status "Closed" (nothing can produce it), the limit of 300 characters (it is a rule of the search box: the system accepts longer text), and the data that does not
exist (Alarm ID, device, more than ten historical quotations): those tests are skipped with the reason.
Every expectation is read from the API as the same user, never hard-coded.
"""
import pytest

from framework_api.client.role_session import RoleApiSession
from shared.config.credentials import load_role_credentials

pytestmark = pytest.mark.api

FINAL = {"Approved", "Closed"}
SHAPE = {"items", "totalCount", "pageNumber", "pageSize", "totalPages", "hasPreviousPage", "hasNextPage"}


def listing(session, closed, page=1, page_size=10, **params):
    return session.get("/api/quotations", page=page, pageSize=page_size, includeClosed="true" if closed else "false", **params)


def ok(session, closed, **params):
    response = listing(session, closed, **params)
    assert response.status_code == 200, f"{response.status_code} {response.text[:200]}"
    return response.json()


def everything(session, closed, **params):
    items, page = [], 1
    while True:
        data = ok(session, closed, page=page, page_size=100, **params)
        items += data["items"]
        if not data["hasNextPage"]:
            return items
        page += 1


def numbers(data):
    return [item["quoteNo"] for item in data["items"]]


@pytest.fixture(scope="module")
def am(api_roles):
    return api_roles["AM"]


@pytest.fixture(scope="module")
def historical_items(am):
    items = everything(am, True)
    if not items:
        pytest.skip("the AM has no historical quotation")
    return items


# ================================================================================================================ permissions
@pytest.mark.parametrize("role", ["FPM", "BU", "CEO"])
def test_an_approver_asking_for_the_historical_list_is_refused(api_roles, role):
    """Qase HQ-API1 (FPM/FSM), HQ-API2 (BU), HQ-API3 (CEO) -- HTTP 403 forbidden."""
    response = listing(api_roles[role], True)
    assert response.status_code == 403 and (response.json().get("details") or {}).get("code") == "QUOTATION_FORBIDDEN", f"{response.status_code} {response.text[:200]}"


def test_a_user_without_a_quotation_role_asking_for_the_historical_list_is_refused():
    """Qase HQ-API4 -- HTTP 403 forbidden."""
    credentials = load_role_credentials("NOROLE")
    if credentials is None:
        pytest.skip("QUOTATION_NOROLE_* not set in .env")
    response = listing(RoleApiSession(credentials["email"], credentials["password"]), True)
    assert response.status_code == 403 and (response.json().get("details") or {}).get("code") == "QUOTATION_FORBIDDEN", f"{response.status_code} {response.text[:200]}"


def test_the_am_gets_the_historical_list(am):
    """Qase HQ-API5 -- HTTP 200 with the list."""
    assert listing(am, True).status_code == 200


# ================================================================================================================ content
def test_the_historical_list_has_only_quotations_in_a_final_status(historical_items):
    """Qase HQ-API6 -- Approved or Closed, nothing else."""
    assert {item["status"] for item in historical_items} <= FINAL, {item["status"] for item in historical_items}


def test_the_quotations_in_progress_are_not_in_a_final_status_and_none_is_in_both_lists(am, historical_items):
    """Qase HQ-API7 -- Draft, Awaiting, Returned, Rejected and OEM Rejected stay in progress; no quotation is in both lists."""
    in_progress = everything(am, False)
    assert {item["status"] for item in in_progress}.isdisjoint(FINAL), {item["status"] for item in in_progress}
    assert {item["status"] for item in in_progress} <= {"Draft", "Awaiting", "Returned", "Rejected", "OemRejected"}
    assert {item["quoteNo"] for item in in_progress}.isdisjoint({item["quoteNo"] for item in historical_items})


def test_the_answer_has_the_paging_data(am):
    """Qase HQ-API8 -- items, totalCount, pageNumber, pageSize, totalPages, hasPreviousPage and hasNextPage, coherent with each other."""
    data = ok(am, True)
    assert SHAPE <= set(data), set(data)
    assert data["pageNumber"] == 1 and data["pageSize"] == 10 and len(data["items"]) == min(10, data["totalCount"])
    assert data["totalPages"] == -(-data["totalCount"] // 10) and data["hasPreviousPage"] is False and data["hasNextPage"] is (data["totalPages"] > 1)


def test_the_quotations_are_sorted_by_creation_date_most_recent_first(am, historical_items):
    """Qase HQ-API9 -- the list follows the creation date, newest first."""
    created = [item["createdAt"] for item in historical_items]
    assert created == sorted(created, reverse=True)


def test_an_approved_quotation_has_no_one_waiting_and_the_step_ready_for_client(historical_items):
    """Qase HQ-API10 -- no 'waiting on', workflowStage 'Ready for Client' and status 'Approved'."""
    approved = [item for item in historical_items if item["status"] == "Approved"]
    if not approved:
        pytest.skip("the AM has no Approved quotation")
    for item in approved:
        assert (item["waitingOnName"], item["waitingOnRole"], item["workflowStage"]) == (None, None, "Ready for Client"), item["quoteNo"]


def test_the_pages_of_the_historical_list_fit_together(am, historical_items):
    """Qase HQ-API11 -- with small pages, every page has the right size and the pages together are the whole list, and a page after the last one is empty."""
    pages, number = [], 1
    while True:
        data = ok(am, True, page=number, page_size=2)
        pages.append(data)
        assert data["hasPreviousPage"] is (number > 1)
        if not data["hasNextPage"]:
            break
        assert len(data["items"]) == 2
        number += 1
    assert [q for data in pages for q in numbers(data)] == [item["quoteNo"] for item in historical_items]
    assert ok(am, True, page=number + 1, page_size=2)["items"] == []



def test_the_system_refuses_to_edit_an_approved_quotation_and_leaves_it_as_it_was(am, historical_items):
    """Qase HQ-API27 -- an edit of an Approved quotation (the same data it already has) is refused with HTTP 400 QUOTATION_NOT_EDITABLE and nothing changes.
    It sends a real edit: if the system ever accepted it, the quotation would be touched, which is what this test would then report."""
    approved = next((item for item in historical_items if item["status"] == "Approved"), None)
    if approved is None:
        pytest.skip("the AM has no Approved quotation")
    before = am.get(f"/api/quotations/{approved['id']}").json()
    response = am.session.put(f"{am.base_url}/api/quotations/{approved['id']}", json=before, timeout=max(am.timeout, 90))
    after = am.get(f"/api/quotations/{approved['id']}").json()
    assert response.status_code == 400 and response.json()["details"]["code"] == "QUOTATION_NOT_EDITABLE", f"{response.status_code} {response.text[:200]}"
    assert (after["status"], after["workflowStage"], after["updatedAt"]) == (before["status"], before["workflowStage"], before["updatedAt"])


def test_the_refused_edit_of_an_approved_quotation_leaves_its_database_row_as_it_was(am, historical_items, db_conn):
    """Qase HQ-API28 -- the same refused edit, read straight from the database (read-only) before and after: status, stage, total and date of the last update do not change."""
    from shared.datasource import quotation_db_source as quotation_db
    approved = next((item for item in historical_items if item["status"] == "Approved"), None)
    if approved is None:
        pytest.skip("the AM has no Approved quotation")
    before_row = quotation_db.get_quotation_audit_fields(db_conn, approved["quoteNo"])
    body = am.get(f"/api/quotations/{approved['id']}").json()
    response = am.session.put(f"{am.base_url}/api/quotations/{approved['id']}", json=body, timeout=max(am.timeout, 90))
    db_conn.rollback()                     # a fresh view of the data for the second read (the connection is read-only)
    after_row = quotation_db.get_quotation_audit_fields(db_conn, approved["quoteNo"])
    assert response.status_code == 400, f"{response.status_code} {response.text[:200]}"
    assert before_row is not None and after_row == before_row, (before_row, after_row)


# ================================================================================================================ filters
@pytest.mark.parametrize("param,field", [("oemName", "oemName"), ("siteName", "siteName"), ("typeOfWork", "typeOfWork")])
def test_each_filter_returns_only_the_quotations_with_that_value(am, historical_items, param, field):
    """Qase HQ-API12 (OEM), HQ-API13 (Site), HQ-API14 (Type of Work) -- only the matching ones; a value nobody has gives an empty list."""
    for value in {item[field] for item in historical_items if item.get(field)}:
        expected = [item["quoteNo"] for item in historical_items if item.get(field) == value]
        assert sorted(numbers(ok(am, True, page_size=100, **{param: value}))) == sorted(expected), (param, value)
    assert ok(am, True, **{param: "no such value"})["items"] == []


def test_the_filters_combine_with_each_other_and_with_the_search(am, historical_items):
    """Qase HQ-API15 -- OEM, Site, Type of Work and search together keep only what matches all of them."""
    item = historical_items[0]
    params = {name: item[field] for name, field in (("oemName", "oemName"), ("siteName", "siteName"), ("typeOfWork", "typeOfWork")) if item.get(field)}
    term = item["title"].split()[0]
    expected = [i["quoteNo"] for i in historical_items if all(i.get(f) == v for f, v in [(name, params[name]) for name in params]) and term.lower() in i["title"].lower()]
    assert sorted(numbers(ok(am, True, page_size=100, search=term, **params))) == sorted(expected)
    assert item["quoteNo"] in expected


# ================================================================================================================ search
def search(am, term, **params):
    return ok(am, True, page_size=100, search=term, **params)


@pytest.mark.parametrize("field,piece", [("title", lambda v: v[3:11].upper()), ("quoteNo", lambda v: v[2:9].lower()), ("gsp", lambda v: v[1:9].lower()),
                                          ("siteName", lambda v: v[1:5].upper()), ("device", lambda v: v[1:5].lower())])
def test_the_search_matches_part_of_each_field_ignoring_case(am, historical_items, field, piece):
    """Qase HQ-API16 (WO Title), 17 (Quote #), 18 (GSP #), 19 (Site), 20 (Device) -- a piece of the value in another case finds the quotation."""
    item = next((i for i in historical_items if i.get(field)), None)
    if item is None:
        pytest.skip(f"no historical quotation has a {field}")
    assert item["quoteNo"] in numbers(search(am, piece(item[field])))


@pytest.mark.skip(reason="OUT OF SCOPE: AC25 of HU-05 says the Alarm ID logic is discarded ('Quotation is no longer linked to Alarms'); the case is deprecated in Qase")
def test_the_search_matches_the_start_of_the_alarm_id_from_its_first_eight_characters_and_not_less(am, historical_items):
    """Qase HQ-API21 -- 8 characters (any case) find it; 7 do not."""
    item = next((i for i in historical_items if i.get("alarmId")), None)
    if item is None:
        pytest.skip("no historical quotation was created from an alarm")
    assert item["quoteNo"] in numbers(search(am, item["alarmId"][:8])) and item["quoteNo"] in numbers(search(am, item["alarmId"][:8].upper()))
    assert item["quoteNo"] not in numbers(search(am, item["alarmId"][:7]))


def test_spaces_at_the_start_and_the_end_are_ignored(am, historical_items):
    """Qase HQ-API22 -- '  term  ' gives the same list as 'term'."""
    term = historical_items[0]["quoteNo"]
    assert numbers(search(am, f"   {term}   ")) == numbers(search(am, term)) and term in numbers(search(am, term))


@pytest.mark.parametrize("text", ["", "     "])
def test_an_empty_search_returns_every_historical_quotation(am, historical_items, text):
    """Qase HQ-API23 (empty) and HQ-API24 (only spaces) -- the whole list."""
    assert sorted(numbers(ok(am, True, page_size=100, search=text))) == sorted(item["quoteNo"] for item in historical_items)


@pytest.mark.parametrize("text", ["<b>x</b>", "<script>alert(1)</script>", "'; DROP TABLE quotations; --", "' OR '1'='1", "%", "_", "\\"])
def test_the_search_text_is_plain_text(am, historical_items, text):
    """Qase HQ-API25 -- HTML, script, SQL-like text and the symbols % and _ are plain text: no error, no result (they are not wildcards), and the list still answers afterwards."""
    data = ok(am, True, page_size=100, search=text)
    assert data["items"] == [] and data["totalCount"] == 0
    assert len(ok(am, True)["items"]) > 0


def test_the_filter_options_hold_the_values_of_all_the_quotations(am, historical_items):
    """Qase HQ-API26 -- OEMs, sites and types of work of the quotations in progress and of the historical ones."""
    response = am.get("/api/quotations/filter-options")
    assert response.status_code == 200
    options = response.json()
    every = everything(am, False) + historical_items
    for key, field in (("oems", "oemName"), ("siteNames", "siteName"), ("typeOfWork", "typeOfWork")):
        assert {value.strip() for value in options[key]} >= {item[field].strip() for item in every if item.get(field)}, key
