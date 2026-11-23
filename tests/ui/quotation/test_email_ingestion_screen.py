"""Quotation module -- HU-02 / OP-18 and HU-03 / OP-15: what the AM SEES on the screen for the drafts created from an email (cases 1030, 1044, 1058, 1059, 1060, 1031, 1061, 1429, 1430, 1432 and the
HU-03 criteria 2 and 4). The drafts are the ones created by tests/cross_layer/test_quotation_email_ingestion.py (and test_quotation_email_singles.py): their Quote # are read from
reports/hu02/ingest_state.json, so those classes must have run first (the tests skip when the draft is not there). The tests of 1031 and 1061 SUBMIT their drafts (T06, T07 of the last TestBatch10): run this file once per run of that class. Signed in as the AM (role_page). Run it on its own (see docs/commands/COMANDOS_TESTS.md).
Open defects are strict xfail: #158 (customer and site that do not belong together)."""
import os
import re

import pytest

from framework_api.services import quotation_setup as qs
from tests.cross_layer import hu02_support as S
from tests.ui.quotation.am_page import quotation_page  # noqa: F401  (the AM)

pytestmark = [pytest.mark.ui]
ROOT = S.ROOT
RFP = os.path.join(ROOT, "docs", "Quotation", "Hithium Service RFP_Raven Cold Cx 1.docx")
DAMAGED = os.path.join(ROOT, "docs", "Quotation", "HU18_test_documents", "damaged.docx")
DAMAGED_MESSAGE = "The file content does not match its extension. Upload a valid PDF or Word document (.pdf, .doc, .docx)."
WO_LABELS = ("OEM Name", "Customer", "WO Title", "Site Name", "Type of Work", "Site Location", "Unit Info", "Units", "Device", "Severity")
FSE_LABELS = ("Support Engineers", "Working Hour / Tech Day", "Estimated Working Days")


def quote_no(group, key):
    state = S.load_state().get(group)
    item = state and state["items"].get(key)
    if not item or not item.get("quote_no"):
        pytest.skip(f"the draft '{key}' of the group '{group}' does not exist: run the class of tests/cross_layer that creates it first")
    return item["quote_no"]


def find_row(quotation_page, quote):
    quotation_page.open(refresh=True)
    quotes = quotation_page.historical_quotes()
    quotes.open_in_progress()
    quotes.type_in_search(quote)
    quotes.search_with_enter(quote)
    return quotes, quotes.row_for(quote)


def open_draft(quotation_page, quote):
    quotes, row = find_row(quotation_page, quote)
    assert row, f"{quote} is not in Quotes in Progress"
    quotation_page.open_listed_quotation(quote)
    return row


def value_of(quotation_page, label):
    control = quotation_page.page.locator("label").filter(has_text=re.compile(rf"^{re.escape(label)}", re.I)).first.locator("xpath=following::*[self::textarea or self::input or self::select][1]")
    if control.evaluate("e => e.tagName") == "SELECT":
        return control.evaluate("e => e.options[e.selectedIndex]?.text ?? ''").strip()
    return control.input_value().strip()


def filled(quotation_page, labels):
    """The labels whose field holds a real value (not empty, not the form's own 0, not the '— Select —' placeholder)."""
    return {l for l in labels if value_of(quotation_page, l) not in ("", "0", "— Select —", "-- Select --")}


