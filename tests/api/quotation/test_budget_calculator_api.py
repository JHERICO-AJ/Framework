"""Quotation module -- Budget Calculator, database and server side (HU-12 'Automated resource and overtime calculation'; Qase suite "HU-12: Automated resource and overtime calculation",
cases BC-DB* and BC-API*).

Only the HU-12 text decides what must happen. Server-side: 'When the quotation is saved, the server recalculates every total from the entered values. The server rejects a negative or fractional
value, an item with a price and no description, a description over 200 characters, more than 100 items per sheet and a total too large to store, with a message naming the engineer, tab and
field. The quotation's amount used to choose the approval level is the Quotation (Income) Grand Total; while the calculator is empty it is a nominal $1.' The AM can edit while the quotation
is Draft, Rejected or Returned; in any other status the calculator is read-only.
What the figures are: PUT /api/quotations/<id>, select.selectedEngineers[].costs[] (tab 'quotation' | 'expense'). Tables: quotation."EngineersSelected" -> "CostoEnginner" (one row per engineer
and tab) -> "CostoItem"; the amount is quotation."Quotation"."MontoTotal".
Observed on the QA build of 2026-11-09: every rule below is enforced with a message that names the engineer BY NAME, the tab and the field ('Pedro Aguilar - Quotation (Income), item 1: Qty can't
be negative.'); the Grand Total limit says 'Quotation (Income): Grand Total is too large to store.' (fixes of OP-173 and OP-174).
"""
import copy
import re

import pytest
from psycopg2.extras import RealDictCursor

from framework_api.services import quotation_setup as qs
from framework_api.services.quotation_service import QuotationService
from tests.api.quotation.calc_draft import Calc, put

pytestmark = pytest.mark.api

Q = qs.engineer_cost
FIELDS = [("hourlyRate", "Hourly Rate"), ("totalHours", "Total Hours"), ("otHourlyRate", "OT Hourly Rate"), ("otTotalHours", "OT Total Hours"), ("travelFlight", "Flight"),
          ("travelCar", "Car Rental"), ("travelHotel", "Hotel"), ("travelMeals", "Meals"), ("travelGas", "Gas"), ("travelParking", "Parking"), ("travelToll", "Toll"), ("travelOther", "Other")]
NO_EXPENSE = "OUT OF SCOPE: the Expense tab of the Budget Calculator was removed from the screen ('The expense fields have been removed for now', OP-131); a server rule is not checked for a tab nobody can use"
TABS = ["quotation", pytest.param("expense", marks=pytest.mark.skip(reason=NO_EXPENSE))]
TAB_LABEL = {"quotation": "Quotation (Income)", "expense": "Expense"}   # the server names the tab like the screen since the build of 2026-11-09
LIMIT_DIGITS = 10 ** 15


def messages(r):
    body = r.json()
    return [m for msgs in (body.get("details") or {}).values() if isinstance(msgs, list) for m in msgs]


def by_name(body, name):
    return next(e for e in body["select"]["selectedEngineers"] if e["contractorName"] == name)


def cost(engineer, tab="quotation"):
    return next(c for c in engineer["costs"] if c["tab"] == tab)


def figures(body):
    """{(engineer name, tab): {field: value}} of what the server holds (by name: the server does not return the engineers in the order they were sent)."""
    return {(e["contractorName"], c["tab"]): {k: c[k] for k in c if k not in ("id", "selectedEngineerId", "items")} | {"items": sorted((x["section"], x["description"], x["quantity"], x["unitCost"]) for x in c["items"])}
            for e in body["select"]["selectedEngineers"] for c in e["costs"]}


@pytest.fixture(scope="module")
def am(api_roles):
    return api_roles["AM"]


@pytest.fixture(scope="module")
def calc(am, api_roles):
    return Calc(am, api_roles)


def set_field(engineer_index, tab, field, value):
    return lambda es, b: cost(es[engineer_index], tab).__setitem__(field, value)


def assert_refused_unchanged(calc, r, *fragments):
    assert r.status_code == 400, f"{r.status_code} {r.text[:300]}"
    text = " | ".join(messages(r))
    for fragment in fragments:
        assert fragment in text, f"{fragment!r} not in {text!r}"
    assert re.search(r"Pedro Aguilar|Employee L01200", text), f"the message must name the engineer BY NAME: {text!r}"
    assert figures(calc.read()) == figures(calc.body), "a refused save must change nothing"


