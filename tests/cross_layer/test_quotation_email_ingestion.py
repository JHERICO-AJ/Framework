"""Quotation module -- HU-02 / OP-18, Automatic quotation ingestion from Outlook (Qase suite 53; HU-03 / OP-15 is tested here, end to end, as its only comment says).

Layers: the AM's Outlook (real emails sent to himself and moved to the folder 'Quotation'; a VISIBLE Chrome window) + the database (read only) + the API as the AM. The screen part is in
tests/ui/quotation/test_email_ingestion_ui.py. Every test is named c<Qase case id>_... (or c_new_... for the new cases) so the run of Qase can be built from the results.

It sends REAL emails and creates test drafts in QA (subject 'HU02R-<stamp>-<key>'): run it with EMAIL_INGEST_TESTS=1, one class at a time (each class sends its own emails, 4 to 9 minutes):
    EMAIL_INGEST_TESTS=1 python -m pytest tests/cross_layer/test_quotation_email_ingestion.py -k TestBatch10 -v
Classes: TestBatch10, TestData1, TestData2, TestSilverleaf, TestSingles1, TestSingles2.
What the build does (verified 2026-11-16/17): one draft per valid email in 9 to 60 s; amounts or counts with decimals are NOT taken (the field stays empty, AC 10); an End before the Start empties the whole FSE block (#232).
Open defects are strict xfail: #155 (same email, different data), #232 (FSE block lost). #177 (line breaks lost) was fixed on 2026-11-17."""
import os
import time

import pytest

from framework_api.client.role_session import RoleApiSession
from shared.config.credentials import load_role_credentials
from tests.cross_layer import hu02_emails as E
from tests.cross_layer import hu02_support as S

pytestmark = [pytest.mark.cross_layer,
              pytest.mark.skipif(not os.environ.get("EMAIL_INGEST_TESTS"), reason="sends real emails from the AM's Outlook (visible Chrome window): set EMAIL_INGEST_TESTS=1")]
ROOT = S.ROOT
RFP = os.path.join(ROOT, "docs", "Quotation", "Hithium Service RFP_Raven Cold Cx 1.docx")
ONE_MINUTE = 65          # AC 9: 1 minute; 5 s of margin for the moment of the click on 'Move'


@pytest.fixture(scope="module")
def am_api():
    creds = load_role_credentials("AM")
    if creds is None:
        pytest.skip("QUOTATION_AM_EMAIL / QUOTATION_AM_PASSWORD not set in .env")
    return RoleApiSession(creds["email"], creds["password"])


@pytest.fixture(scope="module")
def stamp():
    return S.new_stamp()


def subject_of(stamp, key):
    return f"HU02R-{stamp}-{key}"


def mail(stamp, key, **changes):
    """(key, subject, body, None): Template F with WO Title = the subject and the changes given (label -> value)."""
    subject = subject_of(stamp, key)
    wo = changes.pop("_title", "{title}")
    return (key, subject, E.render(subject, fields=E.replaced({"WO Title": wo, **changes})), None)


def raw(stamp, key, body, subject=None, attach=None):
    return (key, subject or subject_of(stamp, key), body, attach)


def ok(item):
    assert item["id"], f"no draft was created for {item['subject']}"
    return item["detail"]


def arr(item):
    return ok(item)["arrangement"] or {}


# ====================================================================================== 10 emails together (1029, and the data of the full template)
@pytest.fixture(scope="module")
def batch10(stamp, db_conn, am_api):
    return S.run_batch("batch10", stamp, [mail(stamp, f"T{n:02d}") for n in range(1, 11)], db_conn, am_api, wait=360)


