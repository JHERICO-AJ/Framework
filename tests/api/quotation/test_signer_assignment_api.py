"""HU-16 (OP-24) SIGNER ASSIGNMENT -- what the SERVER does with the approvers of a quotation, calling the API directly (no screen), signed in as the AM.

Added 2026-11-09 for the regression of Sprint 1 (HU-16 had only screen tests until then). Scope of the story on that date: OP-24 changed on 2026-11-05 (the manual approver
assignment logic was discarded: AC #2, #4, #7 and #8) and the developer confirmed that only the OEM contact can be entered by hand and that the approver level is not validated any more:
the approvers are the defaults for the amount. So what is tested is AC #1/#3 (default approver by amount), #5 (a Submit without added approvers goes to the default approver) and
the OEM contact (one email once, the size of the name and the email). Probe of 2026-11-09 on the QA build:
  * the default approver by amount is FPM/FSM below $100,000, BU from $100,000 up to and including $500,000, CEO above $500,000 (Qase #940, #960; defect #142 / OP-112 fixed);
  * the server refuses the same email twice in the route (APPROVER_DUPLICATE, case-insensitive) and takes the same name with another email (OP-101: only the email is validated);
  * the server limits the approver name to 200 and the email to 300 characters (HTTP 400 with the field in the message): defect #122 / OP-103 fixed on the server.
NOT tested because the developer has not answered yet (2026-11-09): the server saves an email with an emoji or without '@' and a name with '<script>' for the OEM contact, which the screen refuses.
The tests create their own quotations (title prefix HU16-API) and never touch anyone else's. Qase suite 46: the case ids are in the docstrings."""
import pytest

from framework_api.services import quotation_setup as qs
from framework_api.services.quotation_service import QuotationService

pytestmark = pytest.mark.api

OK = 200
BASE_TOTAL = 8410          # the total of the default FSE Arrangement of quotation_setup


def hotel_for(total):
    return {"hotelCost": 1050 + (total - BASE_TOTAL)}


def _route(body):
    """[(role, isAutoAssigned)] in route order."""
    return [(a["role"], a["isAutoAssigned"]) for a in sorted(body["approvers"], key=lambda a: a["order"])]


def _draft_without_signers(api_roles, tag, total=50000):
    quotation_id, _ = qs.create_and_submit(api_roles["AM"], api_roles, tag, ["FPM"], arrangement=hotel_for(total), title_prefix="HU16-API", extra={"approvers": []}, submit=False)
    return quotation_id


def _external(order, name, email):
    return {"workflowStage": "Vendor Reviewing", "order": order, "role": "OEM", "userId": None, "userName": name, "email": email, "status": "Pending", "isAutoAssigned": False}


def _save_with(api_roles, quotation_id, approvers):
    am = api_roles["AM"]
    body = am.get(f"/api/quotations/{quotation_id}").json()
    body["approvers"] = approvers
    return am.session.put(f"{am.base_url}/api/quotations/{quotation_id}", json=body, timeout=90)


@pytest.fixture(scope="module")
def draft(api_roles):
    """One Draft of the AM with one internal signer, shared by the tests that only SAVE the OEM contact (it stays a Draft)."""
    quotation_id, _ = qs.create_draft(api_roles["AM"], api_roles, "SIGNERS", title_prefix="HU16-API")
    return quotation_id


@pytest.fixture
def base_signer(api_roles, draft):
    return api_roles["AM"].get(f"/api/quotations/{draft}").json()["approvers"][0]


# ---- Default approver by amount (Qase #940, #960; OP-24 AC #1, #3) -----------------------------------------------------------------------------
@pytest.mark.parametrize("total, role", [(50000, "FPM_FSM"), (99992, "FPM_FSM"), (100000, "BU"), (499992, "BU"), (500000, "BU"), (500008, "CEO")],
                         ids=["50k", "99,992", "100,000", "499,992", "500,000", "500,008"])
def test_the_default_approver_follows_the_amount_at_the_limits(api_roles, total, role):
    """Qase #960 / #940: below $100,000 the FPM/FSM, from $100,000 up to $500,000 (both included) the BU, above $500,000 the CEO; the one the system assigns is flagged isAutoAssigned.
    $500,000 exactly is BU (defect #142 / OP-112, fixed)."""
    am = api_roles["AM"]
    quotation_id = _draft_without_signers(api_roles, f"T{total}", total)
    response = QuotationService(am).submit(quotation_id)
    assert response.status_code == OK, f"{response.status_code} {response.text[:150]}"
    body = am.get(f"/api/quotations/{quotation_id}").json()
    assert body["totalAmount"] == total and body["status"] == "Awaiting"
    assert _route(body) == [(role, True)]


