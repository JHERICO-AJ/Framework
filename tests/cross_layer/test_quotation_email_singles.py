"""Quotation module -- HU-02 / OP-18 (and HU-03 / OP-15 criterion 4): the cases that need ONE email each and Outlook actions (move out and back, delete, a folder with another name, an attachment).
Same rules as tests/cross_layer/test_quotation_email_ingestion.py (real emails, visible Chrome window, EMAIL_INGEST_TESTS=1). Classes: TestSingles1 (1069, 1026, 1055), TestSingles2 (1023, 1435, 1054, HU-03 AC 4).
Deviations from the case texts, written in the result comment of the run: 1023 uses the existing folder 'OmniOps' as the folder with another name (the case says 'Quotations'); 1055 deletes the email to
'Deleted items' (the case also empties that folder); the unread mark of 1026 is pressed with Ctrl+U and the screenshot reports/hu02/outlook_mark_unread.png shows it."""
import os
import tempfile
import time

import pytest

from framework_api.client.role_session import RoleApiSession
from shared.config.credentials import load_role_credentials
from shared.utils.outlook_ingest import OutlookSession
from tests.cross_layer import hu02_emails as E
from tests.cross_layer import hu02_support as S

pytestmark = [pytest.mark.cross_layer,
              pytest.mark.skipif(not os.environ.get("EMAIL_INGEST_TESTS"), reason="sends real emails from the AM's Outlook (visible Chrome window): set EMAIL_INGEST_TESTS=1")]
RFP = os.path.join(S.ROOT, "docs", "Quotation", "Hithium Service RFP_Raven Cold Cx 1.docx")
ONE_MINUTE = 65


@pytest.fixture(scope="module")
def am_api():
    creds = load_role_credentials("AM")
    if creds is None:
        pytest.skip("QUOTATION_AM_EMAIL / QUOTATION_AM_PASSWORD not set in .env")
    return RoleApiSession(creds["email"], creds["password"])


@pytest.fixture(scope="module")
def stamp():
    return S.new_stamp()


def body_of(subject):
    return E.render(subject, fields=E.replaced({"WO Title": "{title}"}))


def send_and_move(o, subject, body=None, attach=None):
    o.send_to_self(subject, body if body is not None else body_of(subject), attach=attach)
    moved = o.move_many(subject, 1)
    assert moved, f"the email {subject} was not found in the Inbox to move it"
    return moved


@pytest.fixture(scope="module")
def singles1(stamp, db_conn, am_api):
    out = {}
    with OutlookSession() as o:
        # 1069: one email alone
        sub = f"HU02R-{stamp}-single"
        moved = send_and_move(o, sub)
        rows = S.wait_drafts(db_conn, f"%{sub}", 1, timeout=120, settle=0)
        row = next(iter(rows.values()), None)
        out["single"] = {"subject": sub, "id": row and row[0], "seconds": row and (row[2] - moved).total_seconds()}
        # 1026: moved out of 'Quotation' and back in, and marked unread
        sub = f"HU02R-{stamp}-outback"
        send_and_move(o, sub)
        rows = S.wait_drafts(db_conn, f"%{sub}", 1, timeout=120, settle=0)
        first = next(iter(rows.values()), None)
        assert o.move_to(sub, "Bandeja de entrada")
        time.sleep(45)
        assert o.move_to(sub, "Quotation")
        o.mark_unread(sub)
        time.sleep(150)
        after = S.drafts_like(db_conn, f"%{sub}")
        out["outback"] = {"subject": sub, "first": first and first[1], "after": sorted(v[1] for v in after.values())}
        # 1055: the email is deleted from Outlook
        sub = f"HU02R-{stamp}-delete"
        send_and_move(o, sub)
        rows = S.wait_drafts(db_conn, f"%{sub}", 1, timeout=120, settle=0)
        row = next(iter(rows.values()), None)
        before = S.detail(am_api, row[0]) if row else None
        assert o.delete(sub)
        time.sleep(45)
        out["delete"] = {"subject": sub, "id": row and row[0], "before": before, "after": S.detail(am_api, row[0]) if row else None}
    S.save_state("singles1", {"stamp": stamp, "single": {k: out["single"][k] for k in ("subject", "id", "seconds")}})
    return out


class TestSingles1:
    def test_c1069_one_email_alone_gets_its_draft_within_one_minute(self, singles1):
        item = singles1["single"]
        assert item["id"], "no draft was created"
        assert item["seconds"] <= ONE_MINUTE, f"AC 9: the draft took {item['seconds']:.0f} s after the move"

    def test_c1026_an_email_moved_out_and_back_does_not_create_a_second_draft(self, singles1):
        item = singles1["outback"]
        assert item["first"], "the first draft was not created"
        assert item["after"] == [item["first"]], f"after moving the email out and back the drafts are {item['after']}"

    def test_c1055_the_draft_keeps_its_data_after_the_email_is_deleted(self, singles1):
        item = singles1["delete"]
        assert item["id"] and item["before"] == item["after"], "the draft changed after the email was deleted"


