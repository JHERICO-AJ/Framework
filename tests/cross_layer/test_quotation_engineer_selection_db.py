"""HU-11 (OP-29) ENGINEER SELECTION MAP, API against the Postgres database (read-only), added 2026-11-09 for the regression of Sprint 1.
What the API saves for an external contractor must be what is stored, and the employee catalog the map reads must be what the database holds when it is the source."""
import pytest

from framework_api.services import quotation_setup as qs

pytestmark = [pytest.mark.cross_layer, pytest.mark.api]

E = list(qs.ENGINEERS)


def _contractor():
    return dict(isContractor=True, isLeader=False, contractorName="Ext DB Contractor", contractorPhone="+591 700 99999", contractorEmail="ext.db@example.com",
                contractorLocation="Santa Cruz", availabilityStatus="available", costs=[])


def test_a_contractor_saved_through_the_api_is_the_one_stored(api_roles, make_draft, db_conn):
    """Qase #904: name, phone, email and location of the contractor are stored exactly as sent, after the 2 selected engineers, with no leader flag."""
    am = api_roles["AM"]
    quotation_id, _ = make_draft("ENGSELDB", title_prefix="HU11-API", extra=qs.select_extra((E[0], None, None), (E[1], None, None)))
    body = am.get(f"/api/quotations/{quotation_id}").json()
    body["select"]["selectedEngineers"].append(_contractor())
    assert am.session.put(f"{am.base_url}/api/quotations/{quotation_id}", json=body, timeout=90).status_code == 200
    with db_conn.cursor() as cur:
        cur.execute('SELECT e."ContratistaNombre", e."ContratistaTelefono", e."ContratistaEmail", e."ContratistaLocation", e."EsLider" FROM quotation."EngineersSelected" e '
                    'JOIN quotation."FSE_Select" s ON s."Id" = e."FseSelectId" WHERE s."QuotationId" = %s ORDER BY e."Order"', (quotation_id,))
        rows = cur.fetchall()
    assert [r[0] for r in rows] == [E[0], E[1], "Ext DB Contractor"]
    assert rows[-1][:4] == ("Ext DB Contractor", "+591 700 99999", "ext.db@example.com", "Santa Cruz") and rows[-1][4] is False and [r[4] for r in rows] == [True, False, False]


def test_removing_a_contractor_removes_its_row(api_roles, make_draft, db_conn):
    """Qase #902: deselecting a candidate takes it out of the selection (no orphan row stays in the database)."""
    am = api_roles["AM"]
    quotation_id, _ = make_draft("ENGSELDEL", title_prefix="HU11-API", extra=qs.select_extra((E[0], None, None), (E[1], None, None)))
    body = am.get(f"/api/quotations/{quotation_id}").json()
    body["select"]["selectedEngineers"].append(_contractor())
    assert am.session.put(f"{am.base_url}/api/quotations/{quotation_id}", json=body, timeout=90).status_code == 200
    body = am.get(f"/api/quotations/{quotation_id}").json()
    body["select"]["selectedEngineers"] = body["select"]["selectedEngineers"][:2]
    assert am.session.put(f"{am.base_url}/api/quotations/{quotation_id}", json=body, timeout=90).status_code == 200
    with db_conn.cursor() as cur:
        cur.execute('SELECT e."ContratistaNombre" FROM quotation."EngineersSelected" e JOIN quotation."FSE_Select" s ON s."Id" = e."FseSelectId" WHERE s."QuotationId" = %s ORDER BY e."Order"', (quotation_id,))
        assert [r[0] for r in cur.fetchall()] == E[:2]


def test_the_contractor_columns_hold_what_the_server_accepts(db_conn):
    """Qase #910: the contractor name/phone/email/location columns are 200/50/300/200 characters, the limits the server applies (the screen stops at 100/30/-/120)."""
    with db_conn.cursor() as cur:
        cur.execute("SELECT column_name, character_maximum_length FROM information_schema.columns WHERE table_schema = 'quotation' AND table_name = 'EngineersSelected' "
                    "AND column_name IN ('ContratistaNombre', 'ContratistaTelefono', 'ContratistaEmail', 'ContratistaLocation')")
        sizes = dict(cur.fetchall())
    assert sizes == {"ContratistaNombre": 200, "ContratistaTelefono": 50, "ContratistaEmail": 300, "ContratistaLocation": 200}
