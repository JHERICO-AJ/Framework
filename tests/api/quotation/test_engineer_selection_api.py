"""HU-11 (OP-29) ENGINEER SELECTION MAP -- what the SERVER does with the employee catalog and with the external contractors added from the map, calling the API
directly (no screen), signed in as the AM.

Added 2026-11-09 for the regression of Sprint 1 (HU-11 had only screen tests until then). Probe of 2026-11-09 on the QA build:
  * the employee catalog (GET /api/amxcpcatalog/employees) answers with 53 records with their location (latitude/longitude): plain tests below;
  * an external contractor (isContractor) is saved and comes back exactly as sent, and the server limits each field to the size of its column (name 200, location 200,
    phone 50, email 300; the screen is stricter: 100 / 120 / 30): plain tests below;
  * the server does NOT clean what the screen cleans: it keeps <script> tags in the contractor name, emoji in the name, and letters/emoji in the phone. Strict xfail tests
    with the reason written out (same convention as test_fse_select_api.py: when the server is fixed the test turns into an unexpected pass and fails, so the xfail
    mark has to be removed). Same pattern as HU-09 #213.
The tests create their own Draft quotations (title prefix HU11-API) and never touch anyone else's. Qase suite 48: the case ids are in the docstrings."""
import pytest

from framework_api.services import quotation_setup as qs

pytestmark = pytest.mark.api

OK = 200
E = list(qs.ENGINEERS)


def _extra():
    return qs.select_extra(*[(E[i], qs.engineer_cost("quotation", 50, 8), qs.engineer_cost("expense", 30, 8)) for i in range(2)])


def _contractor(**overrides):
    return dict(dict(isContractor=True, isLeader=False, contractorName="Ext Contractor", contractorPhone="+591 700 12345", contractorEmail="",
                     contractorLocation="La Paz", availabilityStatus="available", costs=[]), **overrides)


def _body(am, quotation_id):
    return am.get(f"/api/quotations/{quotation_id}").json()


def _add(am, quotation_id, contractor):
    """Adds the contractor to the selection and saves. Returns (response, the engineers the server sends back)."""
    body = _body(am, quotation_id)
    body["select"]["selectedEngineers"] = body["select"]["selectedEngineers"][:2] + [contractor]
    response = am.session.put(f"{am.base_url}/api/quotations/{quotation_id}", json=body, timeout=90)
    return response, _body(am, quotation_id)["select"]["selectedEngineers"]


@pytest.fixture(scope="module")
def draft(api_roles, make_draft):
    """One Draft of the AM with 2 engineers; every test puts one contractor in it and takes it out again (the quotation stays a Draft)."""
    quotation_id, _ = make_draft("ENGSEL", title_prefix="HU11-API", extra=_extra())
    return quotation_id


@pytest.fixture(autouse=True)
def _back_to_two_engineers(api_roles, draft):
    yield
    am = api_roles["AM"]
    body = _body(am, draft)
    body["select"]["selectedEngineers"] = body["select"]["selectedEngineers"][:2]
    am.session.put(f"{am.base_url}/api/quotations/{draft}", json=body, timeout=90)


# ---- Employee catalog (Qase #899, #900, #906, #907) ---------------------------------------------------------------------------------------
def test_the_employee_catalog_lists_the_candidates_with_their_location(api_roles):
    """Qase #899 / #900: the catalog the map reads answers 200 with the employees; each one has the name, email, phone, company and the coordinates the map needs."""
    response = api_roles["AM"].get("/api/amxcpcatalog/employees")
    assert response.status_code == OK
    employees = response.json()
    assert isinstance(employees, list) and len(employees) >= 1
    for employee in employees:
        assert employee["employeeId"] and employee["name"] and employee["email"], employee
    # Observed 2026-11-09: 3 of the 53 records (the generated GoldenMax employees gen-g01000/g01100/g01200) have no coordinates, so they cannot be drawn on the map.
    located = [e for e in employees if e["latitude"] is not None and e["longitude"] is not None]
    assert len(located) >= len(employees) - 3 and all(isinstance(e["latitude"], (int, float)) and isinstance(e["longitude"], (int, float)) for e in located)


