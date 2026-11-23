"""Quotation module -- Budget Summary, whole-number rule on the server (OP-23 / HU-15; Qase suite "HU-15: BU and OEM view of the Budget Summary", cases FV11-FV12).

HU-15: 'Amounts and hours must be whole numbers. The inputs must not accept decimals, and a value with decimals sent through a direct request must be rejected with
"<Field> must be a whole number."' Observed on the QA build of 2026-10-22: amounts and hours are refused with exactly that message; the count fields (Support Engineers,
Estimated Working Days, Units) are refused too, but with a raw technical error that names the .NET type (see the strict xfail).
"""
import time

import pytest

from framework_api.services import quotation_setup as qs
from framework_api.services.quotation_service import QuotationService

pytestmark = pytest.mark.api

# arrangement field -> the label the server must use in "<Field> must be a whole number."
AMOUNT_AND_HOUR_FIELDS = [("laborCostHour", "Labor Cost / Hour"), ("laborOverCostHour", "Labor Over Cost / Hour"), ("workingHourTechDay", "Working Hour / Tech Day"),
                          ("hotelCost", "Hotel Cost"), ("perDiem", "Per Diem / Person"), ("travelDriveTime", "Travel / Drive Time"), ("airTransportation", "Air Transportation"),
                          ("carExpense", "Car Expense"), ("materialExpense", "Material Expense"), ("equipmentRental", "Equipment Rental"), ("miscellaneous", "Miscellaneous")]


def create_payload(quotation_api, arrangement=None, extra=None):
    svc = quotation_api["AM"]
    quote_no = svc.next_quote_number(qs.CUSTOMER["customerId"], qs.CUSTOMER["customerName"])
    return {"quoteNo": quote_no, "oemName": "Workflow Progress Test OEM", **qs.CUSTOMER, "title": f"Workflow Progress test HU15-FV-API-{time.time_ns() % 10**12}", **qs.SITE, "typeOfWork": "Commissioning",
            "units": 0, "arrangementType": "Arrangement", "source": "MANUAL", "arrangement": {**qs.ARRANGEMENT, **(arrangement or {})}, "attachments": [], "approvers": [], **(extra or {})}


def post(quotation_api, payload):
    return quotation_api["AM"].client.post(QuotationService.PATH, json=payload)


@pytest.mark.parametrize("field, label", AMOUNT_AND_HOUR_FIELDS)
def test_the_server_refuses_decimals_in_amounts_and_hours_with_the_whole_number_message(quotation_api, field, label):
    """Qase HU15-FV11"""
    r = post(quotation_api, create_payload(quotation_api, arrangement={field: 50.5}))
    assert r.status_code == 400, f"{r.status_code} {r.text[:200]}"
    messages = [m for msgs in (r.json().get("details") or {}).values() for m in msgs]
    assert f"{label} must be a whole number." in messages, messages


def test_a_whole_number_written_with_a_decimal_point_is_accepted(quotation_api):
    """Qase HU15-FV11 (the boundary: 50.0 is a whole number)."""
    r = post(quotation_api, create_payload(quotation_api, arrangement={"laborCostHour": 50.0, "hotelCost": 1050.0}))
    assert r.status_code == 201, f"{r.status_code} {r.text[:200]}"


@pytest.mark.parametrize("where, field, label", [("arrangement", "supportEngineers", "Support Engineers"), ("arrangement", "estimatedWorkingDays", "Estimated Working Days"), ("top", "units", "Units")])
def test_the_server_refuses_decimals_in_the_count_fields_with_the_whole_number_message(quotation_api, where, field, label):
    """Qase HU15-FV12"""
    payload = create_payload(quotation_api, arrangement={field: 2.5} if where == "arrangement" else None, extra={field: 2.5} if where == "top" else None)
    r = post(quotation_api, payload)
    assert r.status_code == 400
    text = r.text
    assert f"{label} must be a whole number." in text, "the answer must be the whole-number message"
    assert "System.Nullable" not in text, "the answer must not show internal type names"
