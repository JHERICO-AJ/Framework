"""Support of the HU-02 (OP-18) ingestion tests: sends real emails from the AM's Outlook (a VISIBLE Chrome window, profile .mailbox_profile_AM), moves them to the folder 'Quotation' together and reads the drafts that
OmniOps creates (database, read only, and the API as the AM). Every email has a subject 'HU02R-<stamp>-<key>' and, unless the test says otherwise, the same WO Title. The stamp and the drafts are saved in
reports/hu02/ingest_state.json so the screen tests (tests/ui/quotation/test_email_ingestion_ui.py) can open the same drafts."""
import datetime as dt
import json
import os
import time

import docx
from docx.oxml.ns import qn

from shared.utils.outlook_ingest import OutlookSession

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
STATE = os.path.join(ROOT, "reports", "hu02", "ingest_state.json")
os.environ.setdefault("OUTLOOK_SHOTS", os.path.join(ROOT, "reports", "hu02"))


def new_stamp():
    return dt.datetime.now().strftime("%H%M%S")


def load_state():
    return json.load(open(STATE, encoding="utf-8")) if os.path.exists(STATE) else {}


def save_state(group, data):
    state = load_state()
    state[group] = data
    os.makedirs(os.path.dirname(STATE), exist_ok=True)
    json.dump(state, open(STATE, "w", encoding="utf-8"), indent=1, ensure_ascii=False, default=str)


def drafts_like(conn, like):
    """{CorreoAsunto: (Id, QuoteNo, FechaCreacion)} of the email drafts whose subject matches the LIKE pattern."""
    with conn.cursor() as cur:
        cur.execute('SELECT "CorreoAsunto","Id","QuoteNo","FechaCreacion" FROM quotation."Quotation" WHERE "Origen"=\'CORREO\' AND "CorreoAsunto" LIKE %s', (like,))
        rows = {r[0]: (r[1], r[2], r[3]) for r in cur.fetchall()}
    conn.rollback()
    return rows


def wait_drafts(conn, like, expected, timeout=300, settle=15):
    """Waits until `expected` drafts exist (or the timeout), then `settle` seconds more so a draft that should NOT be there has time to show up."""
    end = time.time() + timeout
    rows = drafts_like(conn, like)
    while len(rows) < expected and time.time() < end:
        time.sleep(5)
        rows = drafts_like(conn, like)
    time.sleep(settle)
    return drafts_like(conn, like)


def detail(api, quotation_id):
    r = api.get(f"/api/quotations/{quotation_id}")
    assert r.status_code == 200, f"GET /api/quotations/{quotation_id} -> {r.status_code}"
    return r.json()


def run_batch(group, stamp, emails, conn, api, expected_drafts=None, wait=300, folder_moves=None):
    """emails: [(key, subject, body, attachment_path or None)]. Sends all, moves them TOGETHER to 'Quotation' (except the keys in folder_moves = {key: folder}), waits and returns
    {key: {subject, id, quote_no, seconds (after the move), detail}} (drafts that do not exist have id None)."""
    prefix = f"HU02R-{stamp}-"
    folder_moves = folder_moves or {}
    with OutlookSession() as o:
        for key, subject, body, attach in emails:
            o.send_to_self(subject, body, attach=attach)
        together = [e for e in emails if e[0] not in folder_moves]
        for key, folder in folder_moves.items():
            subject = next(e[1] for e in emails if e[0] == key)
            assert o.move_to(subject, folder), f"could not move {subject} to {folder}"
        moved = o.move_many(prefix, len(together) + len(folder_moves)) if not folder_moves else o.move_many(prefix, len(together))
    assert moved, "the emails were not found in the Inbox to move them"
    expected = expected_drafts if expected_drafts is not None else len(emails)
    rows = wait_drafts(conn, f"%{prefix}%", expected, timeout=wait)
    result = {}
    for key, subject, body, attach in emails:
        row = next((v for s, v in rows.items() if s.endswith(subject) or subject.endswith(s) or s == subject or s.replace("FW: ", "") == subject.replace("FW: ", "")), None)
        item = {"subject": subject, "id": None, "quote_no": None, "seconds": None, "detail": None}
        if row:
            item.update(id=row[0], quote_no=row[1], seconds=(row[2] - moved).total_seconds(), detail=detail(api, row[0]))
        result[key] = item
    save_state(group, {"stamp": stamp, "moved_utc": moved.isoformat(), "items": {k: {x: v[x] for x in ("subject", "id", "quote_no", "seconds")} for k, v in result.items()}})
    return result


