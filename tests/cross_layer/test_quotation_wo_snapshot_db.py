"""HU-08 (OP-19) WO Snapshot, API against the Postgres database (read-only), added 2026-11-06 for the regression of Sprint 1.
The values saved through the API must be the ones stored, and the limits of the free-text fields (Qase #961, defect #143) must be the size of the columns."""
import pytest

pytestmark = [pytest.mark.cross_layer, pytest.mark.api]

# API field -> (column of quotation."Quotation", limit that the screen and the server apply)
FIELDS = {"oemName": ("OemName", 200), "title": ("Title", 300), "siteLocation": ("SiteLocation", 500), "unitInfo": ("UnitInfo", 200), "device": ("Device", 200)}


def _row(db_conn, quotation_id, column):
    with db_conn.cursor() as cur:
        cur.execute(f'SELECT "{column}" FROM quotation."Quotation" WHERE "Id" = %s', (quotation_id,))
        return cur.fetchone()[0]


@pytest.mark.parametrize("field", list(FIELDS), ids=list(FIELDS))
def test_the_limit_of_each_text_field_is_the_size_of_its_column(db_conn, field):
    column, limit = FIELDS[field]
    with db_conn.cursor() as cur:
        cur.execute("SELECT character_maximum_length FROM information_schema.columns WHERE table_schema = 'quotation' AND table_name = 'Quotation' AND column_name = %s", (column,))
        assert cur.fetchone()[0] == limit, f"the column {column} is not {limit} characters long"


def test_the_values_saved_through_the_api_are_the_ones_stored(api_roles, make_draft, db_conn):
    """Qase #797: a text at the limit in each field, Units and Type Of Work are stored exactly as sent."""
    quotation_id, _ = make_draft("WOSNAPDB", title_prefix="HU08-API")
    am = api_roles["AM"]
    body = am.get(f"/api/quotations/{quotation_id}").json()
    values = {field: "B" * limit for field, (_, limit) in FIELDS.items()}
    body.update(values, units=7, typeOfWork="Rework")
    assert am.session.put(f"{am.base_url}/api/quotations/{quotation_id}", json=body, timeout=90).status_code == 200
    for field, (column, limit) in FIELDS.items():
        stored = _row(db_conn, quotation_id, column)
        assert stored == values[field], f"{column}: stored {len(stored or '')} characters, expected {limit}"
    assert _row(db_conn, quotation_id, "Unites") == 7
    assert _row(db_conn, quotation_id, "TypeOfWork") == "Rework"
