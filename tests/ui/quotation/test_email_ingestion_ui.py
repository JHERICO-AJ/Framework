"""Quotation module -- HU-02 / OP-18, Automatic quotation ingestion from Outlook: what the AM SEES (screen layer).
The drafts are created by the e-mails of tools/hu02_*.py; here the AM looks for them in Quotes in Progress by WO Title."""
import os
import re

import pytest

from tests.ui.quotation.am_page import quotation_page  # noqa: F401  (the AM, as in the other regression modules)

pytestmark = [pytest.mark.ui]
SHOTS = os.path.join("reports", "hu02")


def _latest_email_titles(db_conn, like, limit=3):
    with db_conn.cursor() as cur:
        cur.execute('SELECT "Title","QuoteNo" FROM quotation."Quotation" WHERE "Origen"=\'CORREO\' AND "CorreoAsunto" LIKE %s ORDER BY "FechaCreacion" DESC LIMIT %s', (like, limit))
        rows = cur.fetchall()
    db_conn.rollback()
    return rows


def test_probe_email_draft_row_on_screen(quotation_page, db_conn):
    """Exploration: reads the row of an e-mail draft (and of a manual one) in Quotes in Progress to learn where the origin indicator is."""
    rows = _latest_email_titles(db_conn, "HU02T-%", 2)
    assert rows, "no e-mail draft of the HU02T batch in the database"
    page = quotation_page.page
    quotation_page.open(refresh=True)
    quotes = quotation_page.historical_quotes()
    quotes.open_in_progress()
    for title, quote_no in rows:
        quotes.type_in_search(title)
        quotes.search_with_enter(title)
        row = quotes.row_for(title)
        print(f"ROW {quote_no}: {row}")
        page.screenshot(path=os.path.join(SHOTS, f"ui_row_{quote_no}.png"))
        assert row is not None, f"the e-mail draft {quote_no} '{title}' is not in Quotes in Progress"


def test_probe_workflow_panel_of_email_draft(quotation_page, db_conn):
    """Exploration for Qase defect #178 / OP-143: what the 'Quotation Workflow' panel shows in 'Created / drafted' for a draft created from an email."""
    rows = _latest_email_titles(db_conn, "HU02A-154207-A01%", 1)
    assert rows
    title = rows[0][0]
    quotation_page.open(refresh=True)
    quotes = quotation_page.historical_quotes()
    quotes.open_in_progress()
    quotes.type_in_search(title)
    quotes.search_with_enter(title)
    quotation_page.open_workflow_history(title)
    page = quotation_page.page
    page.wait_for_timeout(1500)
    page.screenshot(path=os.path.join(SHOTS, "ui_workflow_email_draft.png"))
    print("PANEL:", page.locator("body").inner_text()[-1500:].replace("\n", " | "))


def _mark(page, locator, name):
    """Red frame around an element (evidence screenshots)."""
    locator.first.evaluate("(e, n) => { e.style.outline = '3px solid red'; e.style.outlineOffset = '2px'; }", name)


def test_probe_customer_site_pair_of_email_draft(quotation_page, db_conn):
    """Qase defect #158 / OP-127, as the defect says: open the draft of an email with Customer 'Sungrow' + Site 'Valle Verde' and read CUSTOMER, SITE NAME and SITE LOCATION; then, for
    comparison, open a manual quotation, choose the customer SUNgrOW and read what SITE NAME offers."""
    with db_conn.cursor() as cur:
        cur.execute('SELECT "Title" FROM quotation."Quotation" WHERE "Origen"=\'CORREO\' AND "CorreoAsunto" LIKE %s ORDER BY "FechaCreacion" DESC LIMIT 1', ("%Q7 sungrow%",))
        row = cur.fetchone()
    db_conn.rollback()
    assert row, "no draft of the Sungrow email"
    title = row[0]
    page = quotation_page.page
    quotation_page.open(refresh=True)
    quotes = quotation_page.historical_quotes()
    quotes.open_in_progress()
    quotes.type_in_search(title)
    quotes.search_with_enter(title)
    quotation_page.open_listed_quotation(title)
    snap = quotation_page.wo_snapshot()
    values = {label: snap.field(label).first.input_value() for label in ("Customer", "Site Name", "Site Location")}
    print("DRAFT:", values)
    for label in ("Customer", "Site Name", "Site Location"):
        _mark(page, snap.field(label), label)
    page.screenshot(path=os.path.join(SHOTS, "ui_158_draft_marked.png"))