def test_a_submit_without_added_approvers_goes_to_the_default_approver(api_roles):
    """Qase #943 / OP-24 AC #5: the AM adds nobody and sends: the quotation goes to the default approver of the amount (nothing is left without an approver)."""
    am = api_roles["AM"]
    quotation_id = _draft_without_signers(api_roles, "NOSIGNER")
    assert am.get(f"/api/quotations/{quotation_id}").json()["approvers"] == [], "a Draft saved without signers has no approver yet"
    assert QuotationService(am).submit(quotation_id).status_code == OK
    body = am.get(f"/api/quotations/{quotation_id}").json()
    assert len(body["approvers"]) == 1 and body["approvers"][0]["isAutoAssigned"] is True and body["approvers"][0]["status"] == "Pending"


# ---- OEM contact: the only manual entry left (Qase #934 to #938, #946, #948) ---------------------------------------------------------------------
def test_the_oem_contact_is_saved_as_an_external_signer(api_roles, draft, base_signer):
    """Qase #938: the OEM contact (no user id) is kept with its name and email after the internal signer."""
    response = _save_with(api_roles, draft, [base_signer, _external(1, "Zzz Oem Contact", "oem.contact@example.com")])
    assert response.status_code == OK
    saved = sorted(api_roles["AM"].get(f"/api/quotations/{draft}").json()["approvers"], key=lambda a: a["order"])
    assert [(a["role"], a["userName"], a["email"], a["userId"]) for a in saved][1] == ("OEM", "Zzz Oem Contact", "oem.contact@example.com", None)


@pytest.mark.parametrize("second_email", ["dup@example.com", "DUP@Example.com"], ids=["same email", "same email in capitals"])
def test_the_same_email_cannot_be_added_twice(api_roles, draft, base_signer, second_email):
    """Qase #936 / OP-101 (developer, 2026-10-30: only the email is validated): the same email twice is refused with APPROVER_DUPLICATE and a message that names the signer."""
    response = _save_with(api_roles, draft, [base_signer, _external(1, "Name One", "dup@example.com"), _external(2, "Name Two", second_email)])
    assert response.status_code == 400 and "APPROVER_DUPLICATE" in response.text and "Name Two" in response.text, f"{response.status_code} {response.text[:150]}"


def test_the_same_name_with_another_email_is_accepted(api_roles, draft, base_signer):
    """OP-101 (developer): only the email is validated, two people can share a name."""
    response = _save_with(api_roles, draft, [base_signer, _external(1, "Same Name", "same.one@example.com"), _external(2, "Same Name", "same.two@example.com")])
    assert response.status_code == OK


@pytest.mark.parametrize("field, limit", [("userName", 200), ("email", 300)])
def test_the_name_and_the_email_accept_their_maximum_and_refuse_one_more(api_roles, draft, base_signer, field, limit):
    """Qase #948 (defect #122 / OP-103, fixed on the server): name 200 and email 300 characters are the maximum; one more is HTTP 400 with the field in the message."""
    def value(n):
        return ("a" * (n - 12) + "@example.com") if field == "email" else "N" * n
    other = "limit.name@example.com" if field == "userName" else None

    def signer(n):
        return _external(1, value(n) if field == "userName" else "Limit Name", other or value(n))
    assert _save_with(api_roles, draft, [base_signer, signer(limit)]).status_code == OK
    over = _save_with(api_roles, draft, [base_signer, signer(limit + 1)])
    assert over.status_code == 400 and field in over.text, f"{field} with {limit + 1}: {over.status_code} {over.text[:150]}"


# ---- Finding: the rule that the screen states and the server does not hold (Qase #946, defect #120, Jira OP-101) --------------------------------
@pytest.mark.xfail(strict=True, reason="OPEN DEFECT (Qase #946, defect #120, Jira OP-101, retested 2026-11-09): the OEM contact panel says 'One at a time only.' but the server saves two OEM contacts "
                   "in the same route (HTTP 200); the screen lets a second one be added too. The rule is the one the screen states.")
def test_only_one_oem_contact_can_be_in_the_route(api_roles, draft, base_signer):
    response = _save_with(api_roles, draft, [base_signer, _external(1, "Oem One", "oem.one@example.com"), _external(2, "Oem Two", "oem.two@example.com")])
    assert response.status_code == 400, f"two OEM contacts were saved: HTTP {response.status_code}"


# ---- The rules the default approver comes from (OP-24 AC #1, #3, #6; Qase #940, #960) -----------------------------------------------------------
def test_the_default_rules_define_the_three_thresholds(api_roles):
    """OP-24 AC #3 / #6: the screen reads GET /api/quotations/approval-default-rules before the quotation is sent to show the default approver: below $100,000 no BU approver
    (no required role, the FPM/FSM default), from $100,000 to $500,000 the BU, above $500,000 the CEO; every rule active, able to auto-assign and with a default approver."""
    response = api_roles["AM"].get("/api/quotations/approval-default-rules")
    assert response.status_code == OK
    rules = sorted(response.json(), key=lambda r: r["minAmount"])
    assert [(r["minAmount"], r["maxAmount"], r["requiredApproverRole"]) for r in rules] == [(0, 100000, None), (100000, 500000, "BU"), (500000, None, "CEO")]
    assert all(r["isActive"] and r["canAutoAssign"] and r["defaultApproverEmployeeId"] for r in rules)


