"""HU-16 (OP-24) SIGNER ASSIGNMENT, API against the Postgres database (read-only), added 2026-11-09 for the regression of Sprint 1.
What the server assigns and saves as approvers must be what is stored in quotation."Approvers" (role, name, email, EsAutoAsignado)."""
import pytest

from framework_api.services import quotation_setup as qs
from framework_api.services.quotation_service import QuotationService
from shared.datasource.quotation_db_source import get_approvers_by_quote_no

pytestmark = [pytest.mark.cross_layer, pytest.mark.api]

BASE_TOTAL = 8410


def _hotel_for(total):
    return {"hotelCost": 1050 + (total - BASE_TOTAL)}


@pytest.mark.parametrize("total, role", [(50000, "FPM_FSM"), (100000, "BU"), (500000, "BU"), (500008, "CEO")], ids=["50k", "100,000", "500,000", "500,008"])
def test_the_default_approver_is_stored_as_auto_assigned(api_roles, db_conn, total, role):
    """Qase #940 / #960: the approver the system assigns for the amount is stored once, Pending, with EsAutoAsignado true and the role of the threshold."""
    am = api_roles["AM"]
    quotation_id, quote_no = qs.create_and_submit(am, api_roles, f"DB{total}", ["FPM"], arrangement=_hotel_for(total), title_prefix="HU16-API", extra={"approvers": []}, submit=False)
    assert QuotationService(am).submit(quotation_id).status_code == 200
    rows = get_approvers_by_quote_no(db_conn, quote_no)
    assert [(r["Rol"], r["EsAutoAsignado"], r["Estado"]) for r in rows] == [(role, True, "Pending")], rows


def test_the_oem_contact_is_stored_as_an_external_not_auto_assigned_approver(api_roles, db_conn):
    """Qase #938: the OEM contact saved through the API is stored with role OEM, EsAutoAsignado false, after the internal approver."""
    am = api_roles["AM"]
    quotation_id, quote_no = qs.create_draft(am, api_roles, "SIGDB", title_prefix="HU16-API")
    body = am.get(f"/api/quotations/{quotation_id}").json()
    body["approvers"] = body["approvers"][:1] + [{"workflowStage": "Vendor Reviewing", "order": 1, "role": "OEM", "userId": None, "userName": "Zzz Oem Db", "email": "oem.db@example.com",
                                                   "status": "Pending", "isAutoAssigned": False}]
    assert am.session.put(f"{am.base_url}/api/quotations/{quotation_id}", json=body, timeout=90).status_code == 200
    rows = get_approvers_by_quote_no(db_conn, quote_no)
    assert [r["Rol"] for r in rows] == ["FPM_FSM", "OEM"] and rows[1]["NombreUsuario"] == "Zzz Oem Db" and rows[1]["Email"] == "oem.db@example.com" and rows[1]["EsAutoAsignado"] is False


def test_the_approver_columns_hold_what_the_server_accepts(db_conn):
    """Qase #948: the approver name and email columns are 200 and 300 characters, the limits the server applies."""
    with db_conn.cursor() as cur:
        cur.execute("SELECT column_name, character_maximum_length FROM information_schema.columns WHERE table_schema = 'quotation' AND table_name = 'Approvers' AND column_name IN ('NombreUsuario', 'Email')")
        sizes = dict(cur.fetchall())
    assert sizes == {"NombreUsuario": 200, "Email": 300}


def test_the_default_rules_table_holds_the_three_thresholds(api_roles, db_conn):
    """OP-24 AC #3 / #6: quotation."ApprovalDefaultRules" holds the three active thresholds (0 to 100,000 no required role; 100,000 to 500,000 BU; above 500,000 CEO), the same ones
    GET /api/quotations/approval-default-rules answers."""
    with db_conn.cursor() as cur:
        cur.execute('SELECT "MinAmount", "MaxAmount", "RequiredApproverRole", "DefaultApproverEmployeeId", "IsActive" FROM quotation."ApprovalDefaultRules" ORDER BY "MinAmount"')
        rows = cur.fetchall()
    assert [(float(r[0]), None if r[1] is None else float(r[1]), r[2]) for r in rows] == [(0, 100000, None), (100000, 500000, "BU"), (500000, None, "CEO")] and all(r[4] and r[3] for r in rows)
    api = sorted(api_roles["AM"].get("/api/quotations/approval-default-rules").json(), key=lambda r: r["minAmount"])
    assert [r["defaultApproverEmployeeId"] for r in api] == [r[3] for r in rows]


@pytest.mark.parametrize("total", [50000, 100000, 500008], ids=["50k", "100,000", "500,008"])
def test_the_stored_default_approver_is_the_one_of_the_rule(api_roles, db_conn, total):
    """OP-24 AC #1: the approver the system stores for an amount is the default approver of the rule of that amount (UsuarioId = DefaultApproverEmployeeId)."""
    am = api_roles["AM"]
    quotation_id, quote_no = qs.create_and_submit(am, api_roles, f"RULE{total}", ["FPM"], arrangement=_hotel_for(total), title_prefix="HU16-API", extra={"approvers": []}, submit=False)
    assert QuotationService(am).submit(quotation_id).status_code == 200
    with db_conn.cursor() as cur:
        cur.execute('SELECT "DefaultApproverEmployeeId" FROM quotation."ApprovalDefaultRules" WHERE "MinAmount" <= %s AND ("MaxAmount" IS NULL OR "MaxAmount" > %s OR (%s = 100000 AND "MinAmount" = 100000)) ORDER BY "MinAmount" DESC LIMIT 1', (total, total, total))
        expected = cur.fetchone()[0]
    rows = get_approvers_by_quote_no(db_conn, quote_no)
    with db_conn.cursor() as cur:
        cur.execute('SELECT a."UsuarioId" FROM quotation."Approvers" a JOIN quotation."Quotation" q ON q."Id" = a."QuotationId" WHERE q."QuoteNo" = %s', (quote_no,))
        stored = [r[0] for r in cur.fetchall()]
    assert len(rows) == 1 and stored == [expected], f"stored {stored}, rule {expected}"
