"""Quotation module -- Workflow Progress widget (OP-25 / HU-07, Qase suite
45, case #917): the widget's own dedicated load-failure state.

Kept in its own file, separate from test_workflow_progress.py, because it
needs a genuinely fresh browser session: the widget's own fetch renders
from an in-memory cache instead of failing if the record was ever opened
successfully even once before going offline. Run this file on its own
(never bundled with test_workflow_progress.py in the same pytest
invocation) so the session-scoped browser fixture starts clean:

    pytest tests/ui/quotation/test_workflow_progress_widget_error.py

Confirmed real via the user's own manual DevTools reproduction (Offline
mode, applied after opening a saved quotation, then clicking the trigger
button) on 2026-09-27/28, and matched exactly by this automated repro.
"""
import pytest
from playwright.sync_api import expect

from framework_ui.pages.quotation.components import workflow_progress_locators as loc

pytestmark = pytest.mark.ui


def test_error_state_on_widget_only_load_failure(quotation_page):
    """OP-25 AC #5, widget-scoped: the diagram itself has its own error
    state, distinct from the whole-quotation page-level failure -- only
    reproducible by cutting the network for the FIRST time a record is
    ever opened in this browser session, then clicking the trigger."""
    page = quotation_page.page
    from tests.ui.quotation.support import submit_a_full_quotation
    quote_number = submit_a_full_quotation(quotation_page, "WFP-ERR-WIDGET")

    # Now on the list, with network still on -- go offline BEFORE ever
    # opening this record, then open it for the first time by clicking
    # its already-rendered row directly (no search, which itself needs
    # network and would fail before we even get to the widget).
    page.context.set_offline(True)
    try:
        page.get_by_text(quote_number, exact=False).first.click(timeout=15000)
        page.wait_for_timeout(1000)
        quotation_page.workflow_progress().trigger_button().click()
        expect(page.get_by_text(loc.WIDGET_LEVEL_LOAD_FAILURE_HEADING, exact=True)).to_be_visible(timeout=10000)
    finally:
        page.context.set_offline(False)
