"""HU-09 (OP-20) FSE Arrangement -- what the SERVER does with the 14 numeric fields, the dates and the note, calling the API directly (no screen).

Added 2026-11-06 for the regression of Sprint 1. Until then HU-09 was tested only through the screen. Probe of 2026-11-06 on the QA build:
  * the server rejects negatives and decimals in ALL 14 numeric fields (400) and recalculates every total itself (a forged total is ignored): those are plain tests below;
  * it does NOT hold the rules that the screen holds for the minimums (Support Engineers, Working Hour, Estimated Working Days), the empty dates, End before Start, emoji in
    the note and the maximum amount: those are strict xfail tests with the reason written out (same convention as test_wo_snapshot_api.py: when the server is fixed the
    test turns into an unexpected pass and fails, so the xfail mark has to be removed).
The tests create their own Draft quotations (title prefix HU09-API) and never touch anyone else's. Qase suite 49: the case ids are in the docstrings."""
import pytest

pytestmark = pytest.mark.api

OK = 200
NUMERIC = ["supportEngineers", "workingHourTechDay", "estimatedWorkingDays", "totalOverHoursTech", "laborCostHour", "laborOverCostHour", "hotelCost", "perDiem", "travelDriveTime",
           "airTransportation", "carExpense", "materialExpense", "equipmentRental", "miscellaneous"]
CALC = dict(supportEngineers=2, workingHourTechDay=4, estimatedWorkingDays=2, totalOverHoursTech=2, laborCostHour=45, laborOverCostHour=60, hotelCost=10, perDiem=5,
            travelDriveTime=10, airTransportation=1, carExpense=2, materialExpense=3, equipmentRental=4, miscellaneous=5)


def _body(am, quotation_id):
    return am.get(f"/api/quotations/{quotation_id}").json()


def _save(am, quotation_id, **changes):
    body = _body(am, quotation_id)
    body["arrangement"].update(changes)
    return am.session.put(f"{am.base_url}/api/quotations/{quotation_id}", json=body, timeout=90)


def _arrangement(am, quotation_id):
    return _body(am, quotation_id)["arrangement"]


@pytest.fixture(scope="module")
def draft(api_roles, make_draft):
    """One Draft of the AM shared by the tests that only SAVE values (it stays a Draft)."""
    quotation_id, _ = make_draft("FSEAPI", title_prefix="HU09-API")
    return quotation_id


# ---- The server recalculates every total (Qase #827 to #862) ----------------------------------------------------------------------------
def test_the_server_calculates_the_totals_from_the_documented_formulas(api_roles, draft):
    """Qase #828, #832, #836, #839, #841, #858, #861, #846: Total Working Hour = hours x days + the over hours (since the fix of #82 / OP-59, build of 2026-11-09: the over hours are typed and added); Total Days = engineers x days;
    Labor = engineers x (hours x days x rate + over hours x over rate);
    Onsite = Hotel + Per Diem x engineers x days + Travel x $3; Reimbursable = the 5 expenses; Grand Total = the 3 subtotals."""
    assert _save(api_roles["AM"], draft, **CALC).status_code == OK
    a = _arrangement(api_roles["AM"], draft)
    c = CALC
    base = c["workingHourTechDay"] * c["estimatedWorkingDays"]
    assert a["totalWorkingHourTech"] == base + c["totalOverHoursTech"]
    assert a["totalDays"] == c["supportEngineers"] * c["estimatedWorkingDays"]
    assert a["laborSubtotal"] == c["supportEngineers"] * (base * c["laborCostHour"] + c["totalOverHoursTech"] * c["laborOverCostHour"]) == 960
    assert a["onsiteSubtotal"] == c["hotelCost"] + c["perDiem"] * c["supportEngineers"] * c["estimatedWorkingDays"] + c["travelDriveTime"] * 3 == 60
    assert a["reimbursableSubtotal"] == c["airTransportation"] + c["carExpense"] + c["materialExpense"] + c["equipmentRental"] + c["miscellaneous"] == 15
    assert a["grandTotal"] == a["laborSubtotal"] + a["onsiteSubtotal"] + a["reimbursableSubtotal"] == 1035


