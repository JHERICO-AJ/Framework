"""HU-10 (OP-28) FSE Select, API against the Postgres database (read-only), added 2026-11-09 for the regression of Sprint 1.
What the API saves must be what is stored: the planned and possible dates, the Support Engineers, the Field Leader and the selected engineers in their order."""
import pytest

from framework_api.services import quotation_setup as qs

pytestmark = [pytest.mark.cross_layer, pytest.mark.api]

E = list(qs.ENGINEERS)
IN, OUT = "2026-11-20T09:00:00", "2026-11-21T17:00:00"


def test_the_select_values_saved_through_the_api_are_the_ones_stored(api_roles, make_draft, db_conn):
    """Qase #896 / #887 / #889: Support Engineers, Planned and Possible dates, prevailing wage and the Field Leader are stored as saved."""
    am = api_roles["AM"]
    quotation_id, _ = make_draft("FSESELDB", title_prefix="HU10-API", extra=qs.select_extra((E[0], None, None), (E[1], None, None), (E[2], None, None)))
    body = am.get(f"/api/quotations/{quotation_id}").json()
    body["select"].update(plannedCheckIn=IN, plannedCheckOut=OUT, possibleCheckIn=IN, possibleCheckOut=OUT, supportEngineers=3, prevailingWageAct=True)
    assert am.session.put(f"{am.base_url}/api/quotations/{quotation_id}", json=body, timeout=90).status_code == 200
    leader_id = am.get(f"/api/quotations/{quotation_id}").json()["select"]["fieldLeaderId"]
    with db_conn.cursor() as cur:
        cur.execute('SELECT "PlannedCheckIn", "PlannedCheckOut", "PossibleCheckIn", "PossibleCheckOut", "SupportEngineers", "PrevailingWageAct", "FieldLeaderId" FROM quotation."FSE_Select" WHERE "QuotationId" = %s', (quotation_id,))
        row = cur.fetchone()
    assert [d.isoformat() for d in row[:4]] == [IN, OUT, IN, OUT] and row[4] == 3 and row[5] is True and str(row[6]) == leader_id


def test_the_selected_engineers_are_stored_in_order_with_one_leader(api_roles, make_draft, db_conn):
    """Qase #896 / #889: 3 engineers stored in the selection order; only the first one is the leader."""
    quotation_id, _ = make_draft("FSEORDDB", title_prefix="HU10-API", extra=qs.select_extra((E[0], None, None), (E[1], None, None), (E[2], None, None)))
    with db_conn.cursor() as cur:
        cur.execute('SELECT e."ContratistaNombre", e."EsLider", e."AvailabilityStatus" FROM quotation."EngineersSelected" e JOIN quotation."FSE_Select" s ON s."Id" = e."FseSelectId" '
                    'WHERE s."QuotationId" = %s ORDER BY e."Order"', (quotation_id,))
        rows = cur.fetchall()
    assert [r[0] for r in rows] == E[:3] and [r[1] for r in rows] == [True, False, False] and {r[2] for r in rows} == {"available"}


def test_the_select_columns_hold_what_the_form_allows(db_conn):
    """Qase #896: the dates are timestamps, Support Engineers is an integer, the leader is a uuid and the contractor name/phone/email/location are 200/50/300/200 characters."""
    with db_conn.cursor() as cur:
        cur.execute("SELECT table_name, column_name, data_type, character_maximum_length FROM information_schema.columns WHERE table_schema = 'quotation' AND table_name IN ('FSE_Select', 'EngineersSelected')")
        columns = {(t, c): (kind, size) for t, c, kind, size in cur.fetchall()}
    for column in ("PlannedCheckIn", "PlannedCheckOut", "PossibleCheckIn", "PossibleCheckOut"):
        assert columns[("FSE_Select", column)][0] == "timestamp without time zone"
    assert columns[("FSE_Select", "SupportEngineers")][0] == "integer" and columns[("FSE_Select", "FieldLeaderId")][0] == "uuid"
    assert [columns[("EngineersSelected", c)][1] for c in ("ContratistaNombre", "ContratistaTelefono", "ContratistaEmail", "ContratistaLocation")] == [200, 50, 300, 200]
