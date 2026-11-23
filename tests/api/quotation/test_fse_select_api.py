"""HU-10 (OP-28) FSE Select form -- what the SERVER does with Support Engineers, the planned and possible dates, the Field Leader and the selected engineers,
calling the API directly (no screen).

Added 2026-11-09 for the regression of Sprint 1. Until then HU-10 was tested only through the screen. Probe of 2026-11-09 on the QA build:
  * the server rejects a negative, a decimal and a letter in Support Engineers (400) and keeps the dates, the leader, the order and the data of the engineers exactly as saved:
    plain tests below;
  * it does NOT hold the rules the screen holds for the minimum of Support Engineers, more engineers selected than required, a check-out before the check-in and the Field Leader
    (one leader among the selected engineers): strict xfail tests with the reason written out (same convention as test_wo_snapshot_api.py: when the server is fixed the test turns
    into an unexpected pass and fails, so the xfail mark has to be removed);
  * Possible Check-In/Out is never calculated by the server (defect #99 / OP-74).
The tests create their own Draft quotations (title prefix HU10-API) and never touch anyone else's. Qase suite 47: the case ids are in the docstrings."""
import pytest

from framework_api.services import quotation_setup as qs

pytestmark = pytest.mark.api

OK = 200
E = list(qs.ENGINEERS)
IN, OUT = "2026-11-20T09:00:00", "2026-11-21T17:00:00"


def _extra(count=2, support_engineers=None):
    """A priced selection (the Budget Calculator confirmed), which is what the server needs before it lets the quotation be sent."""
    return qs.select_extra(*[(E[i], qs.engineer_cost("quotation", 50, 8), qs.engineer_cost("expense", 30, 8)) for i in range(count)], support_engineers=support_engineers)


def _body(am, quotation_id):
    return am.get(f"/api/quotations/{quotation_id}").json()


def _save(am, quotation_id, mutate):
    body = _body(am, quotation_id)
    mutate(body["select"])
    return am.session.put(f"{am.base_url}/api/quotations/{quotation_id}", json=body, timeout=90)


def _select(am, quotation_id):
    return _body(am, quotation_id)["select"]


def _submit(am, quotation_id):
    return am.post(f"/api/quotations/{quotation_id}/submit", json={"approverOverrideAcknowledged": False})


@pytest.fixture(scope="module")
def draft(api_roles, make_draft):
    """One Draft of the AM with 2 engineers shared by the tests that only SAVE values (it stays a Draft)."""
    quotation_id, _ = make_draft("FSESEL", title_prefix="HU10-API", extra=_extra(2))
    return quotation_id


# ---- Support Engineers (Qase #883 to #885, #908) ----------------------------------------------------------------------------------------
@pytest.mark.parametrize("value", [-1, 2.5, "abc"], ids=["negative", "decimal", "letters"])
def test_support_engineers_rejects_a_negative_a_decimal_and_letters(api_roles, draft, value):
    """Qase #884 / #850: the screen does not go below 1 and takes whole numbers; the server answers HTTP 400 with the field in the message."""
    response = _save(api_roles["AM"], draft, lambda s: s.__setitem__("supportEngineers", value))
    assert response.status_code == 400, f"supportEngineers={value!r}: {response.status_code} {response.text[:150]}"


@pytest.mark.parametrize("value", [1, 2, 5])
def test_support_engineers_accepts_whole_numbers_from_1(api_roles, draft, value):
    """Qase #883 / #885."""
    assert _save(api_roles["AM"], draft, lambda s: s.__setitem__("supportEngineers", value)).status_code == OK
    assert _select(api_roles["AM"], draft)["supportEngineers"] == value


# ---- Dates, leader and engineers are stored as saved (Qase #887, #889, #896) ---------------------------------------------------------------
def test_planned_and_possible_dates_are_stored_exactly(api_roles, draft):
    """Qase #896 / #887: Planned and Possible Check-in/out keep the date and the hour that were saved."""
    am = api_roles["AM"]
    assert _save(am, draft, lambda s: s.update(plannedCheckIn=IN, plannedCheckOut=OUT, possibleCheckIn=IN, possibleCheckOut=OUT)).status_code == OK
    s = _select(am, draft)
    assert (s["plannedCheckIn"], s["plannedCheckOut"], s["possibleCheckIn"], s["possibleCheckOut"]) == (IN, OUT, IN, OUT)


def test_the_first_selected_engineer_is_the_field_leader(api_roles, make_draft):
    """Qase #889: Field Leader defaults to the first selected engineer, and only that one is marked as the leader."""
    am = api_roles["AM"]
    quotation_id, _ = make_draft("FSELEAD", title_prefix="HU10-API", extra=_extra(3))
    s = _select(am, quotation_id)
    leaders = [e for e in s["selectedEngineers"] if e["isLeader"]]
    assert len(leaders) == 1 and leaders[0]["contractorName"] == E[0] and s["fieldLeaderId"] == leaders[0]["id"]


def test_the_selected_engineers_keep_their_order_and_data(api_roles, make_draft):
    """Qase #896: the 3 engineers come back in the order they were selected, with their phone, email, location and availability."""
    am = api_roles["AM"]
    quotation_id, _ = make_draft("FSEORDER", title_prefix="HU10-API", extra=_extra(3))
    engineers = _select(am, quotation_id)["selectedEngineers"]
    assert [e["contractorName"] for e in engineers] == E[:3]
    for e in engineers:
        assert e["contractorPhone"] == qs.ENGINEERS[e["contractorName"]]["contractorPhone"] and e["availabilityStatus"] == "available"