def docx_text(path):
    """The text of a Word document as the body of an email: paragraphs, then the rows of the tables as 'cell | cell | cell'."""
    d, lines = docx.Document(path), []
    for el in d.element.body:
        if el.tag == qn("w:p"):
            t = "".join(x.text or "" for x in el.iter(qn("w:t"))).strip()
            if t:
                lines.append(t)
        elif el.tag == qn("w:tbl"):
            for row in docx.table.Table(el, d).rows:
                lines.append(" | ".join(c.text.replace(chr(10), " ").strip() for c in row.cells))
    return chr(10).join(lines)


EVE_CHANGES = [("Hithium Energy Storage - Global Service - Americas", "EVE Energy North America - Technical Service"), ("Tidwell I", "Silverleaf"),
               ("11174 North Tidwell Prairie Rd, Bremond, TX 76629", "4200 E Brooks Ave, North Las Vegas, Nevada 89115"), ("Hithium 5.016MWh BESS", "EVE 5.0MWh BESS"), ("Quantity: 96", "Quantity: 48"),
               ("Date Requested: 5/4/2026", "Dates: May 18, 2026 - June 5, 2026"), ("Number of Technicians: 4", "Number of Technicians: 2"), ("15 working days * 10 hours * 4 techs", "20 working days * 10 hours * 2 techs"),
               ("Number of Technicians | 4", "Number of Technicians | 2"), ("Working Days | 15", "Working Days | 20"), ("Total Man-Hours | 600", "Total Man-Hours | 400"),
               ("Labor Hourly Rate ($/Hour) | ", "Labor Hourly Rate ($/Hour) | $90.00"), ("Over-Time Hourly Rate ($/Hour) | ", "Over-Time Hourly Rate ($/Hour) | $135.00"),
               ("Airfare ($) | ", "Airfare ($) | 2 round trips x $410.00"), ("Hotel ($) | ", "Hotel ($) | 2 rooms x 20 nights x $150.00"), ("Car Rental ($) | ", "Car Rental ($) | 1 vehicle x 20 days x $78.00"),
               ("Per Diem ($) | ", "Per Diem ($) | 2 techs x 20 days x $72.00")]


def eve_body(rfp_path):
    """The format attached to the story (the Hithium RFP document) with the values of Qase defect #155 (EVE Energy North America / Silverleaf)."""
    text = docx_text(rfp_path)
    for a, b in EVE_CHANGES:
        assert a in text, f"not found in the RFP text: {a}"
        text = text.replace(a, b)
    return text


def run_sequential(group, stamp, emails, conn, api, wait=240):
    """One email at a time: send, move, wait for its draft, next one. Same result format as run_batch."""
    result, moved_times = {}, {}
    with OutlookSession() as o:
        for key, subject, body, attach in emails:
            o.send_to_self(subject, body, attach=attach)
            moved = o.move_many(subject, 1)
            assert moved, f"the email {subject} was not found in the Inbox to move it"
            rows = wait_drafts(conn, f"%{subject}", 1, timeout=wait, settle=5)
            row = next(iter(rows.values()), None)
            item = {"subject": subject, "id": None, "quote_no": None, "seconds": None, "detail": None}
            if row:
                item.update(id=row[0], quote_no=row[1], seconds=(row[2] - moved).total_seconds(), detail=detail(api, row[0]))
            result[key] = item
    save_state(group, {"stamp": stamp, "items": {k: {x: v[x] for x in ("subject", "id", "quote_no", "seconds")} for k, v in result.items()}})
    return result