class TestBatch10:
    def test_c1029_ten_emails_together_ten_drafts_in_one_minute(self, batch10):
        got = [v for v in batch10.values() if v["id"]]
        assert len(got) == 10, f"only {len(got)} of 10 drafts were created"
        assert len({v["quote_no"] for v in got}) == 10, "two emails share a Quote #"
        late = sorted(round(v["seconds"]) for v in got if v["seconds"] > ONE_MINUTE)
        assert not late, f"AC 9: {len(late)} draft(s) took more than 1 minute after the move (seconds: {late})"

    def test_c1021_one_valid_email_one_draft_and_no_second_one(self, batch10, db_conn):
        item = batch10["T01"]
        assert ok(item)["status"] == "Draft" and item["detail"]["source"] == "CORREO"
        time.sleep(30)
        assert len(S.drafts_like(db_conn, f"%{item['subject']}")) == 1

    def test_c1030_draft_is_not_submitted_or_routed(self, batch10):
        d = ok(batch10["T01"])
        assert d["status"] == "Draft" and d["workflowStage"] == "Quoting" and d["approvers"] == [] and d["submittedAt"] is None

    def test_c1037_wo_snapshot_fields(self, batch10):
        d, subject = ok(batch10["T01"]), batch10["T01"]["subject"]
        assert (d["oemName"], d["customerName"], d["title"], d["siteName"], d["typeOfWork"]) == ("Workflow Progress Test OEM", "Andes Renewables SpA", subject, "Valle Verde", "Commissioning")
        assert (d["siteLocation"], d["unitInfo"], d["units"], d["device"], d["severity"]) == ("Camino El Sol 450, Rancagua", "Powin Pod 5.0MWh BESS", 12, "PCS-07", "Major")

    def test_c1038_statement_of_fse_resource(self, batch10):
        a = arr(batch10["T01"])
        assert (a["supportEngineers"], a["workingHourTechDay"], a["estimatedWorkingDays"], a["totalOverHoursTech"]) == (2, 10, 5, 4)
        assert a["estimacionStartTime"].startswith("2026-11-02") and a["estimacionEndTime"].startswith("2026-11-06")
        assert a["totalWorkingHourTech"] and a["totalManWorkingHours"] and a["totalDays"], "the totals are calculated by the system"

    def test_c1041_reimbursable_costs(self, batch10):
        a = arr(batch10["T01"])
        assert (a["airTransportation"], a["carExpense"], a["materialExpense"], a["equipmentRental"], a["miscellaneous"]) == (820, 390, 250, 300, 1250)
        assert a["miscellaneousNote"] == "Site safety training and badges" and a["reimbursableSubtotal"] == 3010

    def test_c1042_diagnosis(self, batch10):
        d = ok(batch10["T01"])
        assert d["signal"] == "PCS-07 DC bus overvoltage alarm" and d["trigger"] == "Alarm raised during cold commissioning checks"
        assert d["cause"] == "Loose DC busbar connection on rack 3" and d["notes"] == "Bring insulated tooling and a phase rotation meter."
        assert d["sopDescription"].startswith("1. Lock out and tag out the PCS.") and d["sopDescription"].rstrip().endswith("for 2 hours.")

    def test_c1044_flat_rate_arrangement(self, batch10):
        assert ok(batch10["T01"])["arrangementType"] == "Arrangement" and arr(batch10["T01"])["laborCostHour"] == 90

    def test_c1047_dates(self, batch10):
        a = arr(batch10["T01"])
        assert a["estimacionStartTime"].startswith("2026-11-02") and a["estimacionEndTime"].startswith("2026-11-06")


# ====================================================================================== data variants, first group
@pytest.fixture(scope="module")
def data1(stamp, db_conn, am_api):
    emails = [
        raw(stamp, "part", E.render(subject_of(stamp, "part"), fields=[(l, v) for l, v in E.FULL if l in ("Customer", "WO Title", "Site Name", "Type of Work")])),
        raw(stamp, "free", "Hi,\nWe need a quote for commissioning work at the Valle Verde site for the customer Andes Renewables SpA. There are 12 Powin Pod units, device PCS-07, severity Major. We need 2 engineers for 5 days.\nThanks"),
        mail(stamp, "valA"),
        raw(stamp, "inv", "Hello,\nnothing about quotations here. Thanks."),
        mail(stamp, "valC"),
        raw(stamp, "noda", "Hello,\nCan we meet tomorrow to talk about the picnic and lunch for the team? Thanks."),
        raw(stamp, "emp", ""),
        mail(stamp, "accents", _title="{title} ñ é # &", Cause="Conexión floja en el rack Ñ-3", Notes="Revisión técnica: año 2026, señal ñ é á í ó ú"),
        mail(stamp, "long", Notes=("Coordinate the site access with the site manager 48 hours before arrival. " * 8) + "END-OF-NOTES",
             **{"SOP / Steps": " ".join(f"{n}. Step number {n} of the procedure: do the work carefully, record the result and tell the AM about it before the next step." for n in range(1, 7)) + " END-OF-SOP",
                "Miscellaneous Note": ("Safety induction, site badges, parking permits. " * 5) + "END-OF-NOTE"}),
        mail(stamp, "wrong", Units="many", Severity="Catastrophic"),
        raw(stamp, "rev", E.render(subject_of(stamp, "rev"), order=lambda rows: list(reversed([r for r in rows if r[0] != "#"])))),
        raw(stamp, "fw", "---------- Forwarded message ---------\nFrom: Michael Turner\nSubject: Quotation request\n\n" + E.render(subject_of(stamp, "fw")), subject="FW: " + subject_of(stamp, "fw")),
    ]
    return S.run_batch("data1", stamp, emails, db_conn, am_api, expected_drafts=9, wait=300)