class TestEmailDraftsOnScreen:
    def test_c1058_email_draft_is_listed_with_the_email_origin(self, quotation_page):
        quotes, row = find_row(quotation_page, quote_no("batch10", "T02"))
        assert row and row["source"] == "Email" and row["status"].startswith("Draft") and row["current_step"] == "WO Quoting"

    def test_c1030_draft_waits_for_nobody_and_can_be_submitted_by_the_am(self, quotation_page):
        quotes, row = find_row(quotation_page, quote_no("batch10", "T03"))
        assert row["waiting_on"] == "—" and row["status"].startswith("Draft")
        quotation_page.open_listed_quotation(quote_no("batch10", "T03"))
        assert quotation_page.page.get_by_role("button", name="Submit Quotation").is_visible() and quotation_page.page.get_by_role("button", name="Save Draft").is_visible()

    def test_c1044_draft_shows_the_flat_rate_arrangement(self, quotation_page):
        open_draft(quotation_page, quote_no("batch10", "T04"))
        assert quotation_page.page.get_by_text(re.compile(r"^statement of fse resource$", re.I)).first.is_visible()
        assert value_of(quotation_page, "Support Engineers") == "2" and value_of(quotation_page, "Labor Cost / Hour").lstrip("$ ") == "90"

    def test_c1060_origin_is_kept_after_the_am_edits_and_saves(self, quotation_page):
        quote = quote_no("batch10", "T05")
        open_draft(quotation_page, quote)
        quotation_page.wo_snapshot().field("Unit Info").first.fill("Edited by the AM")
        quotation_page.save_draft()
        quotation_page.page.wait_for_timeout(2500)
        quotes, row = find_row(quotation_page, quote)
        assert row["source"] == "Email"
        quotation_page.open_listed_quotation(quote)
        assert value_of(quotation_page, "Unit Info") == "Edited by the AM"

    def test_c1031_the_am_completes_saves_and_submits_the_draft(self, quotation_page):
        quote = quote_no("batch10", "T06")
        open_draft(quotation_page, quote)
        page = quotation_page.page
        page.locator("label").filter(has_text=re.compile("^Labor Cost / Hour", re.I)).first.locator("xpath=following::input[1]").fill("95")
        quotation_page.save_draft()
        page.wait_for_timeout(2500)
        open_draft(quotation_page, quote)
        assert value_of(quotation_page, "Labor Cost / Hour").lstrip("$ ") == "95"
        quotation_page.submit_quotation()
        page.wait_for_timeout(4000)
        quotes, row = find_row(quotation_page, quote)
        assert row["status"].startswith("Submitted") and "QA Default" in row["waiting_on"] and row["source"] == "Email"

    def test_c1061_history_shows_the_channel_and_the_am_who_submits(self, quotation_page):
        quote = quote_no("batch10", "T07")
        open_draft(quotation_page, quote)
        quotation_page.submit_quotation()
        quotation_page.page.wait_for_timeout(4000)
        quotes, row = find_row(quotation_page, quote)
        quotation_page.open_workflow_history(row["title"])
        text = quotation_page.page.locator("body").inner_text()
        panel = text[text.find("QUOTATION WORKFLOW"):]
        assert "Incoming email" in panel and "Created from an email" in panel
        assert re.search(r"Jherico Ascencio\s*\|?\s*AM", " | ".join(panel.split("\n"))) and "Submitted for review" in panel

    def test_c1059_a_manual_quotation_does_not_show_the_email_origin(self, quotation_page, api_roles):
        quotation_id, quote = qs.create_draft(api_roles["AM"], api_roles, "S1059", title_prefix="HU02-1059")
        quotes, row = find_row(quotation_page, quote)
        assert row and row["source"] == "Manual"

    def test_c1429_submit_of_a_draft_with_zero_values_shows_the_message(self, quotation_page):
        quote = quote_no("data2", "zero")
        open_draft(quotation_page, quote)
        quotation_page.submit_quotation()
        quotation_page.page.wait_for_timeout(2500)
        assert "Must be greater than 0" in quotation_page.page.locator("body").inner_text()
        quotes, row = find_row(quotation_page, quote)
        assert row["status"].startswith("Draft")

    def test_c1430_reversed_dates_are_empty_on_screen_and_the_draft_is_not_submitted(self, quotation_page):
        quote = quote_no("data2", "dates")
        open_draft(quotation_page, quote)
        dates = quotation_page.page.locator("label").filter(has_text=re.compile(r"^Est\. (Start|End) Time", re.I))
        for i in range(dates.count()):
            assert dates.nth(i).locator("xpath=following::input[1]").input_value() == "", "a date of the reversed range is on the screen"
        quotation_page.submit_quotation()
        quotation_page.page.wait_for_timeout(2500)
        quotes, row = find_row(quotation_page, quote)
        assert row["status"].startswith("Draft")

    @pytest.mark.xfail(strict=True, reason="Qase #158 / OP-127: the pair Sungrow + Valle Verde is kept as a valid pair on the screen")
    def test_c1432_customer_and_site_that_do_not_belong_together(self, quotation_page):
        open_draft(quotation_page, quote_no("data2", "mis"))
        assert not (value_of(quotation_page, "Customer") == "Sungrow" and value_of(quotation_page, "Site Name") == "Valle Verde")

    def test_c1432_the_manual_form_only_offers_the_sites_of_the_customer(self, quotation_page):
        quotation_page.open(refresh=True)
        quotation_page.create_quotation()
        snap = quotation_page.wo_snapshot()
        quotation_page.page.wait_for_timeout(2500)
        customer = snap.field("Customer").first
        label = next(t.strip() for t in customer.locator("option").all_inner_texts() if re.search("sungrow", t, re.I))
        customer.select_option(label=label)
        quotation_page.page.wait_for_timeout(1500)
        sites = [o for o in snap.select_option_values("Site Name") if o and not o.startswith("—")]
        assert sites and "Valle Verde" not in sites, sites  # at the time of writing the only site of Sungrow is 'Sungrow'


class TestHu03OnScreen:
    def test_c_new_hu03_ac2_the_same_fields_are_filled_from_an_email_and_from_an_uploaded_file(self, quotation_page):
        quote = quote_no("data2", "rfp")
        open_draft(quotation_page, quote)
        from_email = filled(quotation_page, WO_LABELS + FSE_LABELS)
        quotation_page.open(refresh=True)
        up = quotation_page.document_upload()
        up.upload(RFP)
        up.wait_form()
        from_file = filled(quotation_page, WO_LABELS + FSE_LABELS)
        assert from_email == from_file, f"filled only from the email: {sorted(from_email - from_file)}; filled only from the file: {sorted(from_file - from_email)}"

    def test_c_new_hu03_ac4_a_damaged_file_is_refused_and_no_form_opens(self, quotation_page):
        quotation_page.open(refresh=True)
        up = quotation_page.document_upload()
        up.upload(DAMAGED)
        assert up.error_text(timeout_ms=60000) == DAMAGED_MESSAGE
        assert not quotation_page.page.get_by_text("WO SNAPSHOT", exact=True).first.is_visible()
