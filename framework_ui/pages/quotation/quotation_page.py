"""QuotationPage -- the Quotation (WO Creation) module. Delegates each form
section to its own component, same pattern as MonitoringPage."""
from __future__ import annotations

import re

from framework_ui.base.base_page import BasePage
from framework_ui.pages.quotation import quotation_locators as loc
from framework_ui.pages.quotation.alarm_already_quoted import AlarmAlreadyQuoted
from framework_ui.pages.quotation.components.wo_snapshot import WoSnapshot
from framework_ui.pages.quotation.components.fse_arrangement import FseArrangement
from framework_ui.pages.quotation.components.engineer_selection import EngineerSelection
from framework_ui.pages.quotation.components.workflow_progress import WorkflowProgress
from framework_ui.pages.quotation.components.signer_assignment import SignerAssignment
from framework_ui.pages.quotation.components.decision_bar import DecisionBar
from framework_ui.pages.quotation.components.budget_calculator import BudgetCalculator
from framework_ui.pages.quotation.components.budget_summary import BudgetSummary
from framework_ui.pages.quotation.components.historical_quotes import HistoricalQuotes
from framework_ui.pages.quotation.components.quotation_history import QuotationHistory
from framework_ui.pages.quotation.components.document_upload import DocumentUpload


class QuotationPage(BasePage):
    PATH = "/quotation"

    def open(self, refresh=False):
        """Deliberately NOT calling self.goto(): same SPA deep-link
        limitation already documented for MonitoringPage/FleetOverviewPage
        -- navigate via the sidebar link instead.

        refresh=True reloads the page first: neither clicking 'Quotation' again nor going through another module re-fetches the
        landing list (confirmed 2026-10-20), so a quotation created or decided after the list was loaded would be missing; a
        reload keeps the session and does. Used by the approve/reject tests, which look for rows that were just created or decided."""
        if refresh:
            # a quotation form that is still open (an unsaved draft) asks 'leave this page?' (beforeunload) and, with nobody answering, the reload never ends: the reload leaves the page
            def leave(dialog):
                try:
                    if dialog.type == "beforeunload":
                        dialog.accept()
                except Exception:
                    pass          # another handler of the test already answered this dialog
            self.page.on("dialog", leave)
            try:
                self.page.reload()
            finally:
                self.page.remove_listener("dialog", leave)
            self.page.wait_for_load_state("domcontentloaded")
        self._go_to_quotation()
        self.wait_loaded()
        return self

    def _go_to_quotation(self):
        """The deployment of 2026-11-16 took the Quotation link out of the navigation bar: the module is reached only by its URL (/quotation). The link is clicked
        when it is still there (older builds); otherwise the URL is opened -- the session is already signed in, so it does not bounce to /login."""
        from shared.config.settings import BASE_URL
        try:
            self.page.locator(loc.SIDEBAR_LINK).wait_for(timeout=3000)
            self.page.locator(loc.SIDEBAR_LINK).click()
        except Exception:
            self.page.goto(f"{BASE_URL}{self.PATH}", timeout=60000)

    def create_quotation(self):
        """Opens a brand-new, blank WO Creation form (the manual-origin
        path -- as opposed to opening one from an alarm)."""
        self.page.get_by_role("button", name=loc.CREATE_QUOTATION_BUTTON_TEXT).click()
        self._resolve_unsaved_draft_conflict()
        return self

    def create_quotation_from_alarm(self, alarm_name_text, open_existing=False):
        """Opens the WO Creation form from a real alarm's "Create Quotation"
        action (Alarms & Events -> click a row -> its "ALARM DETAILS & SOP"
        panel), instead of the module's own blank "Create Quotation".
        Confirmed live 2026-09-22: this is the only way the app offers to
        exercise the documented alarm-origin pre-fill path.

        Resets to the Quotation list first (a known, stable state) before
        navigating away -- confirmed this avoids an intermittent timeout
        clicking the Alarms link directly after a previous test left the
        SPA in an unexpected state."""
        self._go_to_quotation()
        self.page.wait_for_timeout(500)
        self.page.locator("a.nav-item", has_text="Alarms & Events").click()
        self.page.wait_for_timeout(1000)
        self.page.get_by_text(alarm_name_text, exact=False).first.click()
        self.page.wait_for_timeout(1000)
        self.last_alarm_panel = self._read_alarm_panel()
        self.page.get_by_role("button", name=loc.CREATE_QUOTATION_BUTTON_TEXT, exact=True).click()
        self._raise_if_alarm_already_quoted(open_existing=open_existing)
        self._resolve_unsaved_draft_conflict()
        return self

    def _read_alarm_panel(self):
        """The label/value pairs of the selected alarm's "ALARM DETAILS & SOP"
        overview (e.g. {"ALARM ID": "38", "SITE": "BOLIVIA", "DEVICE SOURCE":
        "PCS-1", ...}), read right after the alarm row is clicked."""
        lines = self.page.evaluate("""() => {
            const els = [...document.querySelectorAll('*')].filter(
                e => e.children.length === 0 && e.textContent.trim().toLowerCase() === 'alarm id');
            const e = els[els.length - 1];
            if (!e) return [];
            let box = e;
            while (box.parentElement && !box.innerText.includes('DEVICE SOURCE')) box = box.parentElement;
            return box.innerText.split(String.fromCharCode(10));
        }""")
        lines = [x.strip() for x in lines if x.strip()]
        return {lines[i]: lines[i + 1] for i in range(0, len(lines) - 1, 2)}

    def _raise_if_alarm_already_quoted(self, open_existing=False):
        """Waits for whichever comes first after "Create Quotation": the new
        form, the HU-20 unsaved-draft modal, or the "Alarm already quoted"
        modal -- and raises AlarmAlreadyQuoted (after cancelling the modal)
        in the last case."""
        quoted = self.page.get_by_text("Alarm already quoted", exact=True)
        discard = self.page.get_by_role("button", name=loc.DISCARD_AND_START_NEW_BUTTON_TEXT)
        heading = self.page.get_by_text(loc.FORM_LOADED_MARKER_TEXT, exact=True)
        quoted.or_(discard).or_(heading).first.wait_for(timeout=15000)
        if quoted.count() > 0:
            if open_existing:
                self.page.get_by_role("button", name="Open quotation").click()
                heading.wait_for(timeout=15000)
                return
            text = self.page.locator("div.fixed.inset-0").last.inner_text()
            self.page.get_by_role("button", name="Cancel", exact=True).click()
            raise AlarmAlreadyQuoted(text)

    def open_current_quote(self):
        """Reopens the single, currently in-progress draft via the landing
        page's "Current Quote" shortcut (HU-20)."""
        self.page.get_by_role("button", name=loc.CURRENT_QUOTE_BUTTON_TEXT).click()
        self.page.get_by_text(loc.FORM_LOADED_MARKER_TEXT, exact=True).wait_for(timeout=15000)
        return self

    def open_existing_quotation(self, wo_number):
        """Opens a real, already-existing quotation by its WO Number, via
        the landing list's own search box -- for verifying WO Snapshot
        behavior on a real record already past the Draft stage (as opposed
        to the blank/alarm/draft flows the other open_* methods cover)."""
        self.page.wait_for_timeout(1500)
        self.page.get_by_placeholder(loc.WO_NUMBER_SEARCH_PLACEHOLDER).fill(wo_number)
        self.page.keyboard.press("Enter")
        self.page.wait_for_timeout(1500)
        self.page.get_by_text(wo_number).first.click()   # the row of the list (its markup changed in the 2026-10 build)
        self.page.get_by_text(loc.FORM_LOADED_MARKER_TEXT, exact=True).wait_for(timeout=15000)
        return self

    def _resolve_unsaved_draft_conflict(self):
        """HU-20: if a draft from a previous, un-discarded session already
        exists in localStorage, "Create Quotation" shows the
        "Unsaved Quotation in Progress" conflict modal instead of opening a
        blank form directly -- always discard it here, since every test in
        this suite wants a genuinely blank starting point."""
        discard_button = self.page.get_by_role("button", name=loc.DISCARD_AND_START_NEW_BUTTON_TEXT)
        heading = self.page.get_by_text(loc.FORM_LOADED_MARKER_TEXT, exact=True)
        discard_button.or_(heading).first.wait_for(timeout=15000)
        if discard_button.count() > 0:
            discard_button.click()
            heading.wait_for(timeout=15000)

    def open_listed_quotation(self, title):
        """Opens a quotation from whichever landing list is showing (Quotes in Progress for the AM, Pending
        approval for an approver) by clicking its WO Title -- titles are unique in the tests."""
        self.page.get_by_text(title, exact=False).first.wait_for(timeout=20000)
        self.page.get_by_text(title, exact=False).first.click()
        self.page.get_by_text(loc.FORM_LOADED_MARKER_TEXT, exact=True).wait_for(timeout=15000)
        return self

    def historical_quotes(self) -> HistoricalQuotes:
        """The landing list component (tabs, filters, search, table, pager). One instance per page object: it listens to the list calls."""
        if getattr(self, "_historical_quotes", None) is None:
            self._historical_quotes = HistoricalQuotes(self.page)
        return self._historical_quotes

    def quotation_history(self) -> QuotationHistory:
        """The history drawer ('Quotation workflow') that opens from the Status of a row (HU-06). One instance per page object: it counts the events calls."""
        if getattr(self, "_quotation_history", None) is None:
            self._quotation_history = QuotationHistory(self.page)
        return self._quotation_history

    def document_upload(self) -> DocumentUpload:
        """The 'Upload file' option and what follows it (HU-18). One instance per page object: it listens to the calls to the upload endpoint."""
        if getattr(self, "_document_upload", None) is None:
            self._document_upload = DocumentUpload(self.page)
        return self._document_upload

    def open_historical_quotes(self):
        """Switches the landing list to the 'Historical Quotes' tab (row_text then reads its rows). Confirmed 2026-10-26: a quotation the
        OEM approved is listed there with the step 'Ready for Client' and the status 'Approved'."""
        self.historical_quotes().open_historical()
        return self

    def listed_titles(self):
        """WO Titles of the rows of the landing list that is showing."""
        self.page.wait_for_timeout(1500)
        return self.page.locator("tbody tr, [role=row]").all_inner_texts()

    def pending_approval_count(self):
        """The N of the 'Pending approval (N)' pill of an approver's landing view (0 if not shown)."""
        self.page.wait_for_timeout(1500)
        pill = self.page.get_by_text(re.compile(r"Pending approval\s*\(\d+\)")).first
        if pill.count() == 0:
            return 0
        return int(re.search(r"\((\d+)\)", pill.inner_text()).group(1))

    def _row(self, title):
        """The landing-list row of a WO Title: the deepest element that holds the title and a button (the status pill)."""
        return self.page.locator("div, tr, li").filter(has_text=title).filter(has=self.page.get_by_role("button")).last

    def row_text(self, title):
        """Text of the landing-list row that holds the given WO Title (quote #, step, status...), or '' if absent."""
        self.page.wait_for_timeout(1000)
        row = self._row(title)
        return row.inner_text() if row.count() else ""

    def open_workflow_history(self, title):
        """Clicks the status pill of the quotation's row in the landing list: a side panel 'Quotation Workflow' opens with the
        history (who, role, outcome, recommendation and date of every submit and decision). Confirmed 2026-10-20."""
        self._row(title).get_by_role("button").last.click()
        self.page.get_by_text(re.compile(r"^quotation workflow$", re.I)).first.wait_for(timeout=10000)
        self.page.wait_for_timeout(800)
        return self

    def workflow_history_text(self):
        """Text of the open 'Quotation Workflow' panel."""
        return self.page.evaluate("""() => {
            const h = Array.from(document.querySelectorAll('*')).find(e => e.children.length === 0 && /^quotation workflow$/i.test((e.textContent || '').trim()));
            if (!h) return '';
            let el = h;
            for (let i = 0; i < 6 && el.parentElement; i++) { el = el.parentElement; if ((el.innerText || '').includes('Waiting on')) break; }
            return el.innerText || '';
        }""")

    def diagnosis_field(self, label):
        """The input/textarea of one DIAGNOSIS field (SIGNAL, TRIGGER, CAUSE, NOTES, SOP / STEPS)."""
        container = self.page.locator("div.flex.flex-col.gap-1").filter(
            has=self.page.get_by_text(re.compile(rf"^{re.escape(label)}$", re.I)))
        return container.locator("input, textarea").first

    def open_by_link(self, quotation_id):
        """Opens a quotation by its own link (/quotation/<id>) -- the SPA has one per quotation (the session must be fully
        signed in first: a link opened while the login redirect is still running lands on /login). The QA environment is
        sometimes slow after a deployment, so if the form does not show up in 25 s the page is reloaded once."""
        from playwright.sync_api import TimeoutError as PlaywrightTimeout
        from shared.config.settings import BASE_URL
        marker = self.page.get_by_text(loc.FORM_LOADED_MARKER_TEXT, exact=True)
        discard = self.page.get_by_role("button", name="Discard Draft & Edit Quotation")
        self.page.goto(f"{BASE_URL}/quotation/{quotation_id}", timeout=60000)
        try:
            marker.or_(discard).first.wait_for(timeout=25000)
        except PlaywrightTimeout:
            self.page.reload(timeout=60000)
            marker.or_(discard).first.wait_for(timeout=30000)
        if discard.count() > 0:
            # HU-20: a draft typed in this browser and never saved makes the app ask what to do before opening another quotation
            discard.click()
            marker.wait_for(timeout=25000)
        return self

    def rejected_banner_text(self):
        """Full text of the 'Rejected by <name> <role> <date> : <recommendation>' banner, or '' when it is not shown."""
        label = self.page.get_by_text(re.compile("Rejected by")).first
        label.wait_for(timeout=10000)
        return label.locator("xpath=..").inner_text()

    def budget_summary(self) -> BudgetSummary:
        return BudgetSummary(self.page)

    def budget_calculator(self) -> BudgetCalculator:
        return BudgetCalculator(self.page)

    def decision_bar(self) -> DecisionBar:
        return DecisionBar(self.page)

    def wo_snapshot(self) -> WoSnapshot:
        return WoSnapshot(self.page)

    def fse_arrangement(self) -> FseArrangement:
        return FseArrangement(self.page)

    def engineer_selection(self) -> EngineerSelection:
        return EngineerSelection(self.page)

    def workflow_progress(self) -> WorkflowProgress:
        return WorkflowProgress(self.page)

    def signer_assignment(self) -> SignerAssignment:
        return SignerAssignment(self.page)

    def submit_quotation(self):
        self.page.get_by_role("button", name=loc.SUBMIT_QUOTATION_BUTTON_TEXT).click()
        return self

    def save_draft(self):
        self.page.get_by_role("button", name=loc.SAVE_DRAFT_BUTTON_TEXT).click()
        return self

    def close_form(self):
        # exact=True: the date pickers (react-datepicker) add their own "Close" icon
        # buttons once a date is set, so a case-insensitive "CLOSE" matches 3 elements.
        self.page.get_by_role("button", name=loc.CLOSE_BUTTON_TEXT, exact=True).click()
        return self
