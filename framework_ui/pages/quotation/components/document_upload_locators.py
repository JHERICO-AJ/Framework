"""Selectors and texts for the 'Upload file' option of the Quotation landing page (OP-17 / HU-18).

Confirmed live on the QA build of 2026-10-28:
  - The option is a <label title="Create a quotation from a PDF or Word document"> with the text 'Upload file' that holds a hidden
    <input type=file accept=".pdf,.doc,.docx"> (no 'multiple'). It sits at the top right of the landing page, next to 'Create Quotation'.
    Only the AM sees it (FPM, BU and CEO see neither button).
  - Choosing a file calls POST /api/quotations/from-document (multipart, field 'file'); while it runs a centred panel shows
    'Reading the document…' and 'Creating the quotation from its data. This can take a few seconds.'; when it answers the form opens on /quotation/<id>.
  - The type (by extension) and the empty file are refused in the browser before any call; the size too (> 10 MB). The server also checks the content.
  - (2026-10-28) Errors were Toastify toasts with the prefix 'Bad Request '; since 2026-11-09 they are a dialog, see below.
"""
UPLOAD_BUTTON_TEXT = "Upload file"
UPLOAD_LABEL_TITLE = "Prefill a new quotation from a PDF or Word document"   # it said "Create a quotation from a PDF or Word document" on the build of 2026-10-28
FILE_INPUT = "input[type=file]"
ACCEPT = ".pdf,.doc,.docx"
FROM_DOCUMENT_URL_PART = "/api/quotations/from-document"

LOADING_TITLE = "Reading the document…"
LOADING_TEXT = "Creating the quotation from its data. This can take a few seconds."
ERROR_TOAST = "div.Toastify__toast--error"

# Since the build of 2026-11-09 the errors are a dialog (role=dialog) with a title, one message and a Close button; the type, the empty file and the size are still refused in the browser.
DIALOG = "[role=dialog]"
DIALOG_TITLE = "The document could not be used"
DIALOG_TITLE_TIMEOUT = "Time limit exceeded"
MESSAGE_TYPE = "This file type is not supported. Upload a PDF or Word document (.pdf, .doc, .docx) of up to 10 MB."
MESSAGE_SIZE = "The file is too large. Upload a PDF or Word document (.pdf, .doc, .docx) of up to 10 MB."
MESSAGE_EMPTY = "The file is empty. Choose a document that has content."
MESSAGE_SERVER_TYPE = "The file content does not match its extension. Upload a valid PDF or Word document (.pdf, .doc, .docx)."
MESSAGE_NO_DATA = "We could not find quotation data in this document. You can fill in the form manually with Create Quotation."
MESSAGE_PROTECTED = "This document is password-protected. Remove the password and upload it again."
MESSAGE_GENERIC = "Something went wrong while reading the document. Try again or create the quotation manually."
MESSAGE_TIMEOUT = "Reading the document took too long. Please try again later."

UNSAVED_TITLE = "Unsaved Quotation in Progress"
UNSAVED_TEXT = "You have an unsaved quotation draft in progress. Using the uploaded document will replace it. What would you like to do?"
UNSAVED_OPTIONS = ["Continue Current Draft", "Save as Draft & Use Document", "Discard Draft & Use Document", "Cancel"]

MAX_BYTES = 10 * 1024 * 1024
SOURCE_BADGE_TEXT = "Document"
FORM_MARKER_TEXT = "WO Snapshot"