# ===================================================================================================== SERVER (BC-API*)

def test_the_server_recalculates_every_total_and_ignores_the_totals_sent(am, api_roles):
    """Qase BC-API1 -- the totals typed in a direct request (1) are ignored and every total is recalculated from the entered values."""
    c = Calc(am, api_roles, "RECALC")

    def change(es, b):
        cost(es[c.pedro]).update(hourlyRate=90, serviceTotal=1, allServiceTotal=1, purchaseTotal=1, personalTotal=1, grandConfirmed=1)
    assert c.send(change).status_code == 200
    stored = cost(by_name(c.read(), "Pedro Aguilar"))
    assert (stored["serviceTotal"], stored["otServiceTotal"], stored["allServiceTotal"], stored["purchaseTotal"], stored["travelTotal"], stored["miscTotal"], stored["personalTotal"]) == \
        (1800, 0, 1800, 99, 0, 0, 1899)
    first = cost(by_name(c.read(), "Employee L01200"))
    assert (first["serviceTotal"], first["otServiceTotal"], first["allServiceTotal"], first["purchaseTotal"], first["travelTotal"], first["miscTotal"], first["personalTotal"]) == \
        (1000, 600, 1600, 500, 1975, 150, 4225)


@pytest.mark.parametrize("tab", TABS)
@pytest.mark.parametrize("field, label", FIELDS)
def test_the_server_rejects_a_negative_value_naming_the_engineer_tab_and_field(calc, tab, field, label):
    """Qase BC-API2 (12 fields x 2 tabs)."""
    assert_refused_unchanged(calc, calc.send(set_field(calc.pedro, tab, field, -1)), TAB_LABEL[tab], f"{label} can't be negative")


@pytest.mark.parametrize("tab", TABS)
@pytest.mark.parametrize("field, label", FIELDS)
def test_the_server_rejects_a_fractional_value_naming_the_engineer_tab_and_field(calc, tab, field, label):
    """Qase BC-API3 (12 fields x 2 tabs)."""
    assert_refused_unchanged(calc, calc.send(set_field(calc.pedro, tab, field, 2.5)), TAB_LABEL[tab], f"{label} must be a whole number")


@pytest.mark.parametrize("tab", TABS)
@pytest.mark.parametrize("field, label, value, text", [("quantity", "Qty", -1, "can't be negative"), ("quantity", "Qty", 1.5, "must be a whole number"),
                                                        ("unitCost", "Price", -1, "can't be negative"), ("unitCost", "Price", 1.5, "must be a whole number")])
@pytest.mark.parametrize("section", ["EQUIPMENT", "MISCELLANEOUS"])
def test_the_server_rejects_a_negative_or_fractional_item_quantity_or_price(calc, section, field, label, value, text, tab):
    """Qase BC-API4 (Equipment and Miscellaneous, Qty and Price, negative and fractional, both tabs)."""
    def add(es, b):
        cost(es[calc.pedro], tab)["items"] = [dict(section=section, description="Spare fuse", quantity=1, unitCost=10, order=0)]
        cost(es[calc.pedro], tab)["items"][0][field] = value
    r = calc.send(add)
    assert r.status_code == 400, f"{r.status_code} {r.text[:300]}"
    text_ = " | ".join(messages(r))
    assert TAB_LABEL[tab] in text_ and "item 1" in text_ and f"{label} {text}" in text_, text_


@pytest.mark.parametrize("tab", TABS)
@pytest.mark.parametrize("section", ["EQUIPMENT", "MISCELLANEOUS"])
@pytest.mark.parametrize("description", ["", "   "])
def test_the_server_rejects_an_item_with_a_price_and_no_description(calc, section, description, tab):
    """Qase BC-API5 (empty and only spaces, Equipment and Miscellaneous, both tabs)."""
    def add(es, b):
        cost(es[calc.pedro], tab)["items"] = [dict(section=section, description=description, quantity=1, unitCost=99, order=0)]
    assert_refused_unchanged(calc, calc.send(add), TAB_LABEL[tab], "item 1", "an item with a price needs a description")