def _mark_field(page, label_regex, color="red", scroll=True):
    """Frame around the control that follows the label: red for what fails, green for what works (the form labels are uppercase by CSS; the DOM text is the normal one)."""
    label = page.locator("label").filter(has_text=re.compile(label_regex, re.I)).first
    control = label.locator("xpath=following::*[self::textarea or self::input or self::select][1]")
    control.evaluate("(e, c) => { e.style.outline = '3px solid ' + c; e.style.outlineOffset = '2px'; }", color)
    if scroll:
        control.evaluate("e => e.scrollIntoView({block: 'center'})")
    return control


def _open_draft(quotation_page, quote_no):
    quotation_page.open(refresh=True)
    quotes = quotation_page.historical_quotes()
    quotes.open_in_progress()
    quotes.type_in_search(quote_no)
    quotes.search_with_enter(quote_no)
    quotation_page.open_listed_quotation(quote_no)
    return quotation_page.page


def _quote_no(db_conn, like):
    with db_conn.cursor() as cur:
        cur.execute('SELECT "QuoteNo" FROM quotation."Quotation" WHERE "CorreoAsunto" LIKE %s ORDER BY "FechaCreacion" DESC LIMIT 1', (like,))
        r = cur.fetchone()
    db_conn.rollback()
    assert r, f"no draft for {like}"
    return r[0]


def _evidence(quotation_page, db_conn, like, labels, name, scroll_to=None):
    """Opens the draft of the email, frames the fields in red and saves the screenshot (reports/hu02/<name>.png)."""
    page = _open_draft(quotation_page, _quote_no(db_conn, like))
    for label in labels:
        _mark_field(page, label)
    if scroll_to:
        page.locator("label").filter(has_text=re.compile(scroll_to, re.I)).first.scroll_into_view_if_needed()
    page.wait_for_timeout(600)
    page.screenshot(path=os.path.join(SHOTS, name + ".png"))


FSE_LABELS = ("^Support Engineers", "^Working Hour / Tech Day", "^Estimated Working Days", "Est\. Start Time", "Est\. End Time", "^Labor Cost / Hour")


def test_ev_fse_block_empty(quotation_page, db_conn):
    """New finding: End before Start -> the draft loses the whole FSE block."""
    _evidence(quotation_page, db_conn, "%154207-A09 dates", FSE_LABELS, "ev_fse_block_empty_marked")


def test_ev_fse_block_control(quotation_page, db_conn):
    """Control of the same run: the same email with correct dates keeps the FSE block."""
    _evidence(quotation_page, db_conn, "%154207-A01 full", FSE_LABELS, "ev_fse_block_control_marked")


def test_ev_155_r1_top(quotation_page, db_conn):
    _evidence(quotation_page, db_conn, "%HU02Y-%-R1", ("Est\. Start Time",), "ev_155_R1_start_marked")


def test_ev_155_r2_top(quotation_page, db_conn):
    _evidence(quotation_page, db_conn, "%HU02Y-%-R2", ("Est\. Start Time",), "ev_155_R2_start_marked")


def test_ev_155_r1_costs(quotation_page, db_conn):
    _evidence(quotation_page, db_conn, "%HU02Y-%-R1", ("^Hotel Cost", "^Per Diem", "^Air Transportation", "^Car Expense"), "ev_155_R1_costs_marked", scroll_to="^Hotel Cost")


def test_probe_edit_save_submit_of_email_draft(quotation_page, db_conn):
    """Exploration for the cases 1031 / 1060 / 1061: the AM edits an email draft, saves it, reloads and submits it. Prints what the screen and the server show at each step."""
    qn = _quote_no(db_conn, "%154207-A10 repeated")
    page = _open_draft(quotation_page, qn)
    snap = quotation_page.wo_snapshot()
    snap.field("Unit Info").first.fill("Edited by the AM")
    quotation_page.save_draft()
    page.wait_for_timeout(2500)
    page.screenshot(path=os.path.join(SHOTS, "probe_after_save.png"))
    quotation_page.open(refresh=True)
    quotes = quotation_page.historical_quotes()
    quotes.open_in_progress()
    quotes.type_in_search(qn)
    quotes.search_with_enter(qn)
    print("AFTER SAVE ROW:", quotes.row_for(qn))
    quotation_page.open_listed_quotation(qn)
    print("UNIT INFO after reload:", quotation_page.wo_snapshot().field("Unit Info").first.input_value())
    quotation_page.submit_quotation()
    page.wait_for_timeout(4000)
    page.screenshot(path=os.path.join(SHOTS, "probe_after_submit.png"))
    print("BODY AFTER SUBMIT:", page.locator("body").inner_text()[:600].replace("\n", " | "))


