"""QuotationDocumentService -- the 'Upload file' option of the Quotation module through the API (OP-17 / HU-18), and the test documents.

POST /api/quotations/from-document (multipart, field 'file', AM only) reads the document with the extraction service of HU-03, creates the quotation (status Draft, source DOCUMENTO)
and answers 201 with it. The extraction is made by an AI service, so its answer for a free text is not always the same: the tests compare only what the Hithium template says in plain
words (HITHIUM_EXPECTED) and the documents they build themselves (build_pdf, build_docx) with the same plain 'Label: value' lines.
"""
from __future__ import annotations

import io
import os
import random
import zipfile

from framework_api.client.role_session import RoleApiSession

PATH = "/api/quotations/from-document"
MAX_BYTES = 10 * 1024 * 1024
MIME_DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
MIME_DOC = "application/msword"
MIME_PDF = "application/pdf"

_DOCS = os.path.join(os.path.dirname(__file__), "..", "..", "docs", "Quotation")
HITHIUM_DOCX = os.path.abspath(os.path.join(_DOCS, "Hithium Service RFP_Raven Cold Cx 1.docx"))
HITHIUM_DOC = os.path.abspath(os.path.join(_DOCS, "Hithium Service RFP_Raven Cold Cx 1.doc"))      # the same document saved by Word as 'Word 97-2003' (a real binary .doc)

# What the Hithium template says in plain words, as the system must pre-fill it (verified 2026-10-28 with the .docx and the .doc).
HITHIUM_EXPECTED = {
    "customerName": "Hithium Energy Storage", "title": "Hithium 5.016MWh BESS",
    "siteLocation": "11174 North Tidwell Prairie Rd, Bremond, TX 76629", "units": 96, "device": "Hithium 5.016MWh BESS", "sopDescription": "Contact Jonathan for SOP.",
}
HITHIUM_ARRANGEMENT = {"supportEngineers": 4, "workingHourTechDay": 10, "estimatedWorkingDays": 15}   # the man hours (600) are calculated by the form since the build of 2026-11-09
# The template has no 'OEM' line: the AI sometimes answers 'Hithium' and sometimes the whole customer name, so only that it names Hithium is checked.
HITHIUM_OEM_TOKEN = "Hithium"
# The fields the template does not give (Type of Work 'Half Year PMP' is not one of the four options of the list).
HITHIUM_EMPTY = ["typeOfWork", "unitInfo", "severity", "signal", "trigger", "cause", "notes", "oemName", "siteName"]   # since the build of 2026-11-09 the server also leaves OEM and Site for the form

REQUEST_LINES = ["Service Request", "Customer Name: Acme Solar Corp", "Project Name: Sunrise Field", "Site Address: 100 Main Street, Austin, TX 78701", "Product: Acme 3MWh BESS",
                 "Quantity: 12", "Number of Technicians: 3", "Working Hours/Day: 8", "Working Days: 5", "Contact Maria for SOP."]
REQUEST_EXPECTED = {"customerName": "Acme Solar Corp", "siteName": "Sunrise Field", "siteLocation": "100 Main Street, Austin, TX 78701", "device": "Acme 3MWh BESS", "units": 12,
                    "sopDescription": "Contact Maria for SOP."}
PARTIAL_LINES = ["Service Request", "Customer Name: Borealis Power Inc", "Quantity: 7"]


def read(path):
    with open(path, "rb") as handle:
        return handle.read()


def build_pdf(lines):
    """A one-page PDF with one line of text per entry (no library needed)."""
    stream = "BT /F1 12 Tf 50 780 Td 14 TL " + " ".join(f"({line.replace('(', '[').replace(')', ']')}) Tj T*" for line in lines) + " ET"
    objects = ["<< /Type /Catalog /Pages 2 0 R >>", "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
               "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 842] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>",
               f"<< /Length {len(stream)} >>\nstream\n{stream}\nendstream", "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"]
    out, offsets = b"%PDF-1.4\n", []
    for number, body in enumerate(objects, 1):
        offsets.append(len(out))
        out += f"{number} 0 obj\n{body}\nendobj\n".encode()
    xref = len(out)
    out += f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode() + "".join(f"{offset:010d} 00000 n \n" for offset in offsets).encode()
    return out + f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()


