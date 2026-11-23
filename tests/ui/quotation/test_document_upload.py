"""Quotation module -- 'Upload file' (a pre-loaded quotation from a document), screen side (OP-17 / HU-18; Qase suite "HU-18: Generate a pre-loaded quotation by uploading a document", cases UD-*).

Only the HU-18 text decides what must happen (V13 AC-3.x / V14 describe the same idea for the customer's EMAIL; the story changes it to a document and drops the notice about the unfilled fields).
Observed on the QA build of 2026-11-09 (the build of 2026-10-28 created the quotation when the file was read; since 2026-11-09 the form opens with the data and nothing is saved until Save Draft or Submit; the errors are a dialog): the option is a label 'Upload file' with a hidden file input (accept .pdf,.doc,.docx, one file) at the top right of the landing page; choosing a file calls
POST /api/quotations/from-document, a panel says 'Reading the document…' and the form opens on /quotation/<id>. The type, the empty file and the size (> 10 MB) are refused in the browser.
The data is read by an AI service (HU-03), so the tests compare only what the Hithium template says in plain words (docs/Quotation/Hithium Service RFP_Raven Cold Cx 1.docx, and the same document
saved as .doc) and the PDF the tests build with plain 'Label: value' lines. Every successful upload creates a quotation of the AM in the shared QA, so the module uploads as few documents as
it can (one per scenario fixture) and the test quotations are listed for cleanup (their titles come from the documents: Hithium 5.016MWh BESS, Acme 3MWh BESS, Borealis).
Story-silent behaviour (no data in the document, a service that is slow or down, the same document twice, a quotation already open) is NOT asserted: it is documented as blocked cases.
"""
import os
import re

import pytest

from framework_api.services import quotation_document_service as docs
from framework_ui.pages.quotation import quotation_locators as ql
from framework_ui.pages.quotation.components import document_upload_locators as loc
from framework_ui.pages.quotation.components import fse_arrangement_locators as fl
from framework_ui.pages.quotation.components import wo_snapshot_locators as wl
from framework_ui.pages.quotation.quotation_page import QuotationPage

pytestmark = pytest.mark.ui

WO_LABELS = {"oemName": wl.LABEL_OEM_NAME, "customerName": wl.LABEL_CUSTOMER, "title": wl.LABEL_WO_TITLE, "siteName": wl.LABEL_SITE_NAME, "typeOfWork": wl.LABEL_TYPE_OF_WORK,
             "siteLocation": wl.LABEL_SITE_LOCATION, "unitInfo": wl.LABEL_UNIT_INFO, "units": wl.LABEL_UNITS, "device": wl.LABEL_DEVICE, "severity": wl.LABEL_SEVERITY}
DIAGNOSIS_LABELS = {"signal": "SIGNAL", "trigger": "TRIGGER", "cause": "CAUSE", "notes": "NOTES", "sopDescription": "SOP / STEPS"}
EMPTY_SELECT = "— Select —"
OVER_LIMIT_MESSAGE_TOKENS = (".pdf", "10 MB")
# What the form shows for the Hithium template since the build of 2026-11-09: the project name of the document is the WO Title and the Site Name; the OEM Name stays empty (no OEM line).
FORM_EXPECTED = {"customerName": "Hithium Energy Storage", "title": "Tidwell I", "siteName": "Tidwell I", "siteLocation": "11174 North Tidwell Prairie Rd, Bremond, TX 76629", "units": 96,
                 "device": "Hithium 5.016MWh BESS"}
SLOW_LIMIT_SECONDS = 30


# ---- helpers ----------------------------------------------------------------------------------------------------------------------------
def value_of(locator):
    return locator.evaluate("e => e.tagName === 'SELECT' ? (e.options[e.selectedIndex] ? e.options[e.selectedIndex].text : '') : e.value")


def is_free(locator):
    return locator.evaluate("e => !e.disabled && !e.readOnly")


def read_form(page):
    """What the open form shows: {'wo': {key: value}, 'diagnosis': {...}, 'fse': {...}, 'editable': {key: bool}}."""
    wo, editable = {}, {}
    for key, label in WO_LABELS.items():
        field = page.wo_snapshot().field(label)
        wo[key], editable[key] = value_of(field), is_free(field)
    diagnosis = {}
    for key, label in DIAGNOSIS_LABELS.items():
        field = page.diagnosis_field(label)
        diagnosis[key], editable[key] = value_of(field), is_free(field)
    fse = page.fse_arrangement()
    statement = {}
    for key, label in (("supportEngineers", fl.LABEL_SUPPORT_ENGINEERS), ("workingHourTechDay", fl.LABEL_WORKING_HOUR_TECH_DAY), ("estimatedWorkingDays", fl.LABEL_ESTIMATED_WORKING_DAYS),
                       ("estimacionStartTime", fl.LABEL_EST_START_TIME), ("estimacionEndTime", fl.LABEL_EST_END_TIME)):
        field = fse.field(fl.SECTION_HEADING_STATEMENT, label)
        statement[key], editable[key] = value_of(field), is_free(field)
    statement["totalManWorkingHours"] = fse.computed_value(fl.SECTION_HEADING_STATEMENT, fl.LABEL_TOTAL_MAN_WORKING_HOURS)
    return {"wo": wo, "diagnosis": diagnosis, "fse": statement, "editable": editable}


def api_detail(api_roles, quotation_id):
    response = api_roles["AM"].get(f"/api/quotations/{quotation_id}")
    assert response.status_code == 200, f"{response.status_code} {response.text[:200]}"
    return response.json()


def api_events(api_roles, quotation_id):
    return api_roles["AM"].get(f"/api/quotations/{quotation_id}/events").json()


def total_count(api_roles):
    """How many quotations the AM has (in progress + historical), from the totalCount of the list."""
    return sum(api_roles["AM"].get("/api/quotations", page=1, pageSize=1, includeClosed=closed).json()["totalCount"] for closed in ("false", "true"))