def test_probe_workflow_panel_after_submit(quotation_page, db_conn):
    """Exploration for case 1061: the panel of an email draft that the AM already submitted (FSA00003419)."""
    page = quotation_page.page
    quotation_page.open(refresh=True)
    quotes = quotation_page.historical_quotes()
    quotes.open_in_progress()
    quotes.type_in_search("FSA00003419")
    quotes.search_with_enter("FSA00003419")
    quotation_page.open_workflow_history("HU02A-154207-A10 repeated")
    page.wait_for_timeout(1500)
    page.screenshot(path=os.path.join(SHOTS, "probe_workflow_after_submit.png"))
    text = page.locator("body").inner_text()
    i = text.find("QUOTATION WORKFLOW")
    print("PANEL2:", text[i:i + 900].replace("\n", " | "))


def test_probe_submit_zero_values(quotation_page, db_conn):
    """Exploration for case 1429: what the screen says when the AM submits an email draft with Support Engineers 0 and Labor Cost 0."""
    qn = _quote_no(db_conn, "%B02 zero")
    page = _open_draft(quotation_page, qn)
    quotation_page.submit_quotation()
    page.wait_for_timeout(2500)
    page.screenshot(path=os.path.join(SHOTS, "probe_submit_zero.png"))
    text = page.locator("body").inner_text()
    print("SUBMIT ZERO (visible text with 'must' or 'required'):", [l for l in text.split("\n") if re.search(r"(?i)must|required|error|invalid|cannot", l)][:8])


DOCS = os.path.join("docs", "Quotation", "HU18_test_documents")


def test_probe_upload_rfp_and_damaged(quotation_page):
    """Exploration for the HU-03 cases: what the 'Upload file' path (the document source) gives for the Hithium RFP and for a damaged file."""
    up = quotation_page.document_upload()
    page = quotation_page.page
    rfp = os.path.join("docs", "Quotation", "Hithium Service RFP_Raven Cold Cx 1.docx")
    up.upload(rfp)
    seconds = up.wait_form()
    snap = quotation_page.wo_snapshot()
    values = {label: snap.field(label).first.input_value() for label in ("Customer", "WO Title", "Site Name", "Site Location", "Units", "Device")}
    print("RFP UPLOAD %.0fs:" % seconds, values)
    page.screenshot(path=os.path.join(SHOTS, "probe_upload_rfp.png"))
    quotation_page.open(refresh=True)
    up = quotation_page.document_upload()
    up.upload(os.path.join(DOCS, "damaged.docx"))
    text = up.error_text(timeout_ms=60000)
    print("DAMAGED UPLOAD error text:", repr(text))
    if not text:
        try:
            up.wait_form(timeout_ms=5000)
            snap = quotation_page.wo_snapshot()
            print("DAMAGED opened a form:", {label: snap.field(label).first.input_value() for label in ("Customer", "WO Title", "Site Name")})
        except Exception as exc:
            print("DAMAGED: no form and no dialog", type(exc).__name__)
    page.screenshot(path=os.path.join(SHOTS, "probe_upload_damaged.png"))


FSE_TOP = ("^Support Engineers", "^Working Hour / Tech Day", "^Estimated Working Days", "Est\. Start Time", "Est\. End Time", "^Labor Cost / Hour")


def _evidence_color(quotation_page, db_conn, like, color, name):
    """Frames the FSE fields in `color` and leaves the top of the FSE panel in view (the engineers, hours, days and dates, then the labor costs)."""
    page = _open_draft(quotation_page, _quote_no(db_conn, like))
    for label in FSE_TOP:
        _mark_field(page, label, color=color, scroll=False)
    page.locator("label").filter(has_text=re.compile("^Support Engineers", re.I)).first.scroll_into_view_if_needed()
    page.wait_for_timeout(600)
    page.screenshot(path=os.path.join(SHOTS, name + ".png"))


def test_ev_232_bad(quotation_page, db_conn):
    _evidence_color(quotation_page, db_conn, "%HU02-FSE-1 End before start%", "red", "ev_232_bad_red")


def test_ev_232_good(quotation_page, db_conn):
    _evidence_color(quotation_page, db_conn, "%HU02-FSE-2 Correct dates%", "green", "ev_232_good_green")


def test_ev_177_green(quotation_page, db_conn):
    """Qase #177 retest: the draft of the multi-line email keeps the line breaks (green frames = it works)."""
    page = _open_draft(quotation_page, _quote_no(db_conn, "%-lines"))
    for label in ("^Cause$", "^Notes$", r"^SOP"):
        _mark_field(page, label, color="green", scroll=False)
    page.locator("label").filter(has_text=re.compile("^Cause$", re.I)).first.scroll_into_view_if_needed()
    page.wait_for_timeout(600)
    page.screenshot(path=os.path.join(SHOTS, "ev_177_fixed_green.png"))