def test_travel_and_drive_time_is_valued_at_3_dollars_per_hour_and_counted_once(api_roles, draft):
    """Qase #862 / #847 (OP-20 AC #15): 10 hours -> $30 in the Onsite Support Subtotal, and the Labor Subtotal does not move."""
    am = api_roles["AM"]
    assert _save(am, draft, **{**CALC, "travelDriveTime": 0}).status_code == OK
    before = _arrangement(am, draft)
    assert _save(am, draft, **{**CALC, "travelDriveTime": 10}).status_code == OK
    after = _arrangement(am, draft)
    assert after["travelDriveCosto"] == 30 and after["onsiteSubtotal"] - before["onsiteSubtotal"] == 30 and after["laborSubtotal"] == before["laborSubtotal"]


def test_a_total_sent_by_the_client_is_ignored(api_roles, draft):
    """Qase #829 / #841 (security of the calculation): the request carries a forged Labor Subtotal and Grand Total and the server keeps its own."""
    am = api_roles["AM"]
    assert _save(am, draft, **CALC, laborSubtotal=999999, grandTotal=1, totalManWorkingHours=7, onsiteSubtotal=5).status_code == OK
    a = _arrangement(am, draft)
    assert (a["laborSubtotal"], a["onsiteSubtotal"], a["grandTotal"]) == (960, 60, 1035)


def test_total_man_working_hours_includes_the_over_hours(api_roles, draft):
    am = api_roles["AM"]
    assert _save(am, draft, **CALC).status_code == OK
    assert _arrangement(am, draft)["totalManWorkingHours"] == 20


def test_an_empty_money_field_counts_as_0(api_roles, draft):
    """Qase #838: Hotel Cost and Per Diem sent as null -> the Onsite Subtotal is 0 (plus the travel), the save works."""
    am = api_roles["AM"]
    assert _save(am, draft, **{**CALC, "travelDriveTime": 0, "hotelCost": None, "perDiem": None}).status_code == OK
    assert _arrangement(am, draft)["onsiteSubtotal"] == 0


# ---- Whole numbers only, not negative: the server holds the rule (Qase #831, #834, #835, #850 to #855, #876) -------------------------------
@pytest.mark.parametrize("field", NUMERIC)
def test_every_numeric_field_rejects_a_negative_number(api_roles, draft, field):
    """Qase #831, #834, #835, #852, #853, #854: a negative number gives HTTP 400 with the field in the message (OP-20; the screen blocks the minus sign)."""
    response = _save(api_roles["AM"], draft, **{field: -1})
    assert response.status_code == 400 and field.lower() in response.text.lower(), f"{field}: {response.status_code} {response.text[:150]}"


@pytest.mark.parametrize("field", NUMERIC)
def test_every_numeric_field_rejects_a_decimal_number(api_roles, draft, field):
    """Qase #855 (rule of 2026-11-06, OP-107): the 14 numeric fields take whole numbers only, also for the server: 2.5 gives HTTP 400."""
    response = _save(api_roles["AM"], draft, **{field: 2.5})
    assert response.status_code == 400 and field.lower() in response.text.lower(), f"{field}: {response.status_code} {response.text[:150]}"


def test_a_numeric_field_rejects_letters(api_roles, draft):
    """Qase #876."""
    assert _save(api_roles["AM"], draft, hotelCost="abc").status_code == 400


def test_a_subtotal_too_large_to_store_is_rejected_with_a_message(api_roles, draft):
    """Qase #856 / #857: an amount that makes a subtotal overflow the column (numeric 18,2) gives HTTP 400 'too large to store', not a 500."""
    response = _save(api_roles["AM"], draft, **{**CALC, "laborCostHour": 9999999999999999})
    assert response.status_code == 400 and "too large" in response.text