class TestData1:
    def test_c1034_free_text_creates_a_draft_with_the_data_of_the_text(self, data1):
        d = ok(data1["free"])
        assert (d["customerName"], d["siteName"], d["typeOfWork"], d["units"], d["device"], d["severity"]) == ("Andes Renewables SpA", "Valle Verde", "Commissioning", 12, "PCS-07", "Major")
        assert d["arrangement"]["supportEngineers"] == 2 and d["arrangement"]["estimatedWorkingDays"] == 5
        assert not d["siteLocation"] and not d["unitInfo"] and not d["signal"] and not d["cause"], "nothing is invented"

    def test_c1035_invalid_email_does_not_block_the_next_valid_ones(self, data1):
        assert data1["valA"]["id"] and data1["valC"]["id"], "a valid email next to the invalid one was not processed"
        assert not data1["inv"]["id"], "the invalid email created a draft"

    def test_c1032_email_without_data_or_with_empty_body_creates_nothing(self, data1):
        assert not data1["noda"]["id"] and not data1["emp"]["id"]

    def test_c1036_partial_email_fills_only_its_fields(self, data1):
        d = ok(data1["part"])
        assert (d["customerName"], d["siteName"], d["typeOfWork"], d["title"]) == ("Andes Renewables SpA", "Valle Verde", "Commissioning", data1["part"]["subject"])
        assert not d["oemName"] and not d["siteLocation"] and not d["unitInfo"] and not d["units"] and not d["device"] and not d["severity"]
        assert not d["signal"] and not d["cause"] and not d["notes"] and not d["sopDescription"]
        assert not (d["arrangement"] or {}).get("laborCostHour") and not (d["arrangement"] or {}).get("hotelCost")

    def test_c1048_accents_and_symbols_are_stored_exactly(self, data1):
        d = ok(data1["accents"])
        assert d["title"] == data1["accents"]["subject"] + " ñ é # &", d["title"]
        assert d["cause"] == "Conexión floja en el rack Ñ-3" and d["notes"] == "Revisión técnica: año 2026, señal ñ é á í ó ú"

    def test_c1049_long_texts_are_stored_complete(self, data1):
        d = ok(data1["long"])
        assert d["notes"].endswith("END-OF-NOTES") and len(d["notes"]) > 600
        assert d["sopDescription"].endswith("END-OF-SOP") and len(d["sopDescription"]) > 600
        assert d["arrangement"]["miscellaneousNote"].endswith("END-OF-NOTE")

    def test_c1050_wrong_values_leave_only_their_field_empty(self, data1):
        d = ok(data1["wrong"])
        assert d["units"] is None and d["severity"] is None
        assert d["customerName"] == "Andes Renewables SpA" and d["device"] == "PCS-07" and d["arrangement"]["laborCostHour"] == 90

    def test_c1051_fields_in_a_different_order(self, data1):
        d = ok(data1["rev"])
        assert (d["customerName"], d["siteName"], d["units"], d["cause"]) == ("Andes Renewables SpA", "Valle Verde", 12, "Loose DC busbar connection on rack 3")
        assert d["arrangement"]["supportEngineers"] == 2 and d["arrangement"]["laborCostHour"] == 90 and d["arrangement"]["hotelCost"] == 1500

    def test_c1053_forwarded_email(self, data1):
        d = ok(data1["fw"])
        assert (d["customerName"], d["units"]) == ("Andes Renewables SpA", 12) and d["arrangement"]["supportEngineers"] == 2 and d["arrangement"]["laborCostHour"] == 90