def test_the_employee_catalog_has_no_repeated_employee(api_roles):
    """Qase #906: the candidate pool is built from the catalog; an employee must not come twice."""
    ids = [e["employeeId"] for e in api_roles["AM"].get("/api/amxcpcatalog/employees").json()]
    assert len(ids) == len(set(ids))


# ---- External contractor (Qase #904, #909, #910) ------------------------------------------------------------------------------------------
def test_an_external_contractor_is_saved_as_sent(api_roles, draft):
    """Qase #904: the contractor added from the map comes back as a contractor with the name, phone and location that were sent."""
    response, engineers = _add(api_roles["AM"], draft, _contractor())
    assert response.status_code == OK
    saved = engineers[-1]
    assert (saved["isContractor"], saved["contractorName"], saved["contractorPhone"], saved["contractorLocation"]) == (True, "Ext Contractor", "+591 700 12345", "La Paz")
    assert [e["isContractor"] for e in engineers] == [False, False, True] and sum(e["isLeader"] for e in engineers) == 1


@pytest.mark.parametrize("field, limit", [("contractorName", 200), ("contractorLocation", 200), ("contractorPhone", 50), ("contractorEmail", 300)])
def test_each_contractor_field_accepts_its_maximum_and_rejects_one_more(api_roles, draft, field, limit):
    """Qase #910: the server holds the size of each column (name 200, location 200, phone 50, email 300) with an HTTP 400 and the field in the message.
    The screen stops earlier (100 / 120 / 30), that part is tested in the screen suite."""
    def value(n):
        return "1" * n if field == "contractorPhone" else (("a" * (n - 12)) + "@example.com" if field == "contractorEmail" else "A" * n)
    ok, engineers = _add(api_roles["AM"], draft, _contractor(**{field: value(limit)}))
    assert ok.status_code == OK and len(engineers[-1][field]) == limit
    over, _ = _add(api_roles["AM"], draft, _contractor(**{field: value(limit + 1)}))
    assert over.status_code == 400 and field in over.text, f"{field} with {limit + 1}: {over.status_code} {over.text[:150]}"


def test_sql_looking_text_is_stored_as_plain_text(api_roles, draft):
    """Qase #909: a text that looks like SQL is kept literally (the server does not run it, the table is still there)."""
    text = "x'; DROP TABLE a;--"
    response, engineers = _add(api_roles["AM"], draft, _contractor(contractorLocation=text))
    assert response.status_code == OK and engineers[-1]["contractorLocation"] == text
    assert api_roles["AM"].get(f"/api/quotations/{draft}").status_code == OK


# ---- Findings: what the screen cleans and the server does not --------------------------------------------------------------------------------
# Qase #219 (OP-186): FIXED, verified 2026-11-19 (before, the server saved angle brackets, emoji and letters in the contractor fields; now it cleans them).
@pytest.mark.parametrize("field", ["contractorName", "contractorLocation"])
def test_the_server_removes_the_angle_brackets_of_a_contractor(api_roles, draft, field):
    response, engineers = _add(api_roles["AM"], draft, _contractor(**{field: "<script>alert(1)</script>"}))
    assert response.status_code == 400 or ("<" not in engineers[-1][field] and ">" not in engineers[-1][field]), f"saved as {engineers[-1][field]!r}"


# Qase #219 (OP-186): FIXED, verified 2026-11-19 (before, the server saved angle brackets, emoji and letters in the contractor fields; now it cleans them).
def test_the_server_rejects_emoji_in_the_contractor_name(api_roles, draft):
    response, engineers = _add(api_roles["AM"], draft, _contractor(contractorName="\U0001F4DE Juan"))
    assert response.status_code == 400 or "\U0001F4DE" not in engineers[-1]["contractorName"], f"saved as {ascii(engineers[-1]['contractorName'])}"


# Qase #219 (OP-186): FIXED, verified 2026-11-19 (before, the server saved angle brackets, emoji and letters in the contractor fields; now it cleans them).
def test_the_server_keeps_only_phone_characters_in_the_contractor_phone(api_roles, draft):
    response, engineers = _add(api_roles["AM"], draft, _contractor(contractorPhone="\U0001F4DE123abc"))
    assert response.status_code == 400 or engineers[-1]["contractorPhone"] == "123", f"saved as {ascii(engineers[-1]['contractorPhone'])}"
