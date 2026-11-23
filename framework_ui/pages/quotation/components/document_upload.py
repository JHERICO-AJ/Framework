"""DocumentUpload -- reusable component: the 'Upload file' option of the Quotation landing page (OP-17 / HU-18) and what follows it:
the loading panel, the error toasts and the pre-filled form.

See document_upload_locators.py for everything confirmed live about the markup. The component listens to the calls to
POST /api/quotations/from-document, so a test can assert that a file was refused in the browser (no call) or sent (one call) and how long the form took to open.
"""
from __future__ import annotations

import re
import time

from playwright.sync_api import TimeoutError as PlaywrightTimeout

from framework_ui.base.base_component import BaseComponent
from framework_ui.pages.quotation.components import document_upload_locators as loc


class DocumentUpload(BaseComponent):
    def __init__(self, page):
        super().__init__(page, root=page)
        self.calls = []                       # (method, url) of every call to the upload endpoint since this object was created
        self.answers = []                     # (status, body text) of each answer
        self.started_at = None
        page.on("request", self._on_request)
        page.on("response", self._on_response)

    def detach(self):
        """Stops listening (a page is shared by many tests)."""
        self.page.remove_listener("request", self._on_request)
        self.page.remove_listener("response", self._on_response)

    def _on_request(self, request):
        if loc.FROM_DOCUMENT_URL_PART in request.url:
            self.calls.append((request.method, request.url))

    def _on_response(self, response):
        if loc.FROM_DOCUMENT_URL_PART in response.url:
            try:
                text = response.text()
            except Exception:
                text = ""
            self.answers.append((response.status, text))

    # ---- the option ---------------------------------------------------------------------------------------------------------------
    def label(self):
        return self.page.locator("label").filter(has_text=loc.UPLOAD_BUTTON_TEXT).first

    def is_visible(self, timeout_ms=5000):
        """True when the option shows up within the time (the landing page paints it a moment after the list)."""
        try:
            self.page.locator("label").filter(has_text=loc.UPLOAD_BUTTON_TEXT).first.wait_for(timeout=timeout_ms)
            return True
        except PlaywrightTimeout:
            return False

    def file_input(self):
        return self.page.locator(loc.FILE_INPUT).first

    def accept(self):
        return self.file_input().get_attribute("accept")

    def allows_several(self):
        return self.file_input().evaluate("e => e.multiple")

    def input_count(self):
        return self.page.locator(loc.FILE_INPUT).count()

    # ---- uploading ----------------------------------------------------------------------------------------------------------------
    def upload(self, path, unsaved="Discard Draft & Use Document"):
        """Chooses the file (the same as the user does in the file window) and starts the clock. Since the build of 2026-11-09, when an unsaved quotation draft is in progress the page first asks what
        to do ('Unsaved Quotation in Progress'): `unsaved` is the button to press ('Discard Draft & Use Document' by default so that the upload goes on), or None to leave the question open."""
        self.calls.clear()
        self.answers.clear()
        self.started_at = time.monotonic()
        self.file_input().set_input_files(path)
        if unsaved:
            self.answer_unsaved_draft(unsaved)
            self.started_at = time.monotonic()
        return self

    def unsaved_draft_question_visible(self, timeout_ms=0):
        try:
            self.page.get_by_text(loc.UNSAVED_TITLE, exact=True).first.wait_for(timeout=timeout_ms or 1)
            return True
        except PlaywrightTimeout:
            return False

    def answer_unsaved_draft(self, option, timeout_ms=2500):
        """Presses `option` of the question about the unsaved draft if it shows up within the time; returns True when it did."""
        if not self.unsaved_draft_question_visible(timeout_ms):
            return False
        self.page.get_by_role("button", name=option, exact=True).click()
        return True

    def loading_visible(self):
        return self.page.get_by_text(loc.LOADING_TITLE, exact=True).count() > 0

    def loading_text_visible(self):
        return self.page.get_by_text(loc.LOADING_TEXT, exact=True).count() > 0

    def wait_loading(self, timeout_ms=15000):
        self.page.get_by_text(loc.LOADING_TITLE, exact=True).wait_for(timeout=timeout_ms)
        return self

    def wait_form(self, timeout_ms=60000):
        """Waits until the form opens and returns the seconds since the file was chosen."""
        self.page.get_by_text(loc.FORM_MARKER_TEXT, exact=True).wait_for(timeout=timeout_ms)
        return time.monotonic() - self.started_at

    def quotation_id_from_url(self):
        return self.page.url.rstrip("/").split("/")[-1]

    def error_dialog(self):
        return self.page.locator(loc.DIALOG).filter(has_text=re.compile(f"{loc.DIALOG_TITLE}|{loc.DIALOG_TITLE_TIMEOUT}")).first

    def error_text(self, timeout_ms=8000):
        """The message of the error dialog that shows up (without its title and its Close button), or '' when none shows up."""
        dialog = self.error_dialog()
        try:
            dialog.wait_for(timeout=timeout_ms)
        except PlaywrightTimeout:
            return ""
        text = " ".join(dialog.inner_text().split())
        for title in (loc.DIALOG_TITLE, loc.DIALOG_TITLE_TIMEOUT):
            text = text.replace(title, "", 1)
        return re.sub(r"\s*Close$", "", text).strip()

    def error_title(self):
        dialog = self.error_dialog()
        return " ".join(dialog.get_by_role("heading").first.inner_text().split()) if dialog.count() and dialog.get_by_role("heading").count() else ""

    def wait_idle(self, timeout_ms=60000):
        """Waits until the loading panel is gone (the form opened or an error came back)."""
        self.page.get_by_text(loc.LOADING_TITLE, exact=True).wait_for(state="detached", timeout=timeout_ms)
        return self

    def dismiss_toasts(self):
        """Closes the error dialog if it is open (the name comes from the toasts of the build of 2026-10-28)."""
        dialog = self.error_dialog()
        if dialog.count():
            try:
                dialog.get_by_role("button", name="Close").first.click(timeout=2000)
            except Exception:
                pass
