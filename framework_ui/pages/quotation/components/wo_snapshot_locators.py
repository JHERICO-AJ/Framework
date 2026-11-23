"""Selectors for the WO Snapshot section of the Quotation (WO) Creation
form.

Confirmed against the real deployed app (2026-09-22): fields have NO id/name
attributes -- each is a plain <label>text</label> immediately followed by
its <input>/<select> inside a shared "div.flex.flex-col.gap-1" container,
and a field-level validation error (when present) is a
"p.text-red-400" sibling inside that same container. Field lookup is by
label text, not by id.

Real field order in the DOM (12 fields -- confirmed DIFFERENT from the
documented 9-field spec, see wo_snapshot.py's module docstring for the
diff): GSP # / Alarm ID, Quote # / WO Number, OEM Name, Customer, WO Title,
Site Name, Type of Work, Site Location, Unit Info, Units, Device, Severity.
"""
SECTION_HEADING_TEXT = "WO Snapshot"
FIELD_CONTAINER = "div.flex.flex-col.gap-1"
ERROR_TEXT = "p.text-red-400"

# --- field labels, exactly as rendered ---
LABEL_GSP_ALARM_ID = "GSP #"  # was "GSP # / Alarm ID" until the 2026-11-09 deployment (a quotation is no longer created from an alarm)
LABEL_QUOTE_WO_NUMBER = "Quote # / WO Number"
LABEL_OEM_NAME = "OEM Name"
LABEL_CUSTOMER = "Customer"
LABEL_WO_TITLE = "WO Title"
LABEL_SITE_NAME = "Site Name"
LABEL_TYPE_OF_WORK = "Type of Work"
LABEL_SITE_LOCATION = "Site Location"
LABEL_UNIT_INFO = "Unit Info"
LABEL_UNITS = "Units"
LABEL_DEVICE = "Device"
LABEL_SEVERITY = "Severity"

# The real, live DOM order (top to bottom, left-to-right in the 2-column
# grid) -- used by the "documented field order" test.
REAL_FIELD_ORDER = [
    LABEL_GSP_ALARM_ID, LABEL_QUOTE_WO_NUMBER, LABEL_OEM_NAME, LABEL_CUSTOMER,
    LABEL_WO_TITLE, LABEL_SITE_NAME, LABEL_TYPE_OF_WORK, LABEL_SITE_LOCATION,
    LABEL_UNIT_INFO, LABEL_UNITS, LABEL_DEVICE, LABEL_SEVERITY,
]

# The 9 fields and order OP-19 / HUsACC / V13 document (AC-5.0.1).
DOCUMENTED_FIELD_ORDER = [
    LABEL_GSP_ALARM_ID, LABEL_QUOTE_WO_NUMBER, LABEL_OEM_NAME, LABEL_WO_TITLE,
    LABEL_SITE_NAME, LABEL_SITE_LOCATION, LABEL_TYPE_OF_WORK, LABEL_UNIT_INFO,
    LABEL_UNITS, LABEL_DEVICE, LABEL_SEVERITY,
]

# AC-5.7.1 documents 5 Type Of Work values; the live dropdown only offers 4.
DOCUMENTED_TYPE_OF_WORK_OPTIONS = [
    "Commissioning", "Rework", "Warranty Repair", "Chargeable Repair", "PMP",
]

# AC-5.9.2 documents 5 Severity values -- the live field is free text, so
# this is kept only as the reference list the xfail test checks against.
DOCUMENTED_SEVERITY_VALUES = ["Critical", "Major", "Minor", "Warning", "Normal"]
