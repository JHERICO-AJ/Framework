"""HU-09 (OP-20) FSE Arrangement, API against the Postgres database (read-only), added 2026-11-06 for the regression of Sprint 1.
What the API saves must be what is stored, the stored totals must be the ones of the formulas, and the columns must hold the amounts the form allows."""
import pytest

pytestmark = [pytest.mark.cross_layer, pytest.mark.api]

CALC = dict(supportEngineers=2, workingHourTechDay=4, estimatedWorkingDays=2, totalOverHoursTech=2, laborCostHour=45, laborOverCostHour=60, hotelCost=10, perDiem=5,
            travelDriveTime=10, airTransportation=1, carExpense=2, materialExpense=3, equipmentRental=4, miscellaneous=5)
COLUMNS = {"supportEngineers": "SupportEngineers", "workingHourTechDay": "WorkingHourTechDay", "estimatedWorkingDays": "EstimatedWorkingDays", "totalOverHoursTech": "TotalOverHoursTech",
           "laborCostHour": "LaborCostHour", "laborOverCostHour": "LaborOverCostHour", "hotelCost": "HotelCost", "perDiem": "PerDiem", "travelDriveTime": "TravelDriveTime",
           "airTransportation": "AirTransportation", "carExpense": "CarExpense", "materialExpense": "MaterialExpense", "equipmentRental": "EquipmentRental", "miscellaneous": "Miscellaneous",
           "totalWorkingHourTech": "TotalWorkingHourTech", "totalDays": "TotalDays", "laborSubtotal": "LaborSubtotal", "onsiteSubtotal": "OnsiteSubtotal", "travelDriveCosto": "TravelDriveCosto",
           "reimbursableSubtotal": "ReimbursableSubtotal", "grandTotal": "GrandTotal"}


def _row(db_conn, quotation_id):
    columns = ", ".join(f'"{c}"' for c in COLUMNS.values())
    with db_conn.cursor() as cur:
        cur.execute(f'SELECT {columns}, "MiscellaneousNota" FROM quotation."FSE_Arrangement" WHERE "QuotationId" = %s', (quotation_id,))
        row = cur.fetchone()
    return dict(zip(list(COLUMNS) + ["miscellaneousNote"], row))


def test_the_values_and_the_totals_saved_through_the_api_are_the_ones_stored(api_roles, make_draft, db_conn):
    """Qase #841 / #846: every field sent, every total the server calculated and the note are stored exactly as the API returns them."""
    quotation_id, _ = make_draft("FSEDB", title_prefix="HU09-API")
    am = api_roles["AM"]
    body = am.get(f"/api/quotations/{quotation_id}").json()
    body["arrangement"].update(CALC, miscellaneousNote="Spare fuses")
    assert am.session.put(f"{am.base_url}/api/quotations/{quotation_id}", json=body, timeout=90).status_code == 200
    api_values = am.get(f"/api/quotations/{quotation_id}").json()["arrangement"]
    stored = _row(db_conn, quotation_id)
    for field in COLUMNS:
        assert float(stored[field]) == float(api_values[field]), f"{field}: stored {stored[field]}, API {api_values[field]}"
    assert stored["miscellaneousNote"] == "Spare fuses"
    assert float(stored["grandTotal"]) == 1035 and float(stored["laborSubtotal"]) == 960 and float(stored["onsiteSubtotal"]) == 60


def test_the_money_columns_hold_what_the_form_allows(db_conn):
    """Qase #856: the amount columns are numeric(18,2) (far above the 6-digit limit of the screen) and the counts are integers; the note is text."""
    with db_conn.cursor() as cur:
        cur.execute("SELECT column_name, data_type, numeric_precision FROM information_schema.columns WHERE table_schema = 'quotation' AND table_name = 'FSE_Arrangement'")
        types = {name: (kind, precision) for name, kind, precision in cur.fetchall()}
    for column in ("HotelCost", "PerDiem", "LaborCostHour", "LaborSubtotal", "GrandTotal"):
        assert types[column] == ("numeric", 18), column
    assert types["SupportEngineers"][0] == "integer" and types["EstimatedWorkingDays"][0] == "integer"
    assert types["MiscellaneousNota"][0] == "text"