# ---- Miscellaneous Note (Qase #840, #848, #849, #877) ----------------------------------------------------------------------------------
def test_the_note_accepts_500_characters_and_rejects_501(api_roles, draft):
    """Qase #849 / defect #95: the limit of the screen (500) is also the limit of the server."""
    am = api_roles["AM"]
    assert _save(am, draft, miscellaneousNote="A" * 500).status_code == OK and len(_arrangement(am, draft)["miscellaneousNote"]) == 500
    response = _save(am, draft, miscellaneousNote="A" * 501)
    assert response.status_code == 400 and "miscellaneousnote" in response.text.lower()


def test_the_note_is_stored_with_the_amount(api_roles, draft):
    """Qase #840."""
    am = api_roles["AM"]
    assert _save(am, draft, miscellaneous=5, miscellaneousNote="Spare fuses").status_code == OK
    a = _arrangement(am, draft)
    assert a["miscellaneous"] == 5 and a["miscellaneousNote"] == "Spare fuses"


def test_the_server_removes_the_angle_brackets_of_html_in_the_note(api_roles, draft):
    """Qase #877 / defect #88: '<script>alert(1)</script>' is stored without the < and > (a plain text), so it cannot run."""
    am = api_roles["AM"]
    assert _save(am, draft, miscellaneousNote="<script>alert(1)</script>").status_code == OK
    stored = _arrangement(am, draft)["miscellaneousNote"]
    assert "<" not in stored and ">" not in stored


# ---- Findings: rules that live only in the screen ---------------------------------------------------------------------------------------
@pytest.mark.xfail(strict=True, reason="OPEN FINDING (2026-11-06): the screen blocks emoji in the Miscellaneous Note (defect #94 closed), but the server saves them when the request skips the screen "
                   "(HTTP 200, the emoji comes back). Same pattern as HU-08 (#210). Qase #848.")
def test_emoji_in_the_note_is_rejected_by_the_server(api_roles, draft):
    response = _save(api_roles["AM"], draft, miscellaneousNote="Test \U0001F600")
    assert response.status_code == 400, f"the server saved an emoji in the note: {response.status_code}"


def test_the_server_refuses_an_end_date_before_the_start_date(api_roles, make_draft):
    am = api_roles["AM"]
    quotation_id, _ = make_draft("FSEDATE", title_prefix="HU09-API")
    saved = _save(am, quotation_id, estimacionStartTime="2026-10-10T00:00:00", estimacionEndTime="2026-10-01T00:00:00")
    submitted = am.post(f"/api/quotations/{quotation_id}/submit", json={"approverOverrideAcknowledged": False})
    assert saved.status_code == 400 or submitted.status_code == 400, f"saved {saved.status_code}, submitted {submitted.status_code}"


@pytest.mark.parametrize("changes", [dict(supportEngineers=0), dict(workingHourTechDay=0), dict(estimatedWorkingDays=0), dict(estimacionStartTime=None, estimacionEndTime=None)],
                         ids=["Support Engineers 0", "Working Hour 0", "Working Days 0", "dates empty"])
def test_the_server_refuses_to_submit_with_a_minimum_or_a_date_missing(api_roles, make_draft, changes):
    am = api_roles["AM"]
    quotation_id, _ = make_draft("FSEMIN", title_prefix="HU09-API")
    assert _save(am, quotation_id, **{"supportEngineers": 2, "workingHourTechDay": 8, "estimatedWorkingDays": 2, **changes}).status_code == OK, "a Draft can be saved incomplete"
    response = am.post(f"/api/quotations/{quotation_id}/submit", json={"approverOverrideAcknowledged": False})
    assert response.status_code == 400, f"the server submitted it with {changes}: HTTP {response.status_code}"


@pytest.mark.xfail(strict=True, reason="OPEN FINDING (2026-11-06, low): the screen stops every money field at 6 digits (999,999; the developer confirmed the length on 2026-11-06), but the server saves "
                   "99,999,999,999 in Hotel Cost (a Grand Total of more than 100 billion). Only the column (numeric 18,2) limits it. Qase #849.")
def test_the_server_applies_the_6_digit_limit_of_the_money_fields(api_roles, draft):
    response = _save(api_roles["AM"], draft, **{**CALC, "hotelCost": 1234567})
    assert response.status_code == 400, f"the server accepted Hotel Cost 1234567: {response.status_code}"
