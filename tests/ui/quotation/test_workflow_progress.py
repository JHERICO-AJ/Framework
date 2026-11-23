"""Quotation module -- Workflow Progress widget (OP-25 / HU-07, Qase suite
45).

Cross-checked against Jira OP-25's 5 Acceptance Criteria, HUsACC (identical
5 ACs), and Quotation_Spec_bilingual_V13/V14's much deeper Section 9
(AC-9.0 through AC-9.12, one sub-section per node across the entire
quotation lifecycle). Scope discipline: the Sprint 1 Test Plan explicitly
places "the approval workflow after Submit... actions taken by the BU
Manager, COO, Vendor or FSE" out of scope, so this file never tries to
reach BU/Vendor/FSE-actioned states (only Manual Creation -> WO Quoting ->
BU Reviewing, the one transition reachable purely by an AM completing and
submitting a quotation in Sprint 1).

All 5 ACs pass. Defect #112 (timestamps in UTC) was fixed and re-verified 2026-10-08. See workflow_progress.py's
module docstring for full detail on the two distinct error states and the
timestamp-vs-"Pending" distinction backing AC #2.
"""
import re

import pytest
from playwright.sync_api import expect

QUOTATION_BY_ID_PATTERN = re.compile(r"/api/quotations/\d+(\?|$)")

from framework_ui.pages.quotation.components import workflow_progress_locators as loc

from tests.ui.quotation.support import submit_a_full_quotation

pytestmark = pytest.mark.ui


@pytest.fixture(autouse=True)
def _unroute_quotations_safety_net(quotation_page):
    """Defensive: guarantees the quotations-by-id route block from the two
    error-state tests never leaks into a later test if one of them errors
    before reaching its own page.unroute() call (logged_in_page is
    session-scoped, so a stuck block would otherwise break every
    subsequent test's create_quotation())."""
    yield
    try:
        quotation_page.page.unroute(QUOTATION_BY_ID_PATTERN)
    except Exception:
        pass


def _open_existing_quotation_expecting_failure(quotation_page, wo_number_query):
    """Like QuotationPage.open_existing_quotation(), but never waits for
    the "WO Snapshot" success marker -- used only by the page-level
    error-state test below, where that marker is expected to never
    appear."""
    page = quotation_page.page
    from framework_ui.pages.quotation import quotation_locators as qloc
    page.wait_for_timeout(1000)
    page.get_by_placeholder(qloc.WO_NUMBER_SEARCH_PLACEHOLDER).fill(wo_number_query)
    page.keyboard.press("Enter")
    page.wait_for_timeout(1000)
    page.locator(qloc.WO_LIST_ROW_WO_NUMBER).first.click()


def test_diagram_opens_with_five_levels(quotation_page):
    """OP-25 AC #1: a graphical, read-only representation of the workflow
    progress across its 5 levels."""
    quotation_page.create_quotation()
    wfp = quotation_page.workflow_progress().open()
    expect(quotation_page.page.get_by_text(loc.MODAL_HEADING)).to_be_visible()
    for heading in wfp.column_headings():
        expect(heading).to_be_visible()
    wfp.close()
    quotation_page.close_form()


def test_read_only_clicking_a_future_node_does_not_change_state(quotation_page):
    """OP-25 AC #3: no action available in this view can alter the
    quotation status -- a not-yet-reached node."""
    quotation_page.create_quotation()
    wfp = quotation_page.workflow_progress().open()
    before = wfp.current_step_text()
    wfp.node("BU Review").click()
    quotation_page.page.wait_for_timeout(300)
    assert wfp.current_step_text() == before
    wfp.close()
    quotation_page.close_form()


def test_accessible_from_quotation_detail_screen(quotation_page):
    """OP-25 AC #4: reachable from the quotation detail screen (present as
    soon as the WO Creation form is open)."""
    quotation_page.create_quotation()
    expect(quotation_page.workflow_progress().trigger_button()).to_be_visible()
    quotation_page.close_form()