# ====================================================================================== data variants, second group
@pytest.fixture(scope="module")
def data2(stamp, db_conn, am_api):
    stamp2 = stamp + "b"
    emails = [
        mail(stamp2, "whole", **{"Hotel Cost": "$1,500", "Per Diem": "$720", "Air Transportation": "$1,250", "Equipment Rental": "$12,345", "Miscellaneous": "$1,250"}),
        mail(stamp2, "dec", **{"Units": "12.5", "Support Engineers": "2.7", "Estimated Working Days": "5.5", "Working Hour / Tech Day": "9.5", "Travel / Drive Time": "6.5"}),
        mail(stamp2, "cents", **{"Hotel Cost": "$1,500.50", "Per Diem": "$720", "Air Transportation": "$820.50", "Car Expense": "$390", "Miscellaneous": "$1,250.25", "Equipment Rental": "$12,345.67"}),
        mail(stamp2, "neg", **{"Labor Cost / Hour": "-$90.00", "Hotel Cost": "-$1,500", "Support Engineers": "-2", "Units": "-5"}),
        mail(stamp2, "zero", **{"Labor Cost / Hour": "$0.00", "Support Engineers": "0"}),
        mail(stamp2, "mis", Customer="Sungrow"),
        mail(stamp2, "dates", **{"Est. Start Time": "11/06/2026 08:00", "Est. End Time": "11/02/2026 18:00"}),
        raw(stamp2, "rep", E.render(subject_of(stamp2, "rep"), fields=E.FULL + [("Customer", "Hithium Energy Storage"), ("Units", "30")])),
        mail(stamp2, "lines", Cause="Line 1 - Loose DC busbar connection on rack 3.\nLine 2 - Found during the cold commissioning checks. END-OF-CAUSE",
             Notes="Line 1 - Coordinate the site access.\nLine 2 - Bring PPE.\nLine 3 - No cell coverage.\nLine 4 - Report any finding. END-OF-NOTES",
             **{"SOP / Steps": "1. Lock out and tag out the PCS.\n2. Verify zero energy.\n3. Torque all DC busbar connections.\n4. Run the insulation resistance test.\n5. Record the results.\n6. Restart the PCS and monitor for 2 hours. END-OF-SOP"}),
        raw(stamp2, "rfp", S.docx_text(RFP)),
    ]
    return S.run_batch("data2", stamp2, emails, db_conn, am_api, expected_drafts=10, wait=300)