@pytest.mark.parametrize("tab", TABS)
def test_the_server_accepts_a_description_of_200_characters_and_rejects_201(calc, am, tab):
    """Qase BC-API6"""
    def with_description(n):
        return lambda es, b: cost(es[calc.pedro], tab).__setitem__("items", [dict(section="EQUIPMENT", description="A" * n, quantity=1, unitCost=99, order=0)])
    assert_refused_unchanged(calc, calc.send(with_description(201)), TAB_LABEL[tab], "item 1", "description must be 200 characters or fewer")
    assert calc.send(with_description(200)).status_code == 200
    assert len(cost(by_name(calc.read(), "Pedro Aguilar"), tab)["items"][0]["description"]) == 200
    assert calc.send(lambda es, b: None).status_code == 200      # leave the draft as it was for the next tests
    assert figures(calc.read()) == figures(calc.body)


@pytest.mark.parametrize("tab", TABS)
def test_the_server_accepts_100_items_per_sheet_and_rejects_101(calc, tab):
    """Qase BC-API7 -- 50 Equipment + 50 Miscellaneous are accepted; 51 + 50 and 100 + 1 are rejected."""
    def items(equipment, misc):
        return lambda es, b: cost(es[calc.pedro], tab).__setitem__("items", [dict(section="EQUIPMENT", description=f"E{i}", quantity=1, unitCost=1, order=i) for i in range(equipment)] +
                                                          [dict(section="MISCELLANEOUS", description=f"M{i}", quantity=1, unitCost=1, order=i) for i in range(misc)])
    for equipment, misc in ((51, 50), (100, 1)):
        r = calc.send(items(equipment, misc))
        assert r.status_code == 400 and "no more than 100 items" in " | ".join(messages(r)) and TAB_LABEL[tab] in " | ".join(messages(r)), r.text[:300]
    assert calc.send(items(50, 50)).status_code == 200
    assert len(cost(by_name(calc.read(), "Pedro Aguilar"), tab)["items"]) == 100
    assert calc.send(lambda es, b: None).status_code == 200


@pytest.mark.parametrize("tab", TABS)
def test_the_server_rejects_a_personal_total_too_large_to_store(calc, tab):
    """Qase BC-API8 -- rate x hours that cannot be stored: 400 with a message that names the engineer, the tab and the total, never a server error."""
    def huge(es, b):
        cost(es[calc.pedro], tab).update(hourlyRate=2 * 10 ** 9, totalHours=2 * 10 ** 9)
    assert_refused_unchanged(calc, calc.send(huge), TAB_LABEL[tab], "Personal Total is too large to store")


def test_the_server_rejects_a_grand_total_too_large_to_store(calc):
    """Qase BC-API9 -- every Personal Total can be stored but they do not add up to a number that can be stored."""
    def each_nine_quadrillion(es, b):
        for e in es:
            cost(e).update(hourlyRate=9 * 10 ** 15, totalHours=1)
    r = calc.send(each_nine_quadrillion)
    assert r.status_code == 400, f"{r.status_code} {r.text[:300]}"
    assert "Quotation (Income): Grand Total is too large to store" in " | ".join(messages(r)), messages(r)
    assert figures(calc.read()) == figures(calc.body)


def test_the_quotation_amount_is_the_income_grand_total_and_not_the_expense_one(calc):
    """Qase BC-API10 -- Income: 4,225 + 1,699 = 5,924; Expense: 1,400 + 1,000 = 2,400; the amount is 5,924."""
    assert calc.read()["totalAmount"] == 5924


def test_the_quotation_amount_is_a_nominal_one_dollar_while_the_calculator_is_empty(am, api_roles):
    """Qase BC-API11"""
    qid, _ = qs.create_draft(am, api_roles, "EMPTY", title_prefix="HU12", extra=qs.select_extra(("Pedro Aguilar", None, None), ("Employee L01200", None, None)))
    assert am.get(f"{QuotationService.PATH}/{qid}").json()["totalAmount"] == 1