def test_prevailing_wage_act_is_stored(api_roles, draft):
    am = api_roles["AM"]
    for value in (True, False):
        assert _save(am, draft, lambda s, v=value: s.__setitem__("prevailingWageAct", v)).status_code == OK
        assert _select(am, draft)["prevailingWageAct"] is value


# ---- Findings: rules that live only in the screen ---------------------------------------------------------------------------------------
@pytest.mark.skip(reason="OUT OF SCOPE OF HU-10 (decision of 2026-11-09): the calculation of Possible Check-In/Out moved to Sprint 2 (OP-74); Qase case FSS-API7 deprecated, defect #99 closed as not applicable.")
def test_possible_check_in_and_out_are_calculated_for_the_selected_engineers(api_roles, draft):
    am = api_roles["AM"]
    assert _save(am, draft, lambda s: s.update(supportEngineers=2, plannedCheckIn=IN, plannedCheckOut=OUT, possibleCheckIn=None, possibleCheckOut=None)).status_code == OK
    s = _select(am, draft)
    assert s["possibleCheckIn"] and s["possibleCheckOut"], f"possible dates: {s['possibleCheckIn']} / {s['possibleCheckOut']}"


@pytest.mark.xfail(strict=True, reason="OPEN FINDING (2026-11-09): the screen asks for at least 1 Support Engineer (Qase #884) and does not let more engineers be selected than required "
                   "(Qase #901, #908), but the server SENDS the quotation with Support Engineers 0, or with 3 engineers selected when 2 are required: HTTP 200 and the status "
                   "becomes Awaiting. The rule lives only in the screen (same as HU-08 #208 and HU-09 #211).")
@pytest.mark.parametrize("count, required", [(2, 0), (3, 2)], ids=["Support Engineers 0", "3 selected, 2 required"])
def test_the_server_refuses_to_submit_with_the_engineers_out_of_range(api_roles, make_draft, count, required):
    am = api_roles["AM"]
    quotation_id, _ = make_draft("FSERANGE", title_prefix="HU10-API", extra=_extra(count, support_engineers=required or 2))
    assert _save(am, quotation_id, lambda s: s.__setitem__("supportEngineers", required)).status_code == OK, "a Draft can be saved incomplete"
    response = _submit(am, quotation_id)
    assert response.status_code == 400, f"the server submitted it with {count} selected and {required} required: HTTP {response.status_code}"


@pytest.mark.xfail(strict=True, reason="OPEN FINDING (2026-11-09): the screen does not allow a check-out before the check-in (Qase #892, defect #101 closed), but the server saves it for the Planned "
                   "and the Possible dates and even SENDS the quotation (HTTP 200, status Awaiting). Same as HU-09 #212.")
@pytest.mark.parametrize("field", ["planned", "possible"])
def test_the_server_refuses_a_check_out_before_the_check_in(api_roles, make_draft, field):
    am = api_roles["AM"]
    quotation_id, _ = make_draft("FSECHK", title_prefix="HU10-API", extra=_extra(2))
    saved = _save(am, quotation_id, lambda s: s.update({f"{field}CheckIn": OUT, f"{field}CheckOut": IN}))
    submitted = _submit(am, quotation_id)
    assert saved.status_code == 400 or submitted.status_code == 400, f"saved {saved.status_code}, submitted {submitted.status_code}"


def test_an_unknown_field_leader_id_is_not_stored(api_roles, make_draft, db_conn):
    """Checked against the database 2026-11-10 (developer's remark on OP-185): the server answers 200 but ignores an id that belongs to no selected engineer and keeps the first
    engineer as the leader; FSE_Select.FieldLeaderId never holds the unknown id. Not a defect."""
    am = api_roles["AM"]
    quotation_id, _ = make_draft("FSELDRU", title_prefix="HU10-API", extra=_extra(2))
    unknown = "00000000-0000-0000-0000-000000000001"
    assert _save(am, quotation_id, lambda s: s.update(fieldLeaderId=unknown)).status_code == 200
    select = _select(am, quotation_id)
    with db_conn.cursor() as cur:
        cur.execute('SELECT "FieldLeaderId" FROM quotation."FSE_Select" WHERE "QuotationId" = %s', (quotation_id,))
        stored = str(cur.fetchone()[0])
    assert select["fieldLeaderId"] != unknown and stored != unknown and stored in [e["id"] for e in select["selectedEngineers"]]


@pytest.mark.xfail(strict=True, reason="OPEN FINDING (2026-11-09, defect #217 / OP-185, corrected 2026-11-10): the Field Leader select of the screen holds one leader (Qase #889, #891), but the server "
                   "saves every selected engineer marked as leader (HTTP 200; EngineersSelected.EsLider is true for both). An unknown leader id is NOT stored (see the test above).")
def test_the_server_keeps_only_one_engineer_marked_as_leader(api_roles, make_draft):
    am = api_roles["AM"]
    quotation_id, _ = make_draft("FSELDR", title_prefix="HU10-API", extra=_extra(2))

    def mutate(s):
        for e in s["selectedEngineers"]:
            e["isLeader"] = True
    assert _save(am, quotation_id, mutate).status_code == 400
