"""HU-08 (OP-19) WO Snapshot -- what the SERVER does with the fields, calling the API directly (no screen).

Added 2026-11-06 for the regression of Sprint 1: until then HU-08 was tested only through the screen. The screen blocks many values (units, emoji, the Type Of Work list,
empty mandatory fields) but a request can skip the screen, so these tests check that the server itself holds the rule.
Findings that the server does NOT hold are strict xfail tests with the reason written out, the same convention as the rest of the repo: when the server is fixed the
test turns into an unexpected pass and fails, so the xfail mark has to be removed. Qase cases: 716 to 723, 791, 794, 798, 799, 806 to 813, 961 (see the docstrings).
The tests create their own Draft quotations (title prefix HU08-API) and never touch anyone else's."""
import pytest

pytestmark = pytest.mark.api

SAVE_OK = 200


def _save(am, quotation_id, **changes):
    body = am.get(f"/api/quotations/{quotation_id}").json()
    body.update(changes)
    return am.session.put(f"{am.base_url}/api/quotations/{quotation_id}", json=body, timeout=90)


@pytest.fixture(scope="module")
def draft(api_roles, make_draft):
    """One Draft of the first AM shared by the tests that only SAVE values (it stays a Draft)."""
    quotation_id, _ = make_draft("WOSNAP", title_prefix="HU08-API")
    return quotation_id


# ---- Units (Qase #809 to #813, #878) -------------------------------------------------------------------------------------------------
def test_units_rejects_a_negative_number(api_roles, draft):
    """Qase #812."""
    response = _save(api_roles["AM"], draft, units=-5)
    assert response.status_code == 400 and "units" in response.text.lower(), f"{response.status_code} {response.text[:150]}"


def test_units_rejects_a_decimal_number(api_roles, draft):
    """Qase #813."""
    response = _save(api_roles["AM"], draft, units=3.7)
    assert response.status_code == 400 and "whole number" in response.text, f"{response.status_code} {response.text[:150]}"


def test_units_rejects_letters(api_roles, draft):
    """Qase #878."""
    response = _save(api_roles["AM"], draft, units="abc")
    assert response.status_code == 400, f"{response.status_code} {response.text[:150]}"


@pytest.mark.parametrize("value", [0, 7])
def test_units_accepts_zero_and_positive_whole_numbers(api_roles, draft, value):
    """Qase #811 (the developer confirmed on 2026-11-06 that 0 is valid) and #810."""
    response = _save(api_roles["AM"], draft, units=value)
    assert response.status_code == SAVE_OK and response.json()["units"] == value


# ---- Type Of Work and Severity: the lists (Qase #794, #806, #808) ---------------------------------------------------------------------
@pytest.mark.parametrize("value", ["Commissioning", "Rework", "Warranty Repair", "Chargeable Repair"])
def test_type_of_work_accepts_each_of_the_four_documented_values(api_roles, draft, value):
    """Qase #806 / #808 (PMP was removed: the list has 4 values)."""
    response = _save(api_roles["AM"], draft, typeOfWork=value)
    assert response.status_code == SAVE_OK and response.json()["typeOfWork"] == value


@pytest.mark.parametrize("value", ["Critical", "Major", "Minor", "Warning", "Normal"])
def test_severity_accepts_each_of_the_five_documented_values(api_roles, draft, value):
    """Qase #794."""
    response = _save(api_roles["AM"], draft, severity=value)
    assert response.status_code == SAVE_OK and response.json()["severity"] == value


@pytest.mark.xfail(strict=True, reason="OPEN FINDING (2026-11-06, no defect filed yet, waiting for the team's decision): the server accepts a Type Of Work that is not in the list "
                   "(PMP, which was removed, and a made-up word). Only the dropdown of the screen restricts it. Qase #806.")
@pytest.mark.parametrize("value", ["PMP", "Banana"])
def test_type_of_work_outside_the_list_is_rejected_by_the_server(api_roles, draft, value):
    response = _save(api_roles["AM"], draft, typeOfWork=value)
    assert response.status_code == 400, f"the server accepted typeOfWork={value!r}: {response.status_code}"


@pytest.mark.xfail(strict=True, reason="OPEN FINDING (2026-11-06, no defect filed yet): the server accepts a Severity that is not one of the 5 values; only the dropdown restricts it. Qase #794.")
def test_severity_outside_the_list_is_rejected_by_the_server(api_roles, draft):
    response = _save(api_roles["AM"], draft, severity="Banana")
    assert response.status_code == 400, f"the server accepted severity='Banana': {response.status_code}"


# ---- Emoji (Qase #798, #799) -----------------------------------------------------------------------------------------------------------
@pytest.mark.xfail(strict=True, reason="OPEN FINDING (2026-11-06, no defect filed yet): the screen refuses emoji in OEM Name and WO Title (defect #75 closed), but the server saves them "
                   "when the request skips the screen. Qase #798 / #799.")
@pytest.mark.parametrize("field", ["oemName", "title"])
def test_emoji_is_rejected_by_the_server(api_roles, draft, field):
    response = _save(api_roles["AM"], draft, **{field: "Test \U0001F600"})
    assert response.status_code == 400, f"the server saved an emoji in {field}: {response.status_code}"


# ---- Mandatory fields on Submit (Qase #721, #791, #807; OP-19 AC 3 and 5) --------------------------------------------------------------
@pytest.mark.xfail(strict=True, reason="OPEN FINDING (2026-11-06, no defect filed yet): OP-19 AC-5 says the system must prevent submission until a failed validation is corrected, and the screen "
                   "does (Qase #721, #791, #807), but the server SENDS the quotation with the field empty: HTTP 200 and the status becomes Awaiting. The rule lives only in the screen.")
@pytest.mark.parametrize("field, empty", [("oemName", ""), ("typeOfWork", ""), ("siteName", ""), ("title", ""), ("customerName", "")],
                         ids=["OEM Name", "Type Of Work", "Site Name", "WO Title", "Customer"])
def test_the_server_refuses_to_submit_with_a_mandatory_field_empty(api_roles, make_draft, field, empty):
    quotation_id, _ = make_draft("WOSNAPM", title_prefix="HU08-API")
    am = api_roles["AM"]
    changes = {field: empty}
    if field == "siteName":
        changes["siteProjectId"] = None
    if field == "customerName":
        changes["customerId"] = None
    assert _save(am, quotation_id, **changes).status_code == SAVE_OK, "a Draft can be saved with a field empty"
    response = am.post(f"/api/quotations/{quotation_id}/submit", json={"approverOverrideAcknowledged": False})
    assert response.status_code == 400, f"the server submitted it with {field} empty: HTTP {response.status_code}"