@pytest.mark.parametrize("status", ["Draft", "Rejected", "Returned"])
def test_the_am_can_save_calculator_figures_while_the_quotation_is_draft_rejected_or_returned(am, api_roles, status):
    """Qase BC-API12 (positive)."""
    extra = qs.select_extra(("Employee L01200", Q("quotation", 100, 10), None))
    if status == "Draft":
        qid, _ = qs.create_draft(am, api_roles, "ST-D", title_prefix="HU12", extra=extra)
    elif status == "Rejected":
        qid, _ = qs.create_and_submit(am, api_roles, "ST-R", ["FPM"], title_prefix="HU12", extra=extra)
        assert QuotationService(api_roles["FPM"]).reject(qid, "Rejected for the HU-12 tests.").status_code == 200
    else:
        qid, _ = qs.create_and_submit(am, api_roles, "ST-T", ["FPM", "BU"], title_prefix="HU12", extra=extra)
        assert QuotationService(api_roles["FPM"]).approve(qid, "Approved for the HU-12 tests.").status_code == 200
    body = am.get(f"{QuotationService.PATH}/{qid}").json()
    assert body["status"] == status if "status" in body else True
    cost(body["select"]["selectedEngineers"][0])["hourlyRate"] = 120
    assert put(am, qid, body).status_code == 200
    assert am.get(f"{QuotationService.PATH}/{qid}").json()["totalAmount"] == 1200


def test_the_am_cannot_save_calculator_figures_while_the_quotation_is_awaiting(am, api_roles):
    """Qase BC-API13 -- any other status is read-only: 400 QUOTATION_NOT_EDITABLE and nothing is saved."""
    qid, _ = qs.create_and_submit(am, api_roles, "ST-A", ["FPM", "BU"], title_prefix="HU12", extra=qs.select_extra(("Employee L01200", Q("quotation", 100, 10), None)))
    body = am.get(f"{QuotationService.PATH}/{qid}").json()
    cost(body["select"]["selectedEngineers"][0])["hourlyRate"] = 777
    r = put(am, qid, body)
    assert r.status_code == 400 and (r.json().get("details") or {}).get("code") == "QUOTATION_NOT_EDITABLE", r.text[:300]
    assert am.get(f"{QuotationService.PATH}/{qid}").json()["totalAmount"] == 1000


def test_the_am_cannot_save_calculator_figures_while_the_quotation_is_approved(am):
    """Qase BC-API13 (Approved) -- Approved is what Historical Quotes lists ('Closed' is the same state): read-only, 400 QUOTATION_NOT_EDITABLE and nothing is saved. Needs the Approved FSE Select
    quotation made for HU-12 (title 'Workflow Progress test HU12-APPROVED-...', approved by the OEM from the link of its e-mail); skipped while it does not exist."""
    items = am.get(QuotationService.PATH, page=1, pageSize=100, includeClosed="true").json()["items"]
    found = next((i["id"] for i in items if "HU12-APPROVED" in i.get("title", "")), None)
    if found is None:
        pytest.skip("the OEM has not approved the quotation made for HU-12 yet")
    body = am.get(f"{QuotationService.PATH}/{found}").json()
    amount = body["totalAmount"]
    cost(body["select"]["selectedEngineers"][0])["hourlyRate"] = 777
    r = put(am, found, body)
    assert r.status_code == 400 and (r.json().get("details") or {}).get("code") == "QUOTATION_NOT_EDITABLE", r.text[:300]
    assert am.get(f"{QuotationService.PATH}/{found}").json()["totalAmount"] == amount


@pytest.mark.parametrize("role", ["FPM", "BU", "CEO"])
def test_an_approver_cannot_save_calculator_figures(am, api_roles, role):
    """Qase BC-API14 -- for approvers the calculator is read-only: 403 QUOTATION_FORBIDDEN and nothing is saved."""
    qid, _ = qs.create_and_submit(am, api_roles, "ST-AP", [role], title_prefix="HU12", extra=qs.select_extra(("Employee L01200", Q("quotation", 100, 10), None)))
    body = api_roles[role].get(f"{QuotationService.PATH}/{qid}").json()
    cost(body["select"]["selectedEngineers"][0])["hourlyRate"] = 555
    r = put(api_roles[role], qid, body)
    assert r.status_code == 403 and (r.json().get("details") or {}).get("code") == "QUOTATION_FORBIDDEN", r.text[:300]
    assert am.get(f"{QuotationService.PATH}/{qid}").json()["totalAmount"] == 1000