def build_long_pdf(lines, pages=40, data_page=1):
    """A PDF of `pages` pages: every page has filler text and `lines` are on page number `data_page` (1 = first, `pages` = last)."""
    filler = [f"Page {number} of the long document. This paragraph is only filler text without quotation data." for number in range(1, 6)]
    first_page = 3
    kids = " ".join(f"{first_page + 2 * index} 0 R" for index in range(pages))
    objects = ["<< /Type /Catalog /Pages 2 0 R >>", f"<< /Type /Pages /Kids [{kids}] /Count {pages} >>"]
    for index in range(pages):
        page_lines = filler + (lines if index + 1 == data_page else [])
        stream = "BT /F1 12 Tf 50 780 Td 14 TL " + " ".join(f"({line.replace('(', '[').replace(')', ']')}) Tj T*" for line in page_lines) + " ET"
        objects.append(f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 842] /Contents {first_page + 2 * index + 1} 0 R /Resources << /Font << /F1 {3 + 2 * pages} 0 R >> >> >>")
        objects.append(f"<< /Length {len(stream)} >>\nstream\n{stream}\nendstream")
    objects.append("<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
    out, offsets = b"%PDF-1.4\n", []
    for number, body in enumerate(objects, 1):
        offsets.append(len(out))
        out += f"{number} 0 obj\n{body}\nendobj\n".encode()
    xref = len(out)
    out += f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode() + "".join(f"{offset:010d} 00000 n \n" for offset in offsets).encode()
    return out + f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()


PORTUGUESE_LINES = ["Pedido de Servico", "Customer Name: Solaris Energia Ltda", "Project Name: Campo Verde", "Site Address: Rua das Flores 100, Sao Paulo", "Product: Solaris 2MWh BESS",
                    "Quantity: 8", "Number of Technicians: 2", "Working Hours/Day: 8", "Working Days: 4"]


def build_docx(lines):
    import docx
    document = docx.Document()
    for line in lines:
        document.add_paragraph(line)
    buffer = io.BytesIO()
    document.save(buffer)
    return buffer.getvalue()


def build_scanned_pdf():
    """A one-page PDF that holds only a picture (no text), like a scanned page."""
    width = height = 64
    raw = bytes([(x * 4) % 256 if (x // 8 + y // 8) % 2 else 255 for y in range(height) for x in range(width) for _ in range(3)])
    content = "q 500 0 0 700 50 70 cm /Im0 Do Q"
    bodies = [b"<< /Type /Catalog /Pages 2 0 R >>", b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
              b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 842] /Contents 4 0 R /Resources << /XObject << /Im0 5 0 R >> >> >>",
              f"<< /Length {len(content)} >>\nstream\n{content}\nendstream".encode(),
              f"<< /Type /XObject /Subtype /Image /Width {width} /Height {height} /ColorSpace /DeviceRGB /BitsPerComponent 8 /Length {len(raw)} >>\nstream\n".encode() + raw + b"\nendstream"]
    out, offsets = b"%PDF-1.4\n", []
    for number, body in enumerate(bodies, 1):
        offsets.append(len(out))
        out += f"{number} 0 obj\n".encode() + body + b"\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(bodies) + 1}\n0000000000 65535 f \n".encode() + "".join(f"{offset:010d} 00000 n \n" for offset in offsets).encode()
    return out + f"trailer\n<< /Size {len(bodies) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()


def protected_docx(password="secret123"):
    """The Hithium .docx encrypted with a password (needs msoffcrypto-tool)."""
    from msoffcrypto.format.ooxml import OOXMLFile
    out = io.BytesIO()
    with open(HITHIUM_DOCX, "rb") as source:
        OOXMLFile(source).encrypt(password, out)
    return out.getvalue()


def damaged_docx():
    """Half of the bytes of the Hithium .docx: the zip is cut."""
    data = read(HITHIUM_DOCX)
    return data[:len(data) // 2]


UNRELATED_LINES = ["Lunch menu", "Soup of the day: tomato", "Dessert: cake"]


def padded_docx(target_bytes):
    """The Hithium .docx grown to EXACTLY target_bytes with an unused part inside the zip (it stays a valid, readable document)."""
    source = zipfile.ZipFile(HITHIUM_DOCX)

    def build(size):
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_STORED) as archive:
            for info in source.infolist():
                archive.writestr(info.filename, source.read(info.filename))
            archive.writestr("customXml/pad.bin", random.Random(1).randbytes(size))
        return buffer.getvalue()

    size = target_bytes - 20000
    data = build(size)
    size += target_bytes - len(data)
    data = build(size)
    assert len(data) == target_bytes, (len(data), target_bytes)
    return data


def upload(session: RoleApiSession, name, data, mime="application/octet-stream", field="file", timeout=120):
    """POST the document as the user of `session`. Returns the response as it comes."""
    return session.post_file(PATH, files={field: (name, data, mime)} if name is not None else None, timeout=timeout)


def upload_anonymous(name, data, mime="application/octet-stream"):
    import requests
    from shared.config.settings import BASE_URL
    return requests.post(BASE_URL.rstrip("/") + PATH, files={"file": (name, data, mime)}, timeout=60)


def my_quotation_ids(session):
    """The ids of every quotation of the user (in progress and historical)."""
    ids = set()
    for closed in ("false", "true"):
        page = 1
        while True:
            data = session.get("/api/quotations", page=page, pageSize=100, includeClosed=closed).json()
            ids |= {item["id"] for item in data["items"]}
            if not data["hasNextPage"]:
                break
            page += 1
    return ids