@pytest.fixture(scope="module")
def singles2(stamp, db_conn, am_api):
    out = {}
    damaged = os.path.join(tempfile.gettempdir(), "damaged.docx")
    with open(damaged, "w", encoding="utf-8") as f:
        f.write("this is not a Word document")
    with OutlookSession() as o:
        # 1023: an email that stays in the Inbox, one in a folder with another name, and a control in 'Quotation'
        sub_a, sub_b, sub_c = f"HU02N-{stamp}-A inbox", f"HU02R-{stamp}-B otherfolder", f"HU02R-{stamp}-C control"
        for s in (sub_a, sub_b, sub_c):
            o.send_to_self(s, body_of(s))
        assert o.move_to(sub_b, "OmniOps")
        assert o.move_many(sub_c, 1)
        # 1054: format plus attachment
        sub_att = f"HU02R-{stamp}-attach"
        send_and_move(o, sub_att, attach=RFP)
        # 1435: one email with values longer than the limit of the fields
        sub_big = f"HU02R-{stamp}-big"
        send_and_move(o, sub_big, body=E.render(sub_big, fields=E.replaced({"WO Title": "{title}", "Site Location": "L" * 600, "Unit Info": "U" * 600, "Device": "D" * 400, "Signal": "S" * 1200})))
        # 1052: the same email as an email with formatting (the default of Outlook on the web) and as a plain-text email
        sub_html, sub_plain = f"HU02R-{stamp}-html", f"HU02R-{stamp}-plain"
        send_and_move(o, sub_html)
        o.send_to_self(sub_plain, body_of(sub_plain), plain=True)
        assert o.move_many(sub_plain, 1), "the plain-text email was not found in the Inbox"
        # HU-03 AC 4: damaged attachment and nothing in the body
        sub_dmg = f"HU02R-{stamp}-damaged"
        send_and_move(o, sub_dmg, body="Please see the attached request.", attach=damaged)
    time.sleep(10)
    rows = S.wait_drafts(db_conn, f"%{stamp}-%", 5, timeout=240, settle=150)
    out["rows"] = rows
    out["subjects"] = dict(a=sub_a, b=sub_b, c=sub_c, att=sub_att, dmg=sub_dmg, big=sub_big, html=sub_html, plain=sub_plain)
    out["html_detail"] = S.detail(am_api, rows[sub_html][0]) if sub_html in rows else None
    out["plain_detail"] = S.detail(am_api, rows[sub_plain][0]) if sub_plain in rows else None
    out["big_detail"] = S.detail(am_api, rows[sub_big][0]) if sub_big in rows else None
    out["att_detail"] = S.detail(am_api, rows[sub_att][0]) if sub_att in rows else None
    S.save_state("singles2", {"stamp": stamp, "control": rows.get(sub_c, [None, None])[1], "attach": rows.get(sub_att, [None, None])[1]})
    return out


class TestSingles2:
    def test_c1023_email_in_the_inbox_or_another_folder_creates_nothing(self, singles2):
        s, rows = singles2["subjects"], singles2["rows"]
        assert s["c"] in rows, "the control email moved to 'Quotation' did not create its draft"
        assert not [r for r in rows if r.endswith("A inbox") or r.endswith("B otherfolder")], "an email outside 'Quotation' created a draft"

    def test_c1435_values_longer_than_the_field_limit(self, singles2):
        d = singles2["big_detail"]
        assert d, "the email with the very long values created no draft"
        assert d["siteLocation"] in ("L" * 300, "L" * 299 + "…"), "Site Location is cut to 300 characters (the last one may be an ellipsis)"
        assert d["unitInfo"] == "U" * 200 and d["device"] == "D" * 200 and d["signal"] == "S" * 200 and d["customerName"] == "Andes Renewables SpA"

    def test_c1054_email_with_attachment_creates_the_draft(self, singles2):
        d = singles2["att_detail"]
        assert d, "the email with the attachment created no draft"
        assert (d["customerName"], d["siteName"], d["units"]) == ("Andes Renewables SpA", "Valle Verde", 12) and d["arrangement"]["supportEngineers"] == 2

    def test_c_new_hu03_ac4_damaged_attachment_creates_nothing(self, singles2):
        s, rows = singles2["subjects"], singles2["rows"]
        assert s["att"] in rows, "the control email of the module did not create its draft"
        assert not [r for r in rows if r.endswith("damaged")], "an email with a damaged attachment and no data created a draft"

    def test_c1052_formatted_and_plain_text_emails_give_the_same_draft(self, singles2):
        h, p = singles2["html_detail"], singles2["plain_detail"]
        assert h and p, "one of the two emails (formatted / plain text) created no draft"
        keys = ("customerName", "siteName", "typeOfWork", "units", "device", "severity", "cause", "notes")
        assert [h[k] for k in keys] == [p[k] for k in keys]
        assert {k: h["arrangement"][k] for k in ("supportEngineers", "laborCostHour", "hotelCost", "grandTotal")} == {k: p["arrangement"][k] for k in ("supportEngineers", "laborCostHour", "hotelCost", "grandTotal")}
        assert p["customerName"] == "Andes Renewables SpA" and p["units"] == 12