@pytest.mark.parametrize("tab", TABS)
def test_the_server_messages_name_the_engineer_by_name(calc, tab):
    """Qase BC-API15 -- 'a message naming the engineer, tab and field': the engineer is Pedro Aguilar, not 'Engineer 2'."""
    r = calc.send(set_field(calc.pedro, tab, "hourlyRate", -1))
    assert r.status_code == 400
    assert "Pedro Aguilar" in " | ".join(messages(r)), messages(r)


def test_the_grand_total_message_names_the_tab_and_the_total(calc):
    """Qase BC-API16 -- the refusal of a total too large to store names what is too large: the message must say it is the Grand Total of the tab (Quotation / Income)."""
    def each(es, b):
        for e in es:
            cost(e).update(hourlyRate=9 * 10 ** 15, totalHours=1)
    r = calc.send(each)
    text = " | ".join(messages(r))
    assert r.status_code == 400 and "Grand Total" in text and "quotation" in text.lower(), text


@pytest.mark.parametrize("quantity", [1, 3])
def test_a_row_with_no_description_and_a_price_of_zero_is_ignored_when_the_quotation_is_saved(calc, quantity):
    """Qase BC-API17 -- the server saves the quotation and drops the row (whatever its Qty) instead of refusing it."""
    def add(es, b):
        cost(es[calc.pedro])["items"].append(dict(section="MISCELLANEOUS", description="", quantity=quantity, unitCost=0, order=5))
    r = calc.send(add)
    assert r.status_code == 200, f"{r.status_code} {' | '.join(messages(r))}"
    assert all(i["description"] for i in cost(by_name(calc.read(), "Pedro Aguilar"))["items"]), "the row with no description was not dropped"


# ===================================================================================================== DATABASE (BC-DB*)

def db_costs(db_conn, quotation_id):
    """[(engineer position by selection, tab, row dict)] of the figures stored for a quotation."""
    with db_conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute('SELECT es."Id"::text eid, es."ContratistaNombre" name, c."Id"::text cid, c.* FROM quotation."FSE_Select" f JOIN quotation."EngineersSelected" es ON es."FseSelectId" = f."Id" '
                    'JOIN quotation."CostoEnginner" c ON c."EngineersSelectedId" = es."Id" WHERE f."QuotationId" = %s ORDER BY c."Tab", es."ContratistaNombre"', (quotation_id,))
        rows = [dict(r) for r in cur.fetchall()]
        for r in rows:
            cur.execute('SELECT "Seccion", "Descripcion", "Cantidad", "CostoUnitario", "Orden" FROM quotation."CostoItem" WHERE "CostoEnginnerId" = %s ORDER BY "Seccion", "Orden"', (r["cid"],))
            r["items"] = [dict(i) for i in cur.fetchall()]
    return rows


def amount(db_conn, quotation_id):
    with db_conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute('SELECT "MontoTotal" FROM quotation."Quotation" WHERE "Id" = %s', (quotation_id,))
        return float(cur.fetchone()["MontoTotal"])


def test_the_figures_are_stored_one_row_per_engineer_and_tab(calc, db_conn):
    """Qase BC-DB1 -- two engineers = two rows of the Quotation (Income) tab, each with its own figures."""
    rows = [r for r in db_costs(db_conn, calc.id) if r["Tab"] == "quotation"]   # the Expense tab is out of scope (removed from the screen)
    assert sorted(r["name"] for r in rows) == ["Employee L01200", "Pedro Aguilar"]
    by = {r["name"]: r for r in rows}
    assert (float(by["Employee L01200"]["HourlyRate"]), float(by["Pedro Aguilar"]["HourlyRate"])) == (100, 80)


