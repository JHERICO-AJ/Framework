"""QuotationSetup -- create + submit a quotation entirely through the API (no browser). Shared by the Quotation UI and API tests."""
from __future__ import annotations

import time

from framework_api.services.quotation_service import ROLE_CODE, QuotationService
from shared.config.settings import OEM_TEST_EMAIL, OEM_TEST_NAME

# What the form sends when a customer ('Andes Renewables SpA') and its site ('Valle Verde') are chosen (captured 2026-10-21).
CUSTOMER = {"customerId": 6, "customerName": "Andes Renewables SpA"}
SITE = {"siteName": "Valle Verde", "siteProjectId": 7, "siteLocation": "Camino El Sol 450, Rancagua", "siteLatitude": -34.1708, "siteLongitude": -70.7443}
DISPLAY_NAME = {"FPM": "QA Jhe FPM", "BU": "QA Jhe BU", "CEO": "QA Jhe CEO"}
ARRANGEMENT = {"estimacionStartTime": "2026-10-01", "estimacionEndTime": "2026-10-01", "supportEngineers": 2, "workingHourTechDay": 8,
               "estimatedWorkingDays": 2, "totalOverHoursTech": 0, "laborCostHour": 50, "laborOverCostHour": 0, "hotelCost": 1050, "perDiem": 520,
               "travelDriveTime": 0, "airTransportation": 3100, "carExpense": 580, "materialExpense": 0, "equipmentRental": 0, "miscellaneous": 0}


def create_and_submit(am_session, approver_sessions, tag, route, arrangement=None, title_prefix="HU22-API", extra=None, submit=True):
    """The AM creates and submits a quotation (total under $100,000) whose only signers are `route` (['FPM'], ['BU', 'CEO']...), in that
    order. `arrangement` overrides fields of the default FSE Arrangement; `extra` overrides top-level fields (siteLocation, units, unitInfo...). Returns (quotation id, quote no). Titles start with 'Workflow Progress test' so the QA cleanup pattern also finds them."""
    svc = QuotationService(am_session)
    quote_no = svc.next_quote_number(CUSTOMER["customerId"], CUSTOMER["customerName"])
    approvers = [{"workflowStage": "", "order": i, "role": ROLE_CODE[r], "userId": approver_sessions[r].user_id, "userName": DISPLAY_NAME[r],
                  "email": approver_sessions[r].email, "status": "Pending", "isAutoAssigned": False} for i, r in enumerate(route)]
    payload = {"quoteNo": quote_no, "oemName": "Workflow Progress Test OEM", **CUSTOMER,
               "title": f"Workflow Progress test {title_prefix}-{tag}-{time.time_ns() // 1000000 % 10**9}", **SITE, "typeOfWork": "Commissioning", "units": 0,
               "arrangementType": "Arrangement", "source": "MANUAL", "arrangement": {**ARRANGEMENT, **(arrangement or {})}, "attachments": [], "approvers": approvers, **(extra or {})}
    if payload["arrangementType"] == "Select":
        payload.pop("arrangement")          # the server refuses an Arrangement block on an FSE Select quotation
    created = svc.create(payload)
    quotation_id = created["id"]
    if submit:
        r = svc.submit(quotation_id)
        assert r.status_code == 200, f"submit failed: HTTP {r.status_code} {r.text[:200]}"
    return quotation_id, quote_no


# The OEM is never an OmniOps user: it signs as an EXTERNAL contact (role OEM, no userId) and decides from the link of an email (verified 2026-10-26).
# Every quotation that reaches the OEM's turn sends ONE real email to OEM_TEST_EMAIL (shared/config/settings.py) -- use only the QA test mailbox, never a real OEM address.


def oem_signer(order=3, name=OEM_TEST_NAME, email=OEM_TEST_EMAIL):
    """The approver entry of the external OEM contact, as the create/update payload takes it."""
    if not email:
        raise RuntimeError("OEM_TEST_EMAIL is not set: put the QA test mailbox address in .env (see .env.example)")
    return {"workflowStage": "Vendor Reviewing", "order": order, "role": "OEM", "userId": None, "userName": name, "email": email, "status": "Pending", "isAutoAssigned": False}


