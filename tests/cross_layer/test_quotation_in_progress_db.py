"""HU-04 (OP-11) Quotes in Progress, API against the Postgres database (read-only), added 2026-11-10.
What the list shows is what is stored: the total of active quotations of the AM (every status but Approved), the count behind each filter value and the Item stages.
The AM sees only the quotations it created (CreadoPorEmail), so every count is taken for that account. Not part of HU-04: who may see what (HU-25)."""
import pytest

from shared.config.credentials import load_role_credentials

pytestmark = [pytest.mark.cross_layer, pytest.mark.api]

ACTIVE = ("Draft", "Awaiting", "Returned", "Rejected", "OemRejected")


def _db_count(db_conn, email, where="", args=()):
    sql = f'SELECT count(*) FROM quotation."Quotation" WHERE lower("CreadoPorEmail") = lower(%s) AND "EstadoCotizacion" = ANY(%s) {where}'
    with db_conn.cursor() as cur:
        cur.execute(sql, (email, list(ACTIVE), *args))
        return cur.fetchone()[0]


def _api_total(am, **params):
    response = am.get("/api/quotations", page=1, pageSize=1, includeClosed="false", **params)
    assert response.status_code == 200
    return response.json()["totalCount"]


@pytest.fixture(scope="module")
def am_email():
    creds = load_role_credentials("AM")
    if creds is None:
        pytest.skip("QUOTATION_AM_EMAIL not set in .env")
    return creds["email"]


def test_the_total_of_quotes_in_progress_is_the_active_quotations_stored(api_roles, db_conn, am_email):
    """Qase QP-DB1 (AC1, AC6) -- the number of the tab is the count of the AM's quotations in a non-final status in the database (Draft, Awaiting, Returned, Rejected, OemRejected)."""
    assert _api_total(api_roles["AM"]) == _db_count(db_conn, am_email)


def test_approved_quotations_are_not_in_quotes_in_progress(api_roles, db_conn, am_email):
    """Qase QP-DB2 (AC1) -- an Approved quotation is final: it is in the database but not in the active count."""
    with db_conn.cursor() as cur:
        cur.execute('SELECT count(*) FROM quotation."Quotation" WHERE lower("CreadoPorEmail") = lower(%s) AND "EstadoCotizacion" = %s', (am_email, "Approved"))
        approved = cur.fetchone()[0]
    all_states = _db_count(db_conn, am_email) + approved
    assert approved > 0 and _api_total(api_roles["AM"]) == all_states - approved


@pytest.mark.parametrize("stage, api_value", [("Quoting", "Quoting"), ("BU Reviewing", "BU Reviewing"), ("Vendor Reviewing", "Vendor Reviewing")])
def test_each_item_stage_counts_what_is_stored(api_roles, db_conn, am_email, stage, api_value):
    """Qase QP-DB3 (AC3, AC6) -- the Item filter counts the quotations whose EtapaWorkflow is that stage."""
    assert _api_total(api_roles["AM"], workflowStage=api_value) == _db_count(db_conn, am_email, 'AND "EtapaWorkflow" = %s', (stage,))


# Qase #226 (OP-192): FIXED, verified 2026-11-19 (before, choosing 'Acme' listed 13 quotations because the OEM filter matched by contained text; now it matches the whole name).
@pytest.mark.parametrize("param, column", [("oemName", "OemName"), ("siteName", "SiteName"), ("typeOfWork", "TypeOfWork")])
def test_each_filter_value_counts_what_is_stored(api_roles, db_conn, am_email, param, column):
    """Qase QP-DB4 (Site, Type) and QP-DB5 (OEM, defect #226) (AC2, AC6) -- for the first values of OEM, Site and Type, the count behind the filter equals the database (the filter ignores the case and the outer spaces)."""
    with db_conn.cursor() as cur:
        cur.execute(f'SELECT DISTINCT trim("{column}") FROM quotation."Quotation" WHERE lower("CreadoPorEmail") = lower(%s) AND "EstadoCotizacion" = ANY(%s) AND trim("{column}") <> \'\' '
                    f'ORDER BY 1 LIMIT 4', (am_email, list(ACTIVE)))
        values = [row[0] for row in cur.fetchall()]
    assert values
    for value in values:
        stored = _db_count(db_conn, am_email, f'AND lower(trim("{column}")) = lower(%s)', (value,))
        assert _api_total(api_roles["AM"], **{param: value}) == stored, f"{param}={value!r}"