def test_the_totals_stored_are_the_ones_the_formulas_give(calc, db_conn):
    """Qase BC-DB2 -- Service = rate x hours, OT = rate x hours, All Service = both, Travel = the eight fields, Personal = All Service + Purchase + Travel + Misc."""
    for r in db_costs(db_conn, calc.id):
        n = lambda k: float(r[k])
        assert n("ServiceTotal") == n("HourlyRate") * n("TotalHours")
        assert n("OtServiceTotal") == n("OtHourlyRate") * n("OtTotalHours")
        assert n("AllServiceTotal") == n("ServiceTotal") + n("OtServiceTotal")
        assert n("TravelTotal") == sum(n(k) for k in ("TravelFlight", "TravelCar", "TravelHotel", "TravelMeals", "TravelGas", "TravelParking", "TravelToll", "TravelOther"))
        purchase = sum(float(i["Cantidad"]) * float(i["CostoUnitario"]) for i in r["items"] if i["Seccion"] == "EQUIPMENT")
        misc = sum(float(i["Cantidad"]) * float(i["CostoUnitario"]) for i in r["items"] if i["Seccion"] == "MISCELLANEOUS")
        assert (n("PurchaseTotal"), n("MiscTotal")) == (purchase, misc)
        assert n("PersonalTotal") == n("AllServiceTotal") + n("PurchaseTotal") + n("TravelTotal") + n("MiscTotal")


def test_the_items_are_stored_with_section_description_quantity_and_price(calc, db_conn):
    """Qase BC-DB3"""
    rows = {(r["name"], r["Tab"]): r for r in db_costs(db_conn, calc.id)}
    equipment = rows["Employee L01200", "quotation"]["items"]
    assert [(i["Seccion"], i["Descripcion"], float(i["Cantidad"]), float(i["CostoUnitario"])) for i in equipment] == [("EQUIPMENT", "Tool", 1, 500), ("MISCELLANEOUS", "Misc", 1, 150)]


def test_the_quotation_amount_stored_is_the_income_grand_total(calc, db_conn):
    """Qase BC-DB4 -- MontoTotal = the sum of the Personal Totals of the tab 'quotation' (5,924)."""
    rows = db_costs(db_conn, calc.id)
    assert amount(db_conn, calc.id) == sum(float(r["PersonalTotal"]) for r in rows if r["Tab"] == "quotation") == 5924


def test_the_nominal_amount_of_an_empty_calculator_is_stored(am, api_roles, db_conn):
    """Qase BC-DB5 -- no figures confirmed: MontoTotal is 1."""
    qid, _ = qs.create_draft(am, api_roles, "EMPTYDB", title_prefix="HU12", extra=qs.select_extra(("Pedro Aguilar", None, None)))
    assert amount(db_conn, qid) == 1


def test_every_amount_stored_is_a_whole_number(calc, db_conn):
    """Qase BC-DB6 -- amounts and hours have no decimals in the database."""
    for r in db_costs(db_conn, calc.id):
        for k, v in r.items():
            if k not in ("items", "name", "eid", "cid", "Id", "EngineersSelectedId", "Tab") and v is not None:
                assert float(v) == int(float(v)), (k, v)
        for i in r["items"]:
            assert float(i["Cantidad"]) == int(float(i["Cantidad"])) and float(i["CostoUnitario"]) == int(float(i["CostoUnitario"]))


def test_a_refused_save_leaves_the_database_as_it_was(calc, db_conn):
    """Qase BC-DB7 -- a request refused by the server (negative rate) changes no row and not the amount."""
    before = ([{k: v for k, v in r.items() if k not in ("cid",)} for r in db_costs(db_conn, calc.id)], amount(db_conn, calc.id))
    assert calc.send(set_field(calc.pedro, "quotation", "hourlyRate", -1)).status_code == 400
    after = ([{k: v for k, v in r.items() if k not in ("cid",)} for r in db_costs(db_conn, calc.id)], amount(db_conn, calc.id))
    assert after == before


def test_removing_an_engineer_removes_the_figures_of_that_engineer(am, api_roles, db_conn):
    """Qase BC-DB8 -- the quotation is saved without Pedro Aguilar: his rows (and their items) are gone, the other engineer keeps his."""
    c = Calc(am, api_roles, "REMOVE")
    assert len([r for r in db_costs(db_conn, c.id) if r["Tab"] == "quotation"]) == 2
    assert c.send(lambda es, b: (es.pop(c.pedro), b["select"].update(supportEngineers=1))).status_code == 200
    rows = db_costs(db_conn, c.id)
    assert {r["name"] for r in rows if r["Tab"] == "quotation"} == {"Employee L01200"}
    assert amount(db_conn, c.id) == 4225