def number(text):
    match = re.search(r"-?\d+(?:\.\d+)?", text or "")
    return float(match.group()) if match else None


def upload_and_open(role_page, api_roles, path):
    """The user chooses the file; returns (page, upload component, seconds until the form opened, ids of the AM's quotations while the form is open and before it)."""
    page = QuotationPage(role_page("AM")).open(refresh=True)
    page.historical_quotes().settle()
    upload = page.document_upload()
    before = docs.my_quotation_ids(api_roles["AM"])
    upload.upload(path)
    upload.wait_loading()
    loading = (upload.loading_visible(), upload.loading_text_visible())
    seconds = upload.wait_form()
    page.page.wait_for_timeout(1500)           # the fields are filled a moment after the form opens
    return page, upload, seconds, loading, before, docs.my_quotation_ids(api_roles["AM"])


def scenario(role_page, api_roles, path):
    """Uploads `path` as the user does and keeps what the story talks about: the time, the loading panel, the form as it opens, the quotations before, while it is open and after closing it
    (nothing is stored: the form is only pre-filled)."""
    page, upload, seconds, loading, before, while_open = upload_and_open(role_page, api_roles, path)
    form = read_form(page)
    page.close_form()
    page.page.wait_for_timeout(1500)
    after_close = docs.my_quotation_ids(api_roles["AM"])
    upload.detach()
    return {"seconds": seconds, "loading": loading, "form": form, "before": before, "while_open": while_open, "after_close": after_close}


@pytest.fixture
def landing(role_page):
    """The AM's Quotation landing page, freshly loaded, with the upload component listening."""
    page = QuotationPage(role_page("AM")).open(refresh=True)
    page.historical_quotes().settle()
    yield page
    upload = page.document_upload()
    upload.dismiss_toasts()
    upload.detach()
    page.historical_quotes().detach()


@pytest.fixture(scope="module")
def template(role_page, api_roles):
    """One upload of the Hithium .docx through the screen."""
    return scenario(role_page, api_roles, docs.HITHIUM_DOCX)


@pytest.fixture(scope="module")
def template_doc(role_page, api_roles):
    """The same template saved as a real .doc (Word 97-2003)."""
    return scenario(role_page, api_roles, docs.HITHIUM_DOC)


@pytest.fixture(scope="module")
def request_pdf(role_page, api_roles, tmp_path_factory):
    path = tmp_path_factory.mktemp("hu18") / "request.pdf"
    path.write_bytes(docs.build_pdf(docs.REQUEST_LINES))
    return scenario(role_page, api_roles, str(path))


@pytest.fixture(scope="module")
def partial(role_page, api_roles, tmp_path_factory):
    path = tmp_path_factory.mktemp("hu18") / "partial.docx"
    path.write_bytes(docs.build_docx(docs.PARTIAL_LINES))
    return scenario(role_page, api_roles, str(path))