class TestData2:
    def test_c1046_whole_amounts_with_dollar_and_thousands_separator(self, data2):
        a = arr(data2["whole"])
        assert (a["laborCostHour"], a["hotelCost"], a["perDiem"], a["airTransportation"], a["equipmentRental"], a["miscellaneous"]) == (90, 1500, 720, 1250, 12345, 1250)

    def test_c_new_decimals_are_not_taken_and_the_rest_is_stored(self, data2):
        d = ok(data2["dec"]); a = d["arrangement"]
        assert d["units"] is None and a["supportEngineers"] is None and a["estimatedWorkingDays"] is None and a["workingHourTechDay"] is None and a["travelDriveTime"] is None
        assert d["customerName"] == "Andes Renewables SpA" and a["laborCostHour"] == 90 and a["hotelCost"] == 1500

    def test_c_new_cents_are_not_taken_and_whole_amounts_are_stored(self, data2):
        a = arr(data2["cents"])
        assert a["hotelCost"] is None and a["airTransportation"] is None and a["miscellaneous"] is None and a["equipmentRental"] is None
        assert a["perDiem"] == 720 and a["carExpense"] == 390

    def test_c1429_negative_values_are_not_stored(self, data2):
        d = ok(data2["neg"]); a = d["arrangement"]
        assert a["laborCostHour"] is None and a["hotelCost"] is None and a["supportEngineers"] is None and d["units"] is None

    def test_c1429_zero_values_stay_in_the_draft_and_the_submit_refuses_them(self, data2, am_api):
        item = data2["zero"]; a = arr(item)
        assert a["supportEngineers"] == 0 and a["laborCostHour"] == 0
        r = am_api.post(f"/api/quotations/{item['id']}/submit", json={"approverOverrideAcknowledged": False})
        assert r.status_code == 400, f"the submit of a draft with 0 values answered {r.status_code}"
        assert "SupportEngineers" in r.text and "LaborCostHour" in r.text
        assert S.detail(am_api, item["id"])["status"] == "Draft"

    def test_c1432_customer_and_site_are_kept_as_the_email_says(self, data2):
        """Qase case 1432 (rewritten 2026-11-19): defect #158 is invalid, the developer confirmed in OP-127 that a draft from an email keeps the customer and the site that the email says (the catalog ids stay empty) and the AM reviews them."""
        d = ok(data2["mis"])
        assert d["customerName"] == "Sungrow" and d["siteName"] == "Valle Verde", (d["customerName"], d["siteName"])

    def test_c1430_reversed_dates_are_not_stored(self, data2):
        a = arr(data2["dates"])
        assert a["estimacionStartTime"] is None and a["estimacionEndTime"] is None

    @pytest.mark.xfail(strict=True, reason="Qase #232: with End before Start the draft loses the whole FSE Arrangement")
    def test_c1430_reversed_dates_the_rest_of_the_fse_is_stored(self, data2):
        a = arr(data2["dates"])
        assert a["supportEngineers"] == 2 and a["workingHourTechDay"] == 10 and a["estimatedWorkingDays"] == 5 and a["laborCostHour"] == 90 and a["hotelCost"] == 1500, "Qase #232: the whole FSE block is lost"


    def test_c1430_reversed_dates_the_submit_is_refused(self, data2, am_api):
        item = data2["dates"]
        r = am_api.post(f"/api/quotations/{item['id']}/submit", json={"approverOverrideAcknowledged": False})
        assert r.status_code == 400 and "EstimacionStartTime" in r.text and S.detail(am_api, item["id"])["status"] == "Draft"

    def test_c1434_a_repeated_field_keeps_one_value(self, data2):
        d = ok(data2["rep"])
        assert d["customerName"] in ("Andes Renewables SpA", "Hithium Energy Storage") and d["units"] in (12, 30)

    def test_c_new_line_breaks_are_kept(self, data2):
        d = ok(data2["lines"])
        assert "\n" in d["cause"] and d["notes"].count("\n") == 3 and d["sopDescription"].count("\n") == 5

    def test_c_new_rfp_in_the_body_creates_the_draft_with_its_data(self, data2):
        d = ok(data2["rfp"]); a = d["arrangement"]
        assert d["customerName"].startswith("Hithium Energy Storage") and d["siteLocation"] == "11174 North Tidwell Prairie Rd, Bremond, TX 76629"
        assert "Tidwell I" in (d["siteName"], d["title"]), "the project name of the document is neither in SITE NAME nor in WO TITLE (in 3 runs it landed once in each: see Qase #155)"
        assert d["units"] == 96 and "Hithium 5.016MWh BESS" in (d["device"], d["unitInfo"], d["title"]), "the product of the document is not stored"
        assert a["supportEngineers"] == 4 and a["workingHourTechDay"] == 10 and a["estimatedWorkingDays"] == 15 and a["laborCostHour"] is None


# ====================================================================================== the same email three times (Qase #155)
@pytest.fixture(scope="module")
def silverleaf(stamp, db_conn, am_api):
    body = S.eve_body(RFP)
    emails = [raw(stamp, f"S{n}", body, subject=f"HU02-E2 Silverleaf {n} " + subject_of(stamp, f"S{n}")) for n in (1, 2, 3)]
    return S.run_sequential("silverleaf", stamp, emails, db_conn, am_api)


class TestSilverleaf:
    @pytest.mark.xfail(strict=True, reason="Qase #155 / OP-125: the same email gives different data (Est. Start Time in 1 of 3) and the costs written as '2 rooms x 20 nights x $150' are empty")
    def test_c_new_same_email_three_times_same_data(self, silverleaf):
        keys = ("title", "customerName", "siteName", "units", "device", "siteLocation")
        akeys = ("supportEngineers", "estimatedWorkingDays", "laborCostHour", "laborOverCostHour", "estimacionStartTime", "hotelCost", "perDiem", "airTransportation", "carExpense")
        rows = [tuple([ok(v).get(k) for k in keys] + [arr(v).get(k) for k in akeys]) for v in silverleaf.values()]
        assert len(set(rows)) == 1, f"the three drafts differ: {rows}"
        assert rows[0][-4] is not None and rows[0][-3] is not None, "hotel, per diem, airfare and car are empty"