def internal_signers(api_roles):
    """The approver entries of the three internal levels (FPM/FSM, BU, CEO), in route order."""
    return [{"workflowStage": "", "order": order, "role": ROLE_CODE[role], "userId": api_roles[role].user_id, "userName": DISPLAY_NAME[role], "email": api_roles[role].email,
             "status": "Pending", "isAutoAssigned": False} for order, role in enumerate(["FPM", "BU", "CEO"])]


def drive_to_oem_turn(api_roles, quotation_id, comment):
    """Submit, FPM/FSM approves, the AM submits again, BU approves and CEO approves: the quotation now waits on the OEM (and the OEM is emailed)."""
    services = {role: QuotationService(api_roles[role]) for role in ("AM", "FPM", "BU", "CEO")}
    steps = (("AM submit", lambda: services["AM"].submit(quotation_id)), ("FPM/FSM approve", lambda: services["FPM"].approve(quotation_id, comment)),
             ("AM submit again", lambda: services["AM"].submit(quotation_id)), ("BU approve", lambda: services["BU"].approve(quotation_id, comment)),
             ("CEO approve", lambda: services["CEO"].approve(quotation_id, comment)))
    for name, call in steps:
        response = call()
        assert response.status_code == 200, f"{name} failed: HTTP {response.status_code} {response.text[:200]}"


def create_waiting_on_oem(api_roles, tag, title_prefix="OEM-API", comment="Reviewed for the OEM tests.", extra=None):
    """The AM creates a quotation signed by FPM/FSM, BU, CEO and the external OEM and it goes through the whole internal route
    (submit, FPM/FSM approves, AM submits again, BU approves, CEO approves), so it now waits on the OEM. Returns (quotation id, quote no).
    The system emails the OEM contact: see OEM_TEST_EMAIL. `extra` overrides top-level fields (oemName, typeOfWork, device, customer and site...)."""
    signers = internal_signers(api_roles) + [oem_signer()]
    quotation_id, quote_no = create_and_submit(api_roles["AM"], api_roles, tag, ["FPM"], title_prefix=title_prefix, extra={"approvers": signers, **(extra or {})}, submit=False)
    drive_to_oem_turn(api_roles, quotation_id, comment)
    return quotation_id, quote_no


def route_existing_to_oem(api_roles, quotation_id, comment="Reviewed for the seed."):
    """Takes a quotation that already exists as a Draft (for example one made from an alarm in Alarms & Events), gives it the four signers (FPM/FSM, BU, CEO and the
    external OEM) and drives it to the OEM's turn. The AM can still change the signers because nobody has decided yet."""
    am = api_roles["AM"]
    body = am.get(f"/api/quotations/{quotation_id}").json()
    body["approvers"] = internal_signers(api_roles) + [oem_signer()]
    response = am.session.put(f"{am.base_url}{QuotationService.PATH}/{quotation_id}", json=body, timeout=max(am.timeout, 90))
    assert response.status_code == 200, f"saving the signers failed: HTTP {response.status_code} {response.text[:200]}"
    drive_to_oem_turn(api_roles, quotation_id, comment)
    return body["quoteNo"]


def seed_variant_fields(oem_name, type_of_work, site_key, device):
    """The top-level fields that make one seeded quotation different from the others (see quotation_seed_data)."""
    from framework_api.services.quotation_seed_data import CUSTOMER_SITES
    fields = {**CUSTOMER_SITES[site_key], "oemName": oem_name, "typeOfWork": type_of_work}
    if device:
        fields["device"] = device
    return fields


