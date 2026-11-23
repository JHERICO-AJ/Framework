"""Quotation module -- what the FPM/FSM can edit while they are the current approver (OP-23 / HU-15; Qase suite "HU-15: BU and OEM view of the Budget Summary", cases FE*).

HU-15 'Permissions and roles': 'While they are the current approver, an FPM/FSM must be able to edit only Signal, Trigger, Cause, Notes and SOP/Steps; attachments must be read-only for them.'
Observed on the QA build of 2026-10-23: besides the three controls of the top bar (site filter, period, search) and the Recommendation box of the decision bar, those five fields are the only
editable controls on the page, in a Flat Rate and in an FSE Select quotation; the attachment list shows the file with no way to add or remove one.
"""
import pathlib
import re

import pytest

from framework_api.services import quotation_setup as qs
from framework_ui.pages.quotation.quotation_page import QuotationPage

pytestmark = pytest.mark.ui

DIAGNOSIS = ["SIGNAL", "TRIGGER", "CAUSE", "NOTES", "SOP / STEPS"]
TOP_BAR_CONTROLS = 3
RECOMMENDATION = 1

CONTROLS = ("() => Array.from(document.querySelectorAll('input,textarea,select')).filter(e => !e.disabled && !e.readOnly && e.type !== 'hidden' && e.type !== 'file')"
            ".map(e => e.getAttribute('aria-label') || e.placeholder || e.name || e.tagName)")
ATTACHMENT_CONTROLS = r"""() => {
    const note = Array.from(document.querySelectorAll('*')).find(e => e.children.length === 0 && /new files? in this session/.test(e.textContent));
    const box = note.closest('div').parentElement;
    return {
        file_inputs: document.querySelectorAll('input[type=file]').length,
        buttons: Array.from(box.querySelectorAll('button')).filter(b => b.offsetParent).map(b => b.innerText.trim() || b.getAttribute('aria-label') || b.title || '?'),
        text: box.innerText.replace(/\s+/g, ' ').trim(),
    };
}"""
PDF = b"%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj 2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj 3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 200 200]>>endobj\ntrailer<</Root 1 0 R>>\n%%EOF"


@pytest.fixture(scope="module")
def flat(make_quotation):
    return make_quotation("FE", ["FPM"], title_prefix="HU15")[0]


@pytest.fixture(scope="module")
def select(make_quotation):
    return make_quotation("FE", ["FPM"], title_prefix="HU15", extra=qs.three_engineers())[0]


@pytest.fixture(scope="module")
def with_attachment(role_page, make_draft, quotation_api, tmp_path_factory):
    """A quotation the AM attached a PDF to (through the screen, then Save Draft) and submitted to the FPM/FSM. Also keeps what the AM could do with the attachment while it was a Draft."""
    qid = make_draft("FEATT")[0]
    f = pathlib.Path(tmp_path_factory.mktemp("att")) / "evidence_note.pdf"
    f.write_bytes(PDF)
    qp = QuotationPage(role_page("AM")).open_by_link(qid)
    qp.page.locator("input[type=file]").first.set_input_files(str(f))
    qp.page.get_by_text("evidence_note", exact=False).first.wait_for(timeout=10000)
    am_controls = qp.page.evaluate(ATTACHMENT_CONTROLS)
    qp.save_draft()
    qp.page.wait_for_timeout(4000)
    assert quotation_api["AM"].submit(qid).status_code == 200
    return qid, am_controls


@pytest.mark.parametrize("quotation", ["flat", "select"])
@pytest.mark.parametrize("label", DIAGNOSIS)
def test_the_fpm_can_edit_signal_trigger_cause_notes_and_sop_steps(role_page, request, quotation, label):
    """Qase HU15-FE1 (Signal), FE2 (Trigger), FE3 (Cause), FE4 (Notes), FE5 (SOP/Steps) -- in a Flat Rate and in an FSE Select quotation."""
    qp = QuotationPage(role_page("FPM")).open_by_link(request.getfixturevalue(quotation))
    field = qp.diagnosis_field(label)
    assert field.is_editable()
    field.click()
    field.press_sequentially("x")
    assert field.input_value() == "x"


@pytest.mark.parametrize("quotation", ["flat", "select"])
def test_nothing_else_can_be_edited_by_the_fpm(role_page, request, quotation):
    """Qase HU15-FE6 (Flat Rate), FE7 (FSE Select) -- the only editable controls are the five fields, the Recommendation and the three controls of the top bar."""
    page = QuotationPage(role_page("FPM")).open_by_link(request.getfixturevalue(quotation)).page
    controls = page.evaluate(CONTROLS)
    assert len(controls) == len(DIAGNOSIS) + RECOMMENDATION + TOP_BAR_CONTROLS, controls
    assert "Recommendation" in controls


def test_the_attachments_are_read_only_for_the_fpm(role_page, with_attachment):
    """Qase HU15-FE8 -- the attachment is listed, and the FPM/FSM cannot attach another file or remove it."""
    qid, am_controls = with_attachment
    assert am_controls["file_inputs"] == 1 and len(am_controls["buttons"]) >= 1, f"the AM must be able to attach and remove while it is a Draft: {am_controls}"
    page = QuotationPage(role_page("FPM")).open_by_link(qid).page
    seen = page.evaluate(ATTACHMENT_CONTROLS)
    assert "evidence_note" in seen["text"] and "1 existing" in seen["text"], seen
    assert seen["file_inputs"] == 0, "the FPM/FSM must not be able to attach a file"
    assert seen["buttons"] == [], f"the FPM/FSM must not get a button to remove or replace the file: {seen['buttons']}"