def test_each_default_approver_of_the_rules_is_an_employee_of_the_catalog(api_roles):
    """OP-24 AC #6: the default approver the screen shows comes from the employee catalog; the id of each rule must exist there."""
    am = api_roles["AM"]
    ids = {e["employeeId"] for e in am.get("/api/amxcpcatalog/employees").json()}
    missing = [r["defaultApproverEmployeeId"] for r in am.get("/api/quotations/approval-default-rules").json() if r["defaultApproverEmployeeId"] not in ids]
    assert not missing, f"default approvers that are not in the catalog: {missing}"


# ---- Findings deduced from what the screen enforces (no answer from the developer yet, 2026-11-09) -----------------------------------------------
@pytest.mark.xfail(strict=True, reason="OPEN FINDING (2026-11-09): the screen only enables Add for a valid email and removes emoji from the email field (Qase #934, #947; V13 AC-2.7.9: a valid email "
                   "address is required for every added approver), but the server saves an OEM contact whose email has no '@' or starts with an emoji (HTTP 200). The OEM decides from an email link, "
                   "so an invalid address leaves the quotation waiting on someone who can never receive it.")
@pytest.mark.parametrize("email", ["notanemail", "\U0001F4DEoem@example.com", "a@@example.com", "a b@example.com", "<script>alert(1)</script>@example.com"],
                         ids=["no at sign", "emoji at the start", "two at signs", "with a space", "script tag"])
def test_the_server_refuses_an_invalid_oem_email(api_roles, draft, base_signer, email):
    response = _save_with(api_roles, draft, [base_signer, _external(1, "Oem Bad Email", email)])
    assert response.status_code == 400, f"saved the email {ascii(email)}: HTTP {response.status_code}"


@pytest.mark.xfail(strict=True, reason="OPEN FINDING (2026-11-09): the server saves '<script>alert(1)</script>' as the name of the OEM contact (HTTP 200). The same name rule is applied by the server "
                   "in Miscellaneous Note (HU-09) and is expected for the contractor fields (HU-11); the approver name is shown in the WAITING ON column and in the emails.")
def test_the_server_removes_the_angle_brackets_of_the_oem_name(api_roles, draft, base_signer):
    response = _save_with(api_roles, draft, [base_signer, _external(1, "<script>alert(1)</script>", "oem.script@example.com")])
    saved = [a["userName"] for a in api_roles["AM"].get(f"/api/quotations/{draft}").json()["approvers"]]
    assert response.status_code == 400 or all("<" not in n and ">" not in n for n in saved), f"saved as {saved}"


@pytest.mark.xfail(strict=True, reason="OPEN FINDING (2026-11-09): the server saves an emoji in the name of the OEM contact (HTTP 200). Same rule as OEM Name / WO Title (HU-08, Qase #798/#799), Miscellaneous Note "
                   "(HU-09, #213) and the contractor name (HU-11).")
def test_the_server_rejects_emoji_in_the_oem_name(api_roles, draft, base_signer):
    response = _save_with(api_roles, draft, [base_signer, _external(1, "\U0001F4DE Juan", "oem.emoji.name@example.com")])
    saved = [a["userName"] for a in api_roles["AM"].get(f"/api/quotations/{draft}").json()["approvers"]]
    assert response.status_code == 400 or all("\U0001F4DE" not in n for n in saved), f"saved as {[ascii(n) for n in saved]}"


@pytest.mark.parametrize("name, email", [("x'; DROP TABLE a;--", "sql.name@example.com"), ("' OR '1'='1", "sql.or@example.com"), ("Sql Email", "a'; DROP TABLE a;--@example.com")],
                         ids=["drop table in the name", "or 1=1 in the name", "drop table in the email"])
def test_sql_looking_text_in_the_oem_contact_is_stored_as_plain_text(api_roles, draft, base_signer, name, email):
    """Qase #939: an SQL-looking name or email is never run: it is kept literally (or refused) and the quotation still opens, so there is no SQL injection through the OEM contact."""
    response = _save_with(api_roles, draft, [base_signer, _external(1, name, email)])
    assert response.status_code in (OK, 400), f"HTTP {response.status_code} {response.text[:150]}"
    body = api_roles["AM"].get(f"/api/quotations/{draft}")
    assert body.status_code == OK
    if response.status_code == OK:
        saved = [(a["userName"], a["email"]) for a in body.json()["approvers"]]
        assert (name, email) in saved, f"stored as {saved}"