def test_error_state_on_whole_quotation_load_failure(quotation_page):
    """OP-25 AC #5: if workflow data cannot be loaded, show an error state
    -- reproduced by blocking the per-record fetch before reopening an
    already-saved quotation (a brand-new, unsaved one has no such fetch to
    fail)."""
    quote_number = submit_a_full_quotation(quotation_page, "WFP-ERR-PAGE")
    page = quotation_page.page
    page.route(QUOTATION_BY_ID_PATTERN, lambda route: route.abort())
    _open_existing_quotation_expecting_failure(quotation_page, quote_number)
    page.wait_for_timeout(1500)
    expect(page.get_by_text(loc.PAGE_LEVEL_LOAD_FAILURE_TEXT, exact=True)).to_be_visible()
    page.unroute(QUOTATION_BY_ID_PATTERN)
    close_error_btn = page.get_by_role("button", name="CLOSE", exact=True)
    if close_error_btn.count() > 0:
        close_error_btn.first.click()


# test_error_state_on_widget_only_load_failure lives in its own file,
# test_workflow_progress_widget_error.py -- it needs a genuinely fresh
# browser session (the widget's own fetch renders from cache instead of
# failing if the record was ever opened successfully even once before
# going offline), which this file's other 6 tests would otherwise pollute
# if run in the same pytest invocation.


def test_completed_and_current_steps_are_distinguishable_and_read_only(quotation_page):
    """OP-25 AC #2 + AC #3 (extended): once a step is genuinely completed
    (via a real Submit, not just Save Draft), its status text becomes a
    timestamp instead of "Pending", the current step carries the
    current-step glow, and clicking either the completed or the current
    node still doesn't change the current step."""
    quote_number = submit_a_full_quotation(quotation_page, "WFP-STATE")
    page = quotation_page.page
    quotation_page.open_existing_quotation(quote_number)
    page.wait_for_timeout(1000)
    wfp = quotation_page.workflow_progress().open()

    expect(page.locator("p", has_text=loc.CURRENT_STEP_TEXT_PREFIX)).to_have_text(
        "Current step: BU Review")
    assert "Pending" not in wfp.node_status_text("Manual Creation")
    assert "Pending" not in wfp.node_status_text("WO Quoting")
    assert wfp.is_node_current("BU Review")
    assert not wfp.is_node_current("Manual Creation")

    before = wfp.current_step_text()
    wfp.node("Manual Creation").click()
    page.wait_for_timeout(300)
    assert wfp.current_step_text() == before
    wfp.node("BU Review").click()
    page.wait_for_timeout(300)
    assert wfp.current_step_text() == before

    wfp.close()
    quotation_page.close_form()


def test_completed_step_timestamp_reflects_local_time_not_utc(quotation_page):
    """Qase #112: FIXED, re-verified 2026-10-08. A completed node's timestamp matches the app's own local time
    (the sidebar's 'Local Time'), not raw UTC -- otherwise it could show a different calendar day than when the step
    actually completed (browser in GMT-4: 09:27 local vs 13:27 UTC)."""
    page = quotation_page.page
    local_minute = (
        "() => { const d = new Date(); "
        "return d.getFullYear() + '-' + String(d.getMonth()+1).padStart(2,'0') + '-' + "
        "String(d.getDate()).padStart(2,'0') + ' ' + String(d.getHours()).padStart(2,'0') + ':' + "
        "String(d.getMinutes()).padStart(2,'0'); }")
    local_before = page.evaluate(local_minute)
    quote_number = submit_a_full_quotation(quotation_page, "WFP-TZ")
    local_after = page.evaluate(local_minute)
    quotation_page.open_existing_quotation(quote_number)
    page.wait_for_timeout(1000)
    wfp = quotation_page.workflow_progress().open()
    node_status = wfp.node_status_text("WO Quoting").strip()
    # the submit can cross a minute boundary: the node must fall between the local minute before and after it
    # (UTC would be hours away from both)
    assert local_before <= node_status <= local_after, (
        f"node shows {node_status!r}, local time was {local_before!r}..{local_after!r}")