@pytest.fixture(scope="module")
def edited(role_page, api_roles):
    """Uploads the template, changes pre-filled and empty fields, presses Save Draft and keeps what the system stored and what the list shows (the quotation is created by Save Draft)."""
    import time
    page, upload, seconds, loading, before, while_open = upload_and_open(role_page, api_roles, docs.HITHIUM_DOCX)
    stamp = str(time.time_ns() // 1000000 % 10 ** 9)
    title = f"Edited title HU18 {stamp}"
    wo = page.wo_snapshot()
    changes = {wl.LABEL_OEM_NAME: "Edited OEM", wl.LABEL_CUSTOMER: "Edited Customer", wl.LABEL_WO_TITLE: title, wl.LABEL_SITE_NAME: "Edited Site",
               wl.LABEL_SITE_LOCATION: "1 Edited Street", wl.LABEL_UNITS: "12", wl.LABEL_DEVICE: "Edited device", wl.LABEL_UNIT_INFO: "Unit info typed by the AM"}
    for label, text in changes.items():
        wo.field(label).fill(text)
    wo.field(wl.LABEL_TYPE_OF_WORK).select_option(label="Warranty Repair")
    page.fse_arrangement().field(fl.SECTION_HEADING_STATEMENT, fl.LABEL_SUPPORT_ENGINEERS).fill("5")
    page.diagnosis_field("SOP / STEPS").fill("SOP changed by the AM")
    page.diagnosis_field("NOTES").fill("Notes typed by the AM")
    page.save_draft()                    # Save Draft closes the form and shows the list again
    stored, quotation_id = {}, None
    for _ in range(30):
        page.page.wait_for_timeout(1000)
        items = api_roles["AM"].get("/api/quotations", page=1, pageSize=5, includeClosed="false", search=stamp).json()["items"]
        if items:
            quotation_id = items[0]["id"]
            stored = api_detail(api_roles, quotation_id)
            break
    upload.detach()
    listing = QuotationPage(role_page("AM")).open(refresh=True).historical_quotes()
    listing.settle()
    listing.open_in_progress()
    listing.search_with_enter(stored["quoteNo"])
    row = listing.row_for(stored["quoteNo"])
    listing.detach()
    return {"id": quotation_id, "title": title, "stored": stored, "row": row, "changes": changes, "events": api_events(api_roles, quotation_id), "before": before, "while_open": while_open}


# ================================================================================================================ entry point
def test_the_landing_page_offers_upload_file_next_to_create_quotation(landing):
    """Qase UD-EP1 -- 'The Quotation module landing page displays a new Upload option alongside Create Quotation.'"""
    upload = landing.document_upload()
    assert upload.is_visible() and upload.label().get_attribute("title") == loc.UPLOAD_LABEL_TITLE
    assert landing.page.get_by_role("button", name=ql.CREATE_QUOTATION_BUTTON_TEXT).count() == 1


def test_create_quotation_still_opens_a_blank_form(landing):
    """Qase UD-EP2 -- 'This option does not replace manual creation.'"""
    landing.create_quotation()
    assert landing.wo_snapshot().field(wl.LABEL_WO_TITLE).input_value() == ""
    assert landing.wo_snapshot().field(wl.LABEL_CUSTOMER).input_value() == ""
    landing.close_form()


@pytest.mark.parametrize("role", ["FPM", "BU", "CEO"])
def test_an_approver_does_not_get_the_upload_option(role_page, role):
    """Qase UD-EP3 -- the option belongs to the AM (the server also refuses the other roles: see UD-API13)."""
    page = QuotationPage(role_page(role)).open(refresh=True)
    page.page.wait_for_timeout(2500)
    assert not page.document_upload().is_visible() and page.document_upload().input_count() == 0
    page.document_upload().detach()


def test_the_option_takes_one_pdf_or_word_document_only(landing):
    """Qase UD-EP4 -- 'The user can upload only one document per quotation.' + 'accepted types: .pdf, .doc and .docx'."""
    upload = landing.document_upload()
    assert upload.input_count() == 1 and upload.accept() == loc.ACCEPT and upload.allows_several() is False


# ================================================================================================================ validation in the browser
REFUSED = [("note.txt", b"plain text"), ("picture.png", b"\x89PNG\r\n\x1a\n" + b"0" * 64), ("sheet.xlsx", b"PK\x03\x04" + b"0" * 64), ("document", docs.read(docs.HITHIUM_DOCX))]


@pytest.mark.parametrize("name, data", REFUSED, ids=["txt", "png", "xlsx", "no-extension"])
def test_a_file_of_another_type_is_refused_before_it_is_sent(landing, api_roles, tmp_path, name, data):
    """Qase UD-VF1 (.txt), UD-VF2 (.png), UD-VF3 (.xlsx) and UD-VF4 (no extension) -- 'the system validates the file type before attempting extraction ... rejects it with an error message'."""
    path = tmp_path / name
    path.write_bytes(data)
    before = total_count(api_roles)
    upload = landing.document_upload()
    upload.upload(str(path))
    message = upload.error_text()
    assert message == loc.MESSAGE_TYPE, message
    assert not upload.calls, "the file was sent although its type is not accepted"
    assert not upload.loading_visible() and total_count(api_roles) == before
    upload.dismiss_toasts()
    assert landing.page.get_by_role("button", name=ql.CREATE_QUOTATION_BUTTON_TEXT).count() == 1


def test_an_empty_file_is_refused_before_it_is_sent(landing, api_roles, tmp_path):
    """Qase UD-VF5 -- an empty .pdf is refused with a message, nothing is sent and nothing is created."""
    path = tmp_path / "empty.pdf"
    path.write_bytes(b"")
    before = total_count(api_roles)
    upload = landing.document_upload()
    upload.upload(str(path))
    assert upload.error_text() == loc.MESSAGE_EMPTY
    assert not upload.calls and total_count(api_roles) == before


def test_a_file_over_10_mb_is_refused_before_it_is_sent(landing, api_roles, tmp_path):
    """Qase UD-VF6 -- 'maximum size: 10 MB': a file of 10 MB + 1 byte is refused, nothing is sent and nothing is created."""
    path = tmp_path / "big.pdf"
    path.write_bytes(b"%PDF-1.4\n" + b"0" * (loc.MAX_BYTES + 1 - 9))
    before = total_count(api_roles)
    upload = landing.document_upload()
    upload.upload(str(path))
    assert upload.error_text() == loc.MESSAGE_SIZE
    assert not upload.calls and total_count(api_roles) == before


def test_a_document_of_exactly_10_mb_is_accepted(landing):
    """Qase UD-VF7 -- 'maximum size: 10 MB': a valid .docx of exactly 10 MB (10,485,760 bytes) is not refused for its size or its type (defect #193 fixed in the build of 2026-11-09). Reading it takes
    26 to 45 seconds in the QA: the form opens when it takes less than 30 seconds and the window 'Time limit exceeded' shows when it takes longer; both are accepted here, a refusal for size is not."""
    import tempfile, os, time
    handle, path = tempfile.mkstemp(suffix=".docx")
    with os.fdopen(handle, "wb") as out:
        out.write(docs.padded_docx(docs.MAX_BYTES))
    try:
        upload = landing.document_upload()
        upload.upload(path)
        started, outcome = time.monotonic(), None
        while time.monotonic() - started < 120 and outcome is None:
            if landing.page.get_by_text(loc.FORM_MARKER_TEXT, exact=True).count():
                outcome = "form"
            elif upload.error_dialog().count():
                outcome = upload.error_title()
            else:
                landing.page.wait_for_timeout(500)
        print(f"UD-VF7: outcome {outcome!r} after {time.monotonic() - started:.1f} s")
        assert outcome in ("form", loc.DIALOG_TITLE_TIMEOUT), f"the document of exactly 10 MB was not accepted: {outcome!r} {upload.error_text(timeout_ms=1000)!r}"
        upload.dismiss_toasts()
    finally:
        os.remove(path)


@pytest.mark.parametrize("message", [loc.MESSAGE_TYPE, loc.MESSAGE_SIZE], ids=["type message", "size message"])
def test_the_error_message_says_the_allowed_types_and_the_size(message):
    """Qase UD-VF8 -- 'rejects it with an error message indicating the allowed types and size.' (defect #194 fixed in the build of 2026-11-09: both messages say the types and the 10 MB)"""
    assert all(token in message for token in OVER_LIMIT_MESSAGE_TOKENS), message


def test_a_file_that_is_not_what_its_name_says_is_refused_by_the_server(landing, api_roles, tmp_path):
    """Qase UD-VF9 -- a text named .pdf passes the browser (the extension is right), the server reads it, refuses it, no form opens and nothing is created."""
    path = tmp_path / "fake.pdf"
    path.write_bytes(b"this is not a pdf")
    before = total_count(api_roles)
    upload = landing.document_upload()
    upload.upload(str(path))
    message = upload.error_text()
    assert message == loc.MESSAGE_SERVER_TYPE, message
    assert upload.calls and upload.answers[-1][0] == 400
    assert landing.page.get_by_text(loc.FORM_MARKER_TEXT, exact=True).count() == 0 and total_count(api_roles) == before


def test_after_a_refused_file_the_manual_creation_still_works(landing, tmp_path):
    """Qase UD-VF10 -- 'This option does not replace manual creation': after an error the user can still create a quotation."""
    path = tmp_path / "note.txt"
    path.write_bytes(b"plain text")
    landing.document_upload().upload(str(path))
    landing.document_upload().error_text()
    landing.document_upload().dismiss_toasts()
    landing.page.wait_for_timeout(500)
    landing.create_quotation()
    assert landing.wo_snapshot().field(wl.LABEL_WO_TITLE).input_value() == ""
    landing.close_form()


# ================================================================================================================ three file types open the pre-filled form
def test_a_docx_document_opens_the_form_pre_filled(template):
    """Qase UD-VF11 -- a .docx opens the form with the data of the document (the Hithium template)."""
    assert template["form"]["wo"]["customerName"] == FORM_EXPECTED["customerName"]


def test_a_doc_document_opens_the_form_pre_filled(template_doc):
    """Qase UD-VF12 -- the same document saved as a real .doc (Word 97-2003) opens the form pre-filled."""
    assert template_doc["form"]["wo"]["customerName"] == FORM_EXPECTED["customerName"] and template_doc["form"]["wo"]["siteName"] == FORM_EXPECTED["siteName"]


def test_a_pdf_document_opens_the_form_pre_filled(request_pdf):
    """Qase UD-VF13 -- a .pdf with the data of a request opens the form with it."""
    wo = request_pdf["form"]["wo"]
    assert wo["customerName"] == docs.REQUEST_EXPECTED["customerName"] and wo["siteName"] == docs.REQUEST_EXPECTED["siteName"] and wo["siteLocation"] == docs.REQUEST_EXPECTED["siteLocation"], wo
    assert number(wo["units"]) == docs.REQUEST_EXPECTED["units"] and request_pdf["form"]["diagnosis"]["sopDescription"] == docs.REQUEST_EXPECTED["sopDescription"]


# ================================================================================================================ pre-filled fields
def test_the_oem_name_stays_empty_when_the_template_has_no_oem_line(template):
    """Qase UD-EX1 -- 'Fields that could not be extracted are displayed empty': the Hithium template has no OEM line, so the OEM Name is empty (on the build of 2026-10-28 it was filled with 'Hithium')."""
    assert template["form"]["wo"]["oemName"] == "", template["form"]["wo"]["oemName"]


@pytest.mark.parametrize("key", ["customerName", "title", "siteName", "siteLocation", "units", "device"])
def test_the_wo_snapshot_fields_of_the_document_are_pre_filled(template, key):
    """Qase UD-EX2 .. UD-EX7 -- Customer, WO Title, Site Name, Site Location, Units and Device come from the document."""
    shown = template["form"]["wo"][key]
    expected = FORM_EXPECTED[key]
    assert (number(shown) == expected) if isinstance(expected, int) else (shown == expected), (key, shown)


def test_the_fse_arrangement_fields_of_the_document_are_pre_filled(template):
    """Qase UD-EX8 -- Support Engineers 4, Working Hour / Tech Day 10 and Estimated Working Days 15 come from the document, and the total of man hours is calculated from them (600)."""
    fse = template["form"]["fse"]
    assert (number(fse["supportEngineers"]), number(fse["workingHourTechDay"]), number(fse["estimatedWorkingDays"])) == (4, 10, 15), fse
    assert number(fse["totalManWorkingHours"]) == 600, fse


def test_the_diagnosis_section_is_pre_filled_with_the_sop_of_the_document(template):
    """Qase UD-EX9 -- the Diagnosis section shows the SOP / Steps that the document gives ('Contact Jonathan for SOP.')."""
    assert template["form"]["diagnosis"]["sopDescription"] == docs.HITHIUM_EXPECTED["sopDescription"], template["form"]["diagnosis"]


def test_the_fields_the_document_does_not_give_are_empty(template):
    """Qase UD-EX10 -- 'Fields that could not be extracted are displayed empty': Type of Work, Unit Info, Severity, Signal, Trigger, Cause, Notes and the dates of the work."""
    form = template["form"]
    assert form["wo"]["typeOfWork"] == EMPTY_SELECT and form["wo"]["unitInfo"] == "" and form["wo"]["severity"] in ("", EMPTY_SELECT), form["wo"]
    assert [form["diagnosis"][key] for key in ("signal", "trigger", "cause", "notes")] == ["", "", "", ""], form["diagnosis"]
    assert form["fse"]["estimacionStartTime"] == "" and form["fse"]["estimacionEndTime"] == ""


def test_the_form_opens_when_the_document_gives_only_a_few_fields(partial):
    """Qase UD-EX11 -- 'without preventing the form from opening': a document with only the customer and the quantity opens the form, the rest is empty."""
    wo = partial["form"]["wo"]
    assert wo["customerName"] == "Borealis Power Inc" and number(wo["units"]) == 7
    assert wo["siteName"] == "" and wo["siteLocation"] == "" and wo["device"] == "", wo


@pytest.mark.xfail(strict=True, reason="OPEN DEFECT (Qase case UD-EX15): when the document has no title the WO Title is filled with the NAME OF THE FILE ('partial' for partial.docx) instead of staying empty")
def test_the_wo_title_stays_empty_when_the_document_gives_no_title(partial):
    """Qase UD-EX15 -- 'Fields that could not be extracted are displayed empty': the document has no title, so WO Title must be empty."""
    assert partial["form"]["wo"]["title"] == "", partial["form"]["wo"]["title"]


def test_every_field_of_the_pre_filled_form_can_be_edited_and_the_empty_ones_too(template):
    """Qase UD-EX12 -- 'Pre-filled fields are fully editable' and the fields that were not extracted are editable."""
    editable = template["editable"] if "editable" in template else template["form"]["editable"]
    blocked = [key for key, free in editable.items() if not free]
    assert not blocked, f"fields that cannot be edited: {blocked}"


def test_the_changes_of_the_user_are_kept_by_save_draft(edited):
    """Qase UD-EX13 -- the pre-filled values the user changed, and the empty fields the user filled, are what Save Draft stores."""
    stored = edited["stored"]
    assert (stored["oemName"], stored["customerName"], stored["title"], stored["siteName"], stored["siteLocation"], stored["units"], stored["device"]) == (
        "Edited OEM", "Edited Customer", edited["title"], "Edited Site", "1 Edited Street", 12, "Edited device")
    assert stored["arrangement"]["supportEngineers"] == 5 and stored["sopDescription"] == "SOP changed by the AM"


def test_the_fields_the_document_did_not_give_can_be_filled_and_are_kept(edited):
    """Qase UD-EX14 -- Type of Work, Unit Info and Notes were empty, the user filled them and Save Draft keeps them."""
    stored = edited["stored"]
    assert (stored["typeOfWork"], stored["unitInfo"], stored["notes"]) == ("Warranty Repair", "Unit info typed by the AM", "Notes typed by the AM")


# ================================================================================================================ loading and time
def test_while_the_document_is_read_a_loading_panel_is_shown(template):
    """Qase UD-LD1 -- 'While the document is being processed, the system displays a loading indicator.'"""
    assert template["loading"] == (True, True)


@pytest.mark.parametrize("fixture_name", ["template", "template_doc", "request_pdf"])
def test_the_form_opens_within_30_seconds(request, fixture_name):
    """Qase UD-LD2 -- 'The pre-filled form opens within a maximum of 30 seconds from the moment the document is uploaded.'"""
    seconds = request.getfixturevalue(fixture_name)["seconds"]
    assert seconds <= SLOW_LIMIT_SECONDS, f"the form took {seconds:.1f} s"


# ================================================================================================================ saving
def test_the_quotation_is_not_saved_when_the_form_opens(template):
    """Qase UD-SV1 -- 'The system only opens the pre-filled form. The quotation is not saved until the user clicks Save Draft or Submit.' (defect #192 fixed in the build of 2026-11-09)"""
    assert template["while_open"] == template["before"], "a quotation was stored while the form is open and nothing was pressed"


def test_closing_the_form_without_saving_leaves_no_quotation(template):
    """Qase UD-SV2 -- the user closes the pre-filled form without Save Draft or Submit: no quotation is stored."""
    assert template["after_close"] == template["before"]


def test_after_save_draft_the_quotation_is_in_quotes_in_progress_with_the_document_origin(edited):
    """Qase UD-SV3 -- 'Once saved, the quotation appears in the Quotes in Progress list with a Document origin indicator.'"""
    row = edited["row"]
    assert row is not None and row["source"] == loc.SOURCE_BADGE_TEXT and row["status"].startswith("Draft"), row      # the status button reads "Draft ↦"


def test_the_quotation_belongs_to_the_user_who_uploaded_the_document(edited, api_roles):
    """Qase UD-SV4 -- 'The quotation is assigned to the user who uploaded the document, who is recorded as its creator.' (once the AM saves the pre-filled form)"""
    created = [event for event in edited["events"] if event["eventType"] == "Created"]
    assert len(created) == 1 and created[0]["actorEmail"] == api_roles["AM"].email and created[0]["actorRole"] == "AM", created
    assert edited["stored"]["createdBy"] == created[0]["actorName"], edited["stored"]["createdBy"]


def test_the_stored_quotation_is_a_draft_made_from_a_document(edited):
    """Qase UD-SV5 -- the quotation saved from the pre-filled form is a Draft whose source is DOCUMENTO and has a Quote # of the system."""
    detail = edited["stored"]
    assert detail["status"] == "Draft" and detail["source"] == "DOCUMENTO" and re.fullmatch(r"FS[A-Z]\d{8}", detail["quoteNo"]), detail["quoteNo"]


# ================================================================================================================ when the reading fails (the story does not say: these check the minimum)
SERVICE_FAILURES = {
    "server error 500": (lambda route: route.fulfill(status=500, body=""), loc.MESSAGE_GENERIC),
    "bad gateway 502": (lambda route: route.fulfill(status=502, body="Bad Gateway"), loc.MESSAGE_GENERIC),
    "service unavailable 503": (lambda route: route.fulfill(status=503, body="Service Unavailable"), loc.MESSAGE_GENERIC),
    "reader not reachable (the real answer of the server)": (lambda route: route.fulfill(
        status=400, content_type="application/json", body='{"statusCode":400,"message":"The document reader is not reachable right now. Try again later, or create the quotation manually.","details":{"code":"DOCUMENT_EXTRACTION_UNAVAILABLE"}}'),
        "The document reader is not reachable right now"),
    "connection lost": (lambda route: route.abort("failed"), loc.MESSAGE_GENERIC),
}


@pytest.mark.parametrize("kind", list(SERVICE_FAILURES))
def test_when_the_reading_service_fails_the_user_sees_a_message_and_can_create_manually(landing, api_roles, kind):
    """Qase UD-FL6 -- the story does not say what happens when the service fails: today a dialog says what happened (without technical words), the loading panel goes away when it is closed, no form opens, nothing is created and 'Create Quotation' is still there."""
    handler, expected = SERVICE_FAILURES[kind]
    before = total_count(api_roles)
    landing.page.route("**/api/quotations/from-document", handler)
    try:
        upload = landing.document_upload()
        upload.upload(docs.HITHIUM_DOCX)
        message = upload.error_text(timeout_ms=15000)
        landing.page.wait_for_timeout(500)
        assert expected in message, message
        assert landing.page.get_by_text(loc.FORM_MARKER_TEXT, exact=True).count() == 0
        upload.dismiss_toasts()
        landing.page.wait_for_timeout(500)
        assert not upload.loading_visible()
        assert landing.page.get_by_role("button", name=ql.CREATE_QUOTATION_BUTTON_TEXT).count() == 1 and total_count(api_roles) == before
    finally:
        landing.page.unroute("**/api/quotations/from-document")


NO_DATA_FILES = {"unrelated text": ("menu.docx", lambda: docs.build_docx(docs.UNRELATED_LINES)), "damaged docx": ("damaged.docx", docs.damaged_docx),
                 "scanned pdf": ("scan.pdf", docs.build_scanned_pdf), "password protected docx": ("protected.docx", docs.protected_docx)}


@pytest.mark.parametrize("kind", list(NO_DATA_FILES))
def test_a_document_without_quotation_data_shows_a_message_and_opens_no_form(landing, api_roles, tmp_path, kind):
    """Qase UD-FL7 -- the story does not say what happens: today the dialog says why (no data, content that does not match the extension, password protected), no form opens, nothing is created and the manual creation is still there."""
    name, build = NO_DATA_FILES[kind]
    expected = {"damaged docx": loc.MESSAGE_SERVER_TYPE, "password protected docx": loc.MESSAGE_PROTECTED}.get(kind, loc.MESSAGE_NO_DATA)
    path = tmp_path / name
    path.write_bytes(build())
    before = total_count(api_roles)
    upload = landing.document_upload()
    upload.upload(str(path))
    message = upload.error_text(timeout_ms=30000)
    landing.page.wait_for_timeout(500)
    assert message == expected, message
    assert landing.page.get_by_text(loc.FORM_MARKER_TEXT, exact=True).count() == 0 and total_count(api_roles) == before
    upload.dismiss_toasts()
    landing.page.wait_for_timeout(500)
    assert landing.page.get_by_role("button", name=ql.CREATE_QUOTATION_BUTTON_TEXT).count() == 1


# ================================================================================================================ third pass: reload while reading, two files in a row, Submit from the screen
def test_reloading_the_page_while_the_document_is_read_leaves_a_usable_landing_page(landing, api_roles):
    """Qase UD-FL8 -- the user reloads the page while 'Reading the document…' is shown: the landing page loads again, with Create Quotation, no form is open and nothing was stored."""
    before = docs.my_quotation_ids(api_roles["AM"])
    upload = landing.document_upload()
    upload.upload(docs.HITHIUM_DOCX)
    upload.wait_loading()
    landing.page.reload()
    landing.page.get_by_role("button", name=ql.CREATE_QUOTATION_BUTTON_TEXT).wait_for(timeout=30000)
    landing.page.wait_for_timeout(8000)
    assert landing.page.get_by_text(loc.FORM_MARKER_TEXT, exact=True).count() == 0 and not landing.document_upload().loading_visible()
    left = docs.my_quotation_ids(api_roles["AM"]) - before
    assert len(left) == 0, f"quotations stored after the reload: {len(left)}"


def test_choosing_a_second_file_while_the_first_is_read_ends_in_an_open_form(landing, api_roles):
    """Qase UD-FL9 -- the user chooses a second file while the first is still being read: the page does not break, one form ends up open and nothing is stored."""
    before = docs.my_quotation_ids(api_roles["AM"])
    upload = landing.document_upload()
    upload.upload(docs.HITHIUM_DOCX)
    upload.wait_loading()
    upload.file_input().set_input_files(docs.HITHIUM_DOC)
    upload.wait_form()
    landing.page.wait_for_timeout(8000)
    assert landing.page.get_by_text(loc.FORM_MARKER_TEXT, exact=True).count() == 1
    assert docs.my_quotation_ids(api_roles["AM"]) == before, "a quotation was stored although nothing was saved"


def test_a_pre_filled_quotation_can_be_submitted_from_the_screen(role_page, api_roles):
    """Qase UD-SV6 -- the AM completes the missing required fields of the pre-filled form and presses Submit Quotation (the approver is the default one by amount): the quotation is created, leaves Draft and is waiting for approval."""
    import time
    from tests.ui.quotation.support import pick_first_enabled_day
    page, upload, seconds, loading, before, while_open = upload_and_open(role_page, api_roles, docs.HITHIUM_DOCX)
    stamp = str(time.time_ns() // 1000000 % 10 ** 9)
    wo = page.wo_snapshot()
    wo.field(wl.LABEL_WO_TITLE).fill(f"Workflow Progress test HU18-SV6-{stamp}")
    wo.field(wl.LABEL_TYPE_OF_WORK).select_option(index=1)
    gsp = wo.field("GSP #")
    if gsp.is_enabled():
        gsp.fill(f"HU18-{stamp}")
    if not value_of(wo.field(wl.LABEL_OEM_NAME)):
        wo.field(wl.LABEL_OEM_NAME).fill("Hithium")
    fse = page.fse_arrangement()
    for label in (fl.LABEL_EST_START_TIME, fl.LABEL_EST_END_TIME):
        pick_first_enabled_day(page.page, fse.field(fl.SECTION_HEADING_STATEMENT, label))
    fse.field("Labor Costs", "Labor Cost / Hour").fill("50")
    page.page.wait_for_timeout(300)
    submit_button = page.page.get_by_role("button", name="Submit Quotation", exact=True)
    for attempt in range(4):
        submit_button.click(force=True)
        page.page.wait_for_timeout(5000)
        without = page.page.get_by_role("button", name="Save without approver", exact=False)
        if without.count() > 0:
            without.click()
            page.page.wait_for_timeout(2000)
        if page.page.get_by_text(loc.FORM_MARKER_TEXT, exact=True).count() == 0:
            break
        page.page.keyboard.press("Escape")
    assert page.page.get_by_text(loc.FORM_MARKER_TEXT, exact=True).count() == 0, "the form is still open after Submit Quotation"
    items = []
    for _ in range(20):
        items = api_roles["AM"].get("/api/quotations", page=1, pageSize=5, includeClosed="false", search=stamp).json()["items"]
        if items:
            break
        page.page.wait_for_timeout(1000)
    upload.detach()
    assert items, "the quotation was not created by Submit Quotation"
    assert items[0]["status"] != "Draft" and items[0]["source"] == "DOCUMENTO", (items[0]["status"], items[0]["source"])


# ================================================================================================================ with the reading service REALLY off (run with HU18_AI_OFF=1 once the service of HU-03 is switched off)
AI_OFF = pytest.mark.skipif(os.environ.get("HU18_AI_OFF") != "1", reason="the reading service of HU-03 must be switched off: run with HU18_AI_OFF=1")
OFF_MESSAGE = "The document reader is not reachable right now. Try again later, or create the quotation manually."


@AI_OFF
@pytest.mark.parametrize("kind", ["template docx", "request pdf", "unrelated text", "scanned pdf", "protected docx", "text named pdf"])
def test_with_the_reading_service_off_the_user_sees_a_message_and_nothing_is_created(landing, api_roles, tmp_path, kind):
    """Qase UD-FL6 (real service off, 2026-10-29) -- every valid document gets the message of the unavailable reader within seconds, the panel goes away, no form opens, nothing is created and Create Quotation stays."""
    files = {"template docx": ("t.docx", lambda: docs.read(docs.HITHIUM_DOCX)), "request pdf": ("r.pdf", lambda: docs.build_pdf(docs.REQUEST_LINES)),
             "unrelated text": ("menu.docx", lambda: docs.build_docx(docs.UNRELATED_LINES)), "scanned pdf": ("scan.pdf", docs.build_scanned_pdf),
             "protected docx": ("protected.docx", docs.protected_docx), "text named pdf": ("fake.pdf", lambda: b"this is not a pdf")}
    name, build = files[kind]
    path = tmp_path / name
    path.write_bytes(build())
    before = total_count(api_roles)
    upload = landing.document_upload()
    upload.upload(str(path))
    message = upload.error_text(timeout_ms=60000)
    landing.page.wait_for_timeout(800)
    assert OFF_MESSAGE in message, message
    assert not upload.loading_visible() and landing.page.get_by_text(loc.FORM_MARKER_TEXT, exact=True).count() == 0
    assert landing.page.get_by_role("button", name=ql.CREATE_QUOTATION_BUTTON_TEXT).count() == 1 and total_count(api_roles) == before


# ================================================================================================================ special characters inside the document, as the screen shows them
@pytest.mark.parametrize("kind, value", [("script tag", "<script>alert('XSS-1')</script> Corp"), ("template tags", "{{7*7}} ${7*7} <%= 7*7 %> Corp"), ("emoji", "Solar ☀️⚡\U0001f50b Corp")])
def test_text_with_scripts_templates_or_emoji_is_shown_as_text_and_never_executed(role_page, api_roles, tmp_path, kind, value):
    """Qase UD-FL10 -- the document says a script, template tags or emoji: the form shows them as plain text, no alert opens and no script is added to the page."""
    lines = [f"Customer Name: {value}", f"Project Name: Chars {kind}", "Site Address: 1 Chars Road, Austin, TX", f"Product: Chars {kind} BESS", "Quantity: 5"]
    path = tmp_path / "chars.docx"
    path.write_bytes(docs.build_docx(lines))
    page = QuotationPage(role_page("AM")).open(refresh=True)
    page.historical_quotes().settle()
    dialogs = []
    def on_dialog(dialog):                    # the page is shared by the whole session: this handler is removed at the end and never blocks the 'leave this page?' question
        if dialog.type == "beforeunload":
            dialog.accept()
        else:
            dialogs.append(dialog.message)
            dialog.dismiss()
    page.page.on("dialog", on_dialog)
    upload = page.document_upload()
    upload.upload(str(path))
    upload.wait_form()
    page.page.wait_for_timeout(1500)
    shown = value_of(page.wo_snapshot().field(wl.LABEL_CUSTOMER))
    # the form removes emoji from the customer name ('Solar  Corp'): what matters is that the text is shown as text; the rest of the name is kept
    assert shown == value or (kind == "emoji" and shown == "Solar  Corp") or value in page.page.content(), shown
    assert dialogs == [] and "<script>alert('XSS-1')" not in page.page.content(), dialogs
    page.close_form()
    page.page.wait_for_timeout(1500)
    page.page.remove_listener("dialog", on_dialog)
    upload.detach()
    page.historical_quotes().detach()


def test_with_a_form_open_the_upload_option_is_not_offered(landing):
    """Qase UD-FL4 -- the option 'Upload file' only exists on the list of the Quotation module: with a blank quotation form open (unsaved) it is not offered, so a document cannot be uploaded over an unsaved quotation."""
    assert landing.document_upload().is_visible()
    landing.create_quotation()
    landing.page.get_by_text(loc.FORM_MARKER_TEXT, exact=True).wait_for(timeout=20000)
    landing.page.wait_for_timeout(1000)
    assert landing.page.locator("label").filter(has_text=loc.UPLOAD_BUTTON_TEXT).count() == 0     # the file input that stays belongs to 'Attach document' of the form
    assert landing.page.get_by_role("button", name=ql.CREATE_QUOTATION_BUTTON_TEXT).count() == 0
    landing.close_form()


def test_with_an_unsaved_draft_the_upload_asks_what_to_do_before_reading_the_document(role_page, landing):
    """Qase UD-FL12 -- with an unsaved quotation draft in progress, choosing a document asks 'Unsaved Quotation in Progress' with four options and does not read the document until the user chooses:
    Cancel keeps things as they are, 'Discard Draft & Use Document' opens the form with the data of the document (build of 2026-11-09)."""
    landing.create_quotation()
    landing.wo_snapshot().field(wl.LABEL_WO_TITLE).fill("Unsaved draft HU18")
    landing.page.wait_for_timeout(1500)
    landing.close_form()
    landing.page.wait_for_timeout(1000)
    page = QuotationPage(role_page("AM")).open(refresh=True)
    page.historical_quotes().settle()
    upload = page.document_upload()
    upload.upload(docs.HITHIUM_DOCX, unsaved=None)
    assert upload.unsaved_draft_question_visible(timeout_ms=5000)
    text = " ".join(page.page.locator("body").inner_text().split())
    assert loc.UNSAVED_TEXT in text and all(page.page.get_by_role("button", name=option, exact=True).count() == 1 for option in loc.UNSAVED_OPTIONS), text[-400:]
    assert not upload.calls, "the document was sent before the user chose"
    page.page.get_by_role("button", name="Cancel", exact=True).click()
    page.page.wait_for_timeout(1000)
    assert not upload.unsaved_draft_question_visible() and not upload.calls and page.page.get_by_text(loc.FORM_MARKER_TEXT, exact=True).count() == 0
    upload.upload(docs.HITHIUM_DOCX)                       # now 'Discard Draft & Use Document'
    upload.wait_form()
    page.page.wait_for_timeout(1500)
    assert page.wo_snapshot().field(wl.LABEL_WO_TITLE).input_value() != "Unsaved draft HU18"
    page.close_form()
    upload.detach()


# ================================================================================================================ what a good system tells the user (defects of 2026-10-29)
@pytest.mark.parametrize("kind, must_say", [("unrelated text", None), ("password protected docx", "password"), ("scanned pdf", None)], ids=["unrelated text", "protected document", "scanned document"])
def test_the_message_for_a_document_that_cannot_be_read_is_clear_and_says_why(landing, tmp_path, kind, must_say):
    """Qase UD-FL1 / UD-FL5 -- no technical prefix, and a password-protected document is told apart from a document without data (defect #199 fixed in the build of 2026-11-09)."""
    name, build = NO_DATA_FILES[kind]
    path = tmp_path / name
    path.write_bytes(build())
    upload = landing.document_upload()
    upload.upload(str(path))
    message = upload.error_text(timeout_ms=60000)
    assert message and not message.startswith("Bad Request"), message
    if must_say:
        assert must_say in message.lower(), message
    upload.dismiss_toasts()


def test_after_30_seconds_the_user_is_told_that_reading_takes_longer(landing):
    """Qase UD-FL2 -- the reading service does not answer (the call is held in the browser): after 30 seconds a dialog says 'Time limit exceeded' and gives a way out (defect #200 fixed in the build of 2026-11-09)."""
    held = []
    landing.page.route("**/api/quotations/from-document", lambda route: held.append(route))
    try:
        upload = landing.document_upload()
        upload.upload(docs.HITHIUM_DOCX)
        upload.wait_loading()
        message = upload.error_text(timeout_ms=45000)
        assert message == loc.MESSAGE_TIMEOUT and upload.error_title() == loc.DIALOG_TITLE_TIMEOUT, (upload.error_title(), message)
        upload.dismiss_toasts()
        landing.page.wait_for_timeout(1000)
        assert not upload.loading_visible() and landing.page.get_by_role("button", name=ql.CREATE_QUOTATION_BUTTON_TEXT).count() == 1
    finally:
        landing.page.unroute("**/api/quotations/from-document")
        for route in held:
            try:
                route.abort()
            except Exception:
                pass


def test_the_same_document_uploaded_twice_stores_nothing(landing, api_roles):
    """Qase UD-FL3 -- the same document uploaded twice: since the build of 2026-11-09 an upload stores nothing, so no second quotation is created (a duplicate is refused when the AM saves it: see the case of the server)."""
    before = docs.my_quotation_ids(api_roles["AM"])
    upload = landing.document_upload()
    upload.upload(docs.HITHIUM_DOCX)
    upload.wait_form()
    landing.close_form()
    landing.page.wait_for_timeout(1500)
    upload.upload(docs.HITHIUM_DOCX)
    upload.wait_form()
    landing.page.wait_for_timeout(2000)
    assert docs.my_quotation_ids(api_roles["AM"]) == before


def test_a_script_in_the_document_is_shown_as_text_to_the_approver_and_never_executed(role_page, api_roles):
    """Qase UD-FL11 -- the quotation made from a document with a script in the product is sent to the FPM/FSM: the approver sees the text in the Pending approval list and in the form, no alert opens and no script is added to the page."""
    from framework_api.services import quotation_setup
    marker = "Approver4711"
    lines = ["Customer Name: Approver Corp", "Project Name: Approver Field", "Site Address: 1 Approver Road, Austin, TX", f"Product: {marker} <i>italic</i> <script>alert('XSS-4')</script>", "Quantity: 5"]
    response = docs.upload(api_roles["AM"], "approver.docx", docs.build_docx(lines), docs.MIME_DOCX)
    assert response.status_code == 200, response.text[:200]
    assert marker in response.json()["device"], response.json()["device"]                       # the data read from the document keeps the text
    import time
    title = f"Workflow Progress test HU18-{marker}-{time.time_ns() // 1000000 % 10**9} <i>italic</i> <script>alert('XSS-4')</script>"   # unique: the server refuses a second quotation with the same title
    quotation_setup.create_and_submit(api_roles["AM"], api_roles, "xss", ["FPM"], title_prefix="HU18", extra={"title": title, "device": response.json()["device"]})
    fpm = role_page("FPM")
    dialogs = []
    fpm.on("dialog", lambda dialog: (dialogs.append(dialog.message), dialog.dismiss()))
    page = QuotationPage(fpm).open(refresh=True)
    page.open_listed_quotation(marker)
    fpm.wait_for_timeout(1500)
    assert dialogs == [] and "<script>alert('XSS-4')" not in fpm.content(), dialogs