def create_draft(am_session, approver_sessions, tag, arrangement=None, title_prefix="HU15", extra=None):
    """The AM creates a quotation and leaves it as a Draft (not submitted), so the AM can still edit it. Returns (quotation id, quote no)."""
    return create_and_submit(am_session, approver_sessions, tag, ["FPM"], arrangement=arrangement, title_prefix=title_prefix, extra=extra, submit=False)


# ---- FSE Select (Variable Rate) quotations ----------------------------------------------------------------------------------------------
# What the screen sends when engineers are picked on the map and the Budget Calculator is confirmed (captured 2026-10-23, PUT /api/quotations/{id}):
# "select": {supportEngineers, prevailingWageAct, selectedEngineers: [{isContractor, isLeader, contractorName/Phone/Email/Location, availabilityStatus,
# costs: [{tab: "quotation" | "expense", hourlyRate, totalHours, otHourlyRate, otTotalHours, travelFlight...travelOther, items: [{section, description, quantity, unitCost, order}]}]}]}.
# The server computes every total. An FSE Select quotation must NOT carry an "arrangement" block (create_and_submit drops it).
ENGINEERS = {
    "Pedro Aguilar": dict(contractorPhone="+56-2-555-0114", contractorEmail="pedro.aguilar@example.com", contractorLocation="BEST Chile"),
    "Employee L01200": dict(contractorPhone="+591-703-45012", contractorEmail="employee.l01200@example.com", contractorLocation="AMAXST BO"),
    "Anna Lindqvist": dict(contractorPhone="+1-469-555-0120", contractorEmail="anna.lindqvist@example.com", contractorLocation="BEST USA"),
}


def engineer_cost(tab, rate=0, hours=0, ot_rate=0, ot_hours=0, travel=0, equipment=0, misc=0):
    """One calculator tab of one engineer. `travel` goes in the Flight field; equipment and misc are one item each (quantity 1)."""
    items = ([dict(section="EQUIPMENT", description="Tool", quantity=1, unitCost=equipment, order=0)] if equipment else []) + \
            ([dict(section="MISCELLANEOUS", description="Misc", quantity=1, unitCost=misc, order=0)] if misc else [])
    return dict(tab=tab, hourlyRate=rate, totalHours=hours, otHourlyRate=ot_rate, otTotalHours=ot_hours, travelFlight=travel, travelCar=0, travelHotel=0,
                travelMeals=0, travelGas=0, travelParking=0, travelToll=0, travelOther=0, items=items)


def select_extra(*engineers, support_engineers=None):
    """`engineers`: (name, quotation_cost, expense_cost) in selection order; a cost is an engineer_cost(...) or None (calculator not confirmed). The first one is the Field Leader.
    Returns the `extra` argument of create_and_submit / make_quotation / make_draft."""
    selected = []
    for i, (name, quotation, expense) in enumerate(engineers):
        costs = [c for c in (quotation, expense) if c is not None]
        selected.append(dict(isContractor=False, isLeader=i == 0, contractorName=name, availabilityStatus="available", costs=costs, **ENGINEERS[name]))
    return {"arrangementType": "Select", "select": {"supportEngineers": support_engineers or max(len(engineers), 1), "prevailingWageAct": False, "selectedEngineers": selected}}


def three_engineers():
    """The three engineers of the HU-15 mockup: Quotation (Income) and Expense figures for each. Totals: Quotation 4,225 / 3,700 / 3,300 (Final Total 11,225); Expense 2,267 / 2,080 / 1,620 (Final Total 5,967)."""
    return select_extra(
        ("Pedro Aguilar", engineer_cost("quotation", 110, 24, 165, 4, 615, 250, 60), engineer_cost("expense", 55, 24, 83, 4, 615)),
        ("Employee L01200", engineer_cost("quotation", 110, 24, 0, 0, 880, 180), engineer_cost("expense", 50, 24, 0, 0, 880)),
        ("Anna Lindqvist", engineer_cost("quotation", 67, 40, 0, 0, 500, 100, 20), engineer_cost("expense", 30, 40, 0, 0, 420)))
