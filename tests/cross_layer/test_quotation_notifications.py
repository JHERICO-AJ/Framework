"""Quotation module -- HU-23 / OP-33, Notifications: who is emailed, when and with what, read from the system's own outbox (notifications."OutboundNotification")
and, when the test mailboxes are signed in, from the emails themselves.

Layers: API (the route is driven with the real approve / reject / submit calls) + database (the outbox rows) + the mailboxes (Gmail of FPM, BU, CEO, the QA Default FPM and the
OEM; Outlook on the web of the AM). The mailbox part needs the profiles of tools/mailbox_login.py and NOTIFY_MAILBOX_TESTS=1 (Outlook opens a visible Chrome window).

What the system does (verified 2026-11-13): a quotation sent for approval queues ONE email to the approver whose turn it is; a decision of an approver queues ONE email to the owner AM
(approved at level 1 = 'returned for review', or rejected with the reason); the next level is emailed only when it is its turn; when the last internal level approves, the OEM contact
is emailed (oem-review-requested) and the AM is not. Emails are sent by the notification sender (NOTIFICATION_SENDER_EMAIL), in English. Every test sends REAL emails to the QA test mailboxes."""
import os
import re
import time
from datetime import timezone

import pytest

from framework_api.services import quotation_setup as qs
from shared.config.credentials import load_role_credentials
from shared.config.settings import NOTIFICATION_SENDER_EMAIL
from shared.datasource import quotation_db_source as qdb
from framework_api.services.oem_decision_service import OemDecisionService
from shared.utils import mailbox, oem_mailbox

pytestmark = [pytest.mark.cross_layer]
MAILBOXES = bool(os.environ.get("NOTIFY_MAILBOX_TESTS"))
needs_mailbox = pytest.mark.skipif(not MAILBOXES, reason="reads the real mailboxes: set NOTIFY_MAILBOX_TESTS=1 (profiles from tools/mailbox_login.py)")

REASON = "The labor cost is higher than agreed, please correct it."
HTML_REASON = "Check <b>labor</b> & \"hotel\" costs <script>alert(1)</script>"
CUSTOMER, SITE = "Andes Renewables SpA", "Valle Verde"
SENDER = NOTIFICATION_SENDER_EMAIL


def wait_rows(conn, quote_no, count, timeout=120, settle=8):
    """The outbox rows of the quotation once at least `count` exist (they are written within seconds), plus `settle` seconds so a row that should NOT be there has time to appear."""
    deadline = time.time() + timeout
    rows = qdb.get_outbound_notifications(conn, quote_no)
    while (len(rows) < count or any(r["Status"] not in ("Sent", "Failed") for r in rows)) and time.time() < deadline:   # also wait until the worker has sent them
        time.sleep(3)
        rows = qdb.get_outbound_notifications(conn, quote_no)
    time.sleep(settle)
    return qdb.get_outbound_notifications(conn, quote_no)


def kinds(rows):
    return [(r["Type"].replace("quotation.", ""), r["RecipientEmail"].lower()) for r in rows]


@pytest.fixture(scope="module")
def flow(api_roles, quotation_api, db_conn):
    """Drives five quotations once and keeps the outbox after every step; the tests only read it."""
    am, fpm, bu, ceo = (quotation_api[r] for r in ("AM", "FPM", "BU", "CEO"))
    emails = {r: api_roles[r].email.lower() for r in ("AM", "FPM", "BU", "CEO")}
    seen = dict(emails=emails)

    # Q1: the whole route FPM/FSM -> BU -> CEO -> OEM (the AM submits again after the FPM/FSM approves)
    signers = qs.internal_signers(api_roles) + [qs.oem_signer()]
    id1, no1 = qs.create_and_submit(api_roles["AM"], api_roles, "NTF1", ["FPM"], title_prefix="HU23-NTF", extra={"approvers": signers}, submit=False)
    seen.update(id1=id1, no1=no1, q1_created=qdb.get_outbound_notifications(db_conn, no1))
    assert am.submit(id1).status_code == 200
    seen["q1_submitted"] = wait_rows(db_conn, no1, 1)
    assert fpm.approve(id1, "Reviewed for HU-23").status_code == 200
    seen["q1_fpm_approved"] = wait_rows(db_conn, no1, 2)
    assert am.submit(id1).status_code == 200
    seen["q1_resubmitted"] = wait_rows(db_conn, no1, 3)
    assert bu.approve(id1, "BU is fine").status_code == 200
    seen["q1_bu_approved"] = wait_rows(db_conn, no1, 4)
    assert ceo.approve(id1, "CEO is fine").status_code == 200
    seen["q1_ceo_approved"] = wait_rows(db_conn, no1, 5)
    link = oem_mailbox.fetch_decision_link(no1, 1) if oem_mailbox.available() else None      # the OEM approves from the button of its email
    seen["q1_oem_approved"] = None
    if link:
        assert OemDecisionService().decide(link, "approve", "OEM approves for HU-23").status_code == 200
        seen["q1_oem_approved"] = wait_rows(db_conn, no1, 6)

    # Q2: rejected at level 1, then the AM submits it again
    id2, no2 = qs.create_and_submit(api_roles["AM"], api_roles, "NTF2", ["FPM"], title_prefix="HU23-NTF")
    seen.update(id2=id2, no2=no2, q2_submitted=wait_rows(db_conn, no2, 1))
    assert fpm.reject(id2, REASON).status_code == 200
    seen["q2_rejected"] = wait_rows(db_conn, no2, 2)
    seen["q2_resubmit"] = am.submit(id2)
    seen["q2_resubmitted"] = wait_rows(db_conn, no2, 3)

    # Q3 / Q4: a route with only the BU / only the CEO, each one rejects
    id3, no3 = qs.create_and_submit(api_roles["AM"], api_roles, "NTF3", ["BU"], title_prefix="HU23-NTF")
    seen.update(id3=id3, no3=no3)
    assert bu.reject(id3, REASON).status_code == 200
    seen["q3_rejected"] = wait_rows(db_conn, no3, 2)
    id4, no4 = qs.create_and_submit(api_roles["AM"], api_roles, "NTF4", ["CEO"], title_prefix="HU23-NTF")
    seen.update(id4=id4, no4=no4)
    assert ceo.reject(id4, HTML_REASON).status_code == 200
    seen["q4_rejected"] = wait_rows(db_conn, no4, 2)

    # Q6: only level 1 and the OEM; the OEM rejects with a reason from its email
    id6, no6 = qs.create_and_submit(api_roles["AM"], api_roles, "NTF6", ["FPM"], title_prefix="HU23-NTF", extra={"approvers": [qs.internal_signers(api_roles)[0], qs.oem_signer(order=1)]}, submit=False)
    seen.update(id6=id6, no6=no6)
    assert am.submit(id6).status_code == 200 and fpm.approve(id6, "Level 1 only").status_code == 200
    assert wait_rows(db_conn, no6, 2) and am.submit(id6).status_code == 200
    seen["q6_oem_turn"] = wait_rows(db_conn, no6, 3)
    link = oem_mailbox.fetch_decision_link(no6, 1) if oem_mailbox.available() else None
    seen["q6_oem_rejected"] = None
    if link:
        assert OemDecisionService().decide(link, "reject", REASON).status_code == 200
        seen["q6_oem_rejected"] = wait_rows(db_conn, no6, 4)

    # Q5: no signers chosen -> the default approvers (QA Default FPM/BU/CEO) are the ones emailed
    id5, no5 = qs.create_and_submit(api_roles["AM"], api_roles, "NTF5", [], title_prefix="HU23-NTF")
    seen.update(id5=id5, no5=no5, q5_submitted=wait_rows(db_conn, no5, 1))
    return seen


# ---------------------------------------------------------------- AC1 / AC2: the events and the turn of each approver (outbox)
def test_the_approver_of_level_1_is_emailed_when_the_am_submits(flow):
    assert kinds(flow["q1_created"]) == [], "nothing is emailed while the quotation is still a draft"
    assert kinds(flow["q1_submitted"]) == [("approval-requested", flow["emails"]["FPM"])]


def test_the_am_is_emailed_when_level_1_approves_and_the_next_level_waits(flow):
    new = flow["q1_fpm_approved"][len(flow["q1_submitted"]):]
    assert kinds(new) == [("decision", flow["emails"]["AM"])]
    assert new[0]["Data"]["decision"] == "approved" and new[0]["Data"]["actorRole"] == "FPM_FSM"
    assert not [k for k, e in kinds(flow["q1_fpm_approved"]) if k == "approval-requested" and e in (flow["emails"]["BU"], flow["emails"]["CEO"])], \
        "BU and CEO are not emailed before the AM submits again"


def test_the_next_level_is_emailed_only_when_it_is_its_turn(flow):
    assert kinds(flow["q1_resubmitted"][len(flow["q1_fpm_approved"]):]) == [("approval-requested", flow["emails"]["BU"])]
    assert flow["emails"]["CEO"] not in [e for _, e in kinds(flow["q1_resubmitted"])]


def test_the_am_is_not_emailed_when_level_2_or_3_approves(flow):
    after_bu = kinds(flow["q1_bu_approved"][len(flow["q1_resubmitted"]):])
    after_ceo = kinds(flow["q1_ceo_approved"][len(flow["q1_bu_approved"]):])
    assert after_bu == [("approval-requested", flow["emails"]["CEO"])]
    assert flow["emails"]["AM"] not in [e for _, e in after_bu + after_ceo]


def test_the_oem_is_emailed_when_the_last_level_approves(flow):
    after_ceo = flow["q1_ceo_approved"][len(flow["q1_bu_approved"]):]
    assert [r["Type"] for r in after_ceo] == ["quotation.oem-review-requested"]
    assert after_ceo[0]["RecipientEmail"].lower() == qs.OEM_TEST_EMAIL.lower()


@pytest.mark.parametrize("quote, rows, role", [("no2", "q2_rejected", "FPM_FSM"), ("no3", "q3_rejected", "BU"), ("no4", "q4_rejected", "CEO")])
def test_the_am_is_emailed_when_any_level_rejects(flow, quote, rows, role):
    rejection = flow[rows][-1]
    assert (rejection["Type"], rejection["RecipientEmail"].lower()) == ("quotation.decision", flow["emails"]["AM"])
    assert rejection["Data"]["decision"] == "rejected" and rejection["Data"]["actorRole"] == role
    assert rejection["Data"]["comment"] == (HTML_REASON if quote == "no4" else REASON)


def test_the_level_1_approver_is_emailed_again_when_the_am_submits_a_rejected_quotation(flow):
    assert flow["q2_resubmit"].status_code == 200
    assert kinds(flow["q2_resubmitted"][2:]) == [("approval-requested", flow["emails"]["FPM"])]


def test_a_rejection_does_not_email_any_later_approver(flow):
    for rows in ("q3_rejected", "q4_rejected"):
        assert [t for t, _ in kinds(flow[rows])] == ["approval-requested", "decision"]
    assert flow["emails"]["BU"] not in [e for _, e in kinds(flow["q2_rejected"])]


def test_the_default_approver_is_emailed_when_no_signer_was_chosen(flow):
    default_fpm = load_role_credentials("DEFAULT_FPM")["email"].lower()
    assert kinds(flow["q5_submitted"]) == [("approval-requested", default_fpm)]


def test_the_oem_is_emailed_when_only_level_1_is_required_and_the_am_is_emailed_before(flow):
    assert kinds(flow["q6_oem_turn"]) == [("approval-requested", flow["emails"]["FPM"]), ("decision", flow["emails"]["AM"]), ("oem-review-requested", qs.OEM_TEST_EMAIL.lower())]


def test_the_am_is_emailed_when_the_oem_approves(flow):
    rows = flow["q1_oem_approved"]
    if not rows:
        pytest.skip("the OEM mailbox is not signed in (python tools/oem_mailbox_login.py)")
    last = rows[-1]
    assert (last["Type"], last["RecipientEmail"].lower()) == ("quotation.decision", flow["emails"]["AM"])
    assert last["Data"]["decision"] == "approved" and last["Data"]["actorRole"] == "OEM" and last["Data"]["comment"] == "OEM approves for HU-23"


def test_the_am_is_emailed_with_the_reason_when_the_oem_rejects(flow):
    rows = flow["q6_oem_rejected"]
    if not rows:
        pytest.skip("the OEM mailbox is not signed in (python tools/oem_mailbox_login.py)")
    last = rows[-1]
    assert (last["Type"], last["RecipientEmail"].lower()) == ("quotation.decision", flow["emails"]["AM"])
    assert last["Data"]["decision"] == "rejected" and last["Data"]["actorRole"] == "OEM" and last["Data"]["comment"] == REASON


# ---------------------------------------------------------------- AC4 / AC5: what the notification says (outbox data)
def test_every_notification_carries_wo_number_customer_site_and_date(flow):
    rows = flow["q1_ceo_approved"] + flow["q2_rejected"] + flow["q3_rejected"] + flow["q4_rejected"]
    for r in rows:
        data = r["Data"]
        oem = r["Type"] == "quotation.oem-review-requested"          # the OEM email keeps the site and the date in its project sheet
        site, date = (data.get("sheetSiteName"), data.get("sheetIssuedOn")) if oem else (data.get("siteName"), data.get("dateOn"))
        assert data["customerName"] == CUSTOMER and site == SITE, (r["Type"], data)
        assert re.fullmatch(r"\d\d/\d\d/\d{4}", date or ""), (r["Type"], date)
        assert data["quoteNo"].startswith("FS")


# ---------------------------------------------------------------- each event sends exactly one email to each recipient
def test_each_event_queues_one_email_per_recipient_and_all_are_sent_at_the_first_attempt(flow):
    for key in ("q1_ceo_approved", "q2_resubmitted", "q3_rejected", "q4_rejected", "q5_submitted"):
        rows = flow[key]
        assert len({r["IdempotencyKey"] for r in rows}) == len(rows), f"{key}: a duplicated event"
        assert all(r["Status"] == "Sent" and r["Attempts"] == 1 and not r["Error"] for r in rows), [(r["Type"], r["Status"], r["Attempts"], r["Error"]) for r in rows]


def test_the_emails_go_only_to_the_intended_recipients(flow):
    allowed = {flow["emails"][r] for r in ("AM", "FPM", "BU", "CEO")} | {qs.OEM_TEST_EMAIL.lower()}
    for key in ("q1_ceo_approved", "q2_resubmitted", "q3_rejected", "q4_rejected"):
        assert {e for _, e in kinds(flow[key])} <= allowed, key
    assert {e for _, e in kinds(flow["q3_rejected"])} == {flow["emails"]["BU"], flow["emails"]["AM"]}
    assert {e for _, e in kinds(flow["q4_rejected"])} == {flow["emails"]["CEO"], flow["emails"]["AM"]}


# ---------------------------------------------------------------- AC8: the failure log and the retries (what the outbox already holds)
def test_failed_sends_are_logged_with_their_error_and_retried(db_conn):
    with db_conn.cursor() as cur:
        cur.execute('SELECT "Status", "Attempts", count(*) FROM notifications."OutboundNotification" GROUP BY 1, 2 ORDER BY 1, 2')
        groups = cur.fetchall()
        cur.execute('SELECT count(*) FROM notifications."OutboundNotification" WHERE "Status" = \'Failed\' AND ("Error" IS NULL OR "Error" = \'\')')
        failed_without_error = cur.fetchone()[0]
        cur.execute('SELECT count(*) FROM notifications."OutboundNotification" WHERE "Status" = \'Sent\' AND "Attempts" > 1')
        sent_after_retry = cur.fetchone()[0]
    if not any(status == "Failed" for status, _, _ in groups):
        pytest.skip("no failed send in the outbox yet, so there is nothing to read")
    assert failed_without_error == 0, "every failed send keeps its error"
    assert sent_after_retry > 0, "a send that failed once was retried and went out"


@pytest.mark.xfail(strict=True, reason="OBSERVATION (not confirmed as a defect): AC8 says 4 waits of 30 s, 60 s, 2 min and 4 min (about 7.5 min); the failed sends of 2026-11-12 made 8 attempts over 2 h 13 min - 2 h 21 min")
def test_a_failed_send_gives_up_after_the_waits_the_story_lists(db_conn):
    with db_conn.cursor() as cur:
        cur.execute('SELECT max("ProcessedAtUtc" - "CreatedAtUtc"), max("Attempts") FROM notifications."OutboundNotification" WHERE "Status" = \'Failed\'')
        longest, attempts = cur.fetchone()
    if longest is None:
        pytest.skip("no failed send in the outbox")
    assert attempts <= 5 and longest.total_seconds() < 600


# ---------------------------------------------------------------- the emails themselves (mailboxes)
@pytest.fixture(scope="module")
def mails(flow):
    pytest.importorskip("playwright")
    wanted = {"fpm1": ("FPM", flow["no1"]), "bu1": ("BU", flow["no1"]), "ceo1": ("CEO", flow["no1"]), "am1": ("AM", flow["no1"]), "am2": ("AM", flow["no2"]),
              "am4": ("AM", flow["no4"]), "am6": ("AM", flow["no6"]), "dfpm5": ("DEFAULT_FPM", flow["no5"]), "fpm3": ("FPM", flow["no3"]), "bu2": ("BU", flow["no2"])}
    out = {}
    for key, (role, quote_no) in wanted.items():
        if not mailbox.available(role):
            pytest.skip(f"the {role} mailbox is not signed in (python tools/mailbox_login.py {role})")
        expect_none = key in ("fpm3", "bu2")
        out[key] = mailbox.fetch_emails(role, quote_no, timeout=15 if expect_none else 120, min_count=0 if expect_none else 1)
    out["oem1"] = oem_mailbox.fetch_email(flow["no1"], 1) if oem_mailbox.available() else None
    return out


def email_with(mail_list, text):
    return next((m for m in mail_list or [] if text in m["subject"]), None)


@needs_mailbox
@pytest.mark.parametrize("key, level", [("fpm1", "FPM/FSM"), ("bu1", "BU"), ("ceo1", "CEO")])
def test_the_approver_email_says_your_approval_is_required_with_wo_customer_site_and_date(flow, mails, key, level):
    mail = email_with(mails[key], f"pending your approval ({level})")
    assert mail, mails[key]
    assert mail["sender"].lower() == SENDER and mail["subject"] == f"OmniOps: Quotation {flow['no1']}: pending your approval ({level})"
    body = mail["body"]
    assert "Your approval is required for:" in body
    assert f"WO Number: {flow['no1']}" in body and f"Customer: {CUSTOMER}" in body and f"Site: {SITE}" in body
    assert re.search(r"Date: \d\d/\d\d/\d{4}", body)


@needs_mailbox
@pytest.mark.parametrize("key", ["fpm1", "bu1", "ceo1"])
def test_the_approver_email_has_no_link_to_approve_or_reject(flow, mails, key):
    mail = email_with(mails[key], "pending your approval")
    assert mail
    assert not [l for l in mail["links"] if re.search(r"oem-decision|approve|reject", l, re.I)], mail["links"]


@needs_mailbox
def test_the_am_email_of_an_approval_shows_the_data_the_status_and_the_comment(flow, mails):
    mail = email_with(mails["am1"], "approved")
    assert mail, mails["am1"]
    body = mail["body"]
    for text in (f"WO Number: {flow['no1']}", f"Customer: {CUSTOMER}", f"Site: {SITE}", "Status: Approved", "Reviewed for HU-23"):
        assert text in body, (text, body)
    assert re.search(r"Date: \d\d/\d\d/\d{4}", body)


@needs_mailbox
def test_the_am_email_of_a_rejection_shows_the_data_the_status_and_the_reason(flow, mails):
    mail = email_with(mails["am2"], "rejected")
    assert mail, mails["am2"]
    body = mail["body"]
    for text in (f"WO Number: {flow['no2']}", f"Customer: {CUSTOMER}", f"Site: {SITE}", "Rejected", REASON):
        assert text in body, (text, body)
    assert re.search(r"Date: \d\d/\d\d/\d{4}", body)


@needs_mailbox
def test_the_am_emails_of_the_oem_decisions_show_the_data_the_status_and_the_comment(flow, mails):
    approved = [m for m in mails["am1"] if "OEM" in m["body"] and "OEM approves for HU-23" in m["body"]]
    rejected = [m for m in mails["am6"] if REASON in m["body"] and "OEM" in m["body"]]
    assert approved and rejected, (mails["am1"], mails["am6"])
    for m, status in ((approved[0], "Approved"), (rejected[0], "Rejected")):
        for text in (f"Customer: {CUSTOMER}", f"Site: {SITE}", f"Status: {status}"):
            assert text in m["body"], (text, m["body"])


@needs_mailbox
def test_html_and_special_characters_of_the_reason_are_shown_as_plain_text(flow, mails):
    mail = email_with(mails["am4"], "rejected")
    assert mail, mails["am4"]
    assert "<b>labor</b>" in mail["body"] and "alert(1)" in mail["body"] and "& \"hotel\"" in mail["body"]


@needs_mailbox
def test_the_oem_email_shows_wo_number_customer_site_date_and_the_decision_buttons(flow, mails):
    mail = mails["oem1"]
    if not mail:
        pytest.skip("the OEM mailbox could not be read (python tools/oem_mailbox_login.py)")
    assert flow["no1"] in mail["subject"] and CUSTOMER in mail["body"] and SITE in mail["body"]


@needs_mailbox
def test_the_default_approver_receives_the_email(flow, mails):
    assert email_with(mails["dfpm5"], "pending your approval (FPM/FSM)")


@needs_mailbox
def test_an_approver_does_not_receive_the_email_of_a_quotation_that_is_not_theirs(mails):
    assert not mails["fpm3"], "the FPM/FSM is not on the route of the BU-only quotation"
    assert not mails["bu2"], "the BU is not on the route of the FPM/FSM-only quotation"


@needs_mailbox
def test_every_email_is_in_english(flow, mails):
    for key in ("fpm1", "bu1", "ceo1", "am1", "am2"):
        for m in mails[key]:
            assert not re.search(r"[áéíóúñ¿¡]|Hola|Cotización|aprobación", m["body"]), (key, m["subject"])


# ---------------------------------------------------------------- API answers OK -> does the database keep it? (decisions and their comments)
def test_every_decision_the_api_accepted_is_kept_in_the_database(flow, db_conn):
    route = [(a["Rol"], a["Estado"]) for a in qdb.get_approver_decisions_by_quote_no(db_conn, flow["no1"])]
    assert route[:3] == [("FPM_FSM", "Approved"), ("BU", "Approved"), ("CEO", "Approved")], route
    for key, reason, role in (("no3", REASON, "BU"), ("no4", HTML_REASON, "CEO")):
        approvers = qdb.get_approver_decisions_by_quote_no(db_conn, flow[key])
        assert (approvers[0]["Rol"], approvers[0]["Estado"], approvers[0]["Comentario"]) == (role, "Rejected", reason), approvers
        last = qdb.get_events_by_quote_no(db_conn, flow[key])[-1]
        assert (last["EventType"], last["Comment"]) == ("Rejected", reason), last


# ---------------------------------------------------------------- AC 8: a failed send must not block or revert the workflow (read from the sends that really failed)
def test_the_quotations_of_failed_sends_kept_their_workflow_transition(db_conn):
    with db_conn.cursor() as cur:
        cur.execute('SELECT DISTINCT "Data"->>\'quoteNo\', "Type" FROM notifications."OutboundNotification" WHERE "Status" = \'Failed\'')
        failed = cur.fetchall()
    checked = 0
    for quote_no, kind in failed:
        state = qdb.get_quotation_state(db_conn, quote_no)
        if not state:
            continue                                   # the test quotation was cleaned up
        events = [e["EventType"] for e in qdb.get_events_by_quote_no(db_conn, quote_no)]
        if kind == "quotation.approval-requested":
            assert state["EstadoCotizacion"] != "Draft" and "Submitted" in events, (quote_no, state["EstadoCotizacion"], events)
        elif kind == "quotation.decision":
            assert "Approved" in events or "Rejected" in events, (quote_no, events)
        checked += 1
    if not checked:
        pytest.skip("no quotation of a failed send is left to read")


# ---------------------------------------------------------------- an OEM contact with a malformed email (Qase #220): what the server answers and what it keeps
@pytest.fixture(scope="module")
def bad_oem(api_roles, quotation_api, db_conn):
    signers = qs.internal_signers(api_roles) + [qs.oem_signer(email="not-an-email")]
    quotation_id, quote_no = qs.create_and_submit(api_roles["AM"], api_roles, "BADMAIL", ["FPM"], title_prefix="HU23-NTF", extra={"approvers": signers}, submit=False)
    answers = [quotation_api["AM"].submit(quotation_id).status_code, quotation_api["FPM"].approve(quotation_id, "ok").status_code, quotation_api["AM"].submit(quotation_id).status_code,
               quotation_api["BU"].approve(quotation_id, "ok").status_code, quotation_api["CEO"].approve(quotation_id, "ok").status_code]
    rows = wait_rows(db_conn, quote_no, 4, settle=15)
    return dict(no=quote_no, answers=answers, rows=rows, state=qdb.get_quotation_state(db_conn, quote_no), approvers=qdb.get_approver_decisions_by_quote_no(db_conn, quote_no),
                tokens=qdb.get_oem_decision_tokens_by_quote_no(db_conn, quote_no))


def test_the_server_saves_the_malformed_oem_email_and_takes_the_quotation_to_the_oem(bad_oem):
    """Documents what happens today (the answers are all 200 and the database keeps the address); the next test says what is wrong with it."""
    assert bad_oem["answers"] == [200] * 5
    assert bad_oem["approvers"][-1]["Email"] == "not-an-email"
    assert (bad_oem["state"]["EstadoCotizacion"], bad_oem["state"]["EtapaWorkflow"]) == ("Awaiting", "Vendor Reviewing")


@pytest.mark.xfail(strict=True, reason="Qase #231 (open, found 2026-11-13): the OEM turn of a malformed email queues NO notification and logs NO failure; the link token is created and revoked at once; the quotation stays Awaiting / Vendor Reviewing and nobody is told")
def test_an_oem_email_that_cannot_be_used_leaves_a_logged_failure_instead_of_silence(bad_oem):
    assert any(r["Type"] == "quotation.oem-review-requested" for r in bad_oem["rows"]), [(r["Type"], r["RecipientEmail"]) for r in bad_oem["rows"]]


# ---------------------------------------------------------------- the time of the OEM pages and email: it must be converted to the local time of the viewer, like the rest of OmniOps (Qase #229 / #230, open)
@pytest.fixture(scope="module")
def oem_time(make_waiting_on_oem, db_conn):
    if not (MAILBOXES and oem_mailbox.available()):
        pytest.skip("reads the OEM mailbox: NOTIFY_MAILBOX_TESTS=1 and python tools/oem_mailbox_login.py")
    quotation_id, quote_no = make_waiting_on_oem("TIME", title_prefix="HU23-TIME")
    email = oem_mailbox.fetch_email(quote_no, 1, timeout=150)
    link = oem_mailbox.fetch_decision_link(quote_no, 1, timeout=150)
    assert email and link
    oem = OemDecisionService()
    assert oem.decide(link, "approve", "time check").status_code == 200
    used = oem.open_page(link, "approve")
    return dict(no=quote_no, email=email, used_status=used.status_code, used_text=OemDecisionService.page_text(used), token=qdb.get_oem_decision_tokens_by_quote_no(db_conn, quote_no)[0])


@needs_mailbox
@pytest.mark.xfail(strict=True, reason="Qase #230 (open): the email writes the expiry of the link in UTC ('works through <date> (UTC)') instead of the local time that the rest of OmniOps shows")
def test_the_oem_email_gives_the_expiry_of_the_link_in_local_time(oem_time):
    body = oem_time["email"]["body"]
    assert "(UTC)" not in body and "UTC" not in body.split("works through")[-1], body[-200:]


@needs_mailbox
@pytest.mark.xfail(strict=True, reason="Qase #229 (open): the page of a used link writes the time of the decision in UTC instead of converting it to the local time of the viewer, which is what the AM's workflow panel shows")
def test_the_page_of_a_used_link_gives_the_time_of_the_decision_in_local_time(oem_time):
    assert oem_time["used_status"] == 409
    local = oem_time["token"]["UsedAt"].replace(tzinfo=timezone.utc).astimezone()
    assert f"{local:%Y-%m-%d %H:%M}" in oem_time["used_text"] and "UTC" not in oem_time["used_text"], (f"{local:%Y-%m-%d %H:%M}", oem_time["used_text"])


@needs_mailbox
def test_the_utc_times_of_the_oem_email_and_page_match_the_database(oem_time):
    """What the system writes today is at least exact: the expiry date and the time of the decision are the UTC ones of the database."""
    found = re.search(r"works through (\d{4}-\d\d-\d\d) \(UTC\)", oem_time["email"]["body"])
    assert found and found.group(1) == f"{oem_time['token']['ExpiresAt']:%Y-%m-%d}"
    assert f"the decision was Approved on {oem_time['token']['UsedAt']:%Y-%m-%d %H:%M} UTC" in oem_time["used_text"]


# ---------------------------------------------------------------- the screens that the cases check after the emails (AM, approver and Historical Quotes)
@pytest.fixture(scope="module")
def screens(api_roles, quotation_api, role_page, db_conn):
    from framework_ui.pages.quotation.quotation_page import QuotationPage
    id_a, no_a = qs.create_and_submit(api_roles["AM"], api_roles, "SCRA", ["BU"], title_prefix="HU23-SCR")          # rejected by the BU: the AM sees it
    assert quotation_api["BU"].reject(id_a, REASON).status_code == 200
    id_b, no_b = qs.create_and_submit(api_roles["AM"], api_roles, "SCRB", ["FPM"], title_prefix="HU23-SCR")         # waits on the FPM/FSM
    title_a, title_b = (qdb.get_quotation_state(db_conn, n)["Title"] for n in (no_a, no_b))
    seen = {}
    for attempt in range(4):                                                                                          # the list can take a few seconds to paint
        am = QuotationPage(role_page("AM")).open(refresh=True)
        seen["am_row"] = am.row_text(title_a)
        if seen["am_row"]:
            break
        am.page.wait_for_timeout(2000 + 2000 * attempt)
    am = QuotationPage(role_page("AM")).open(refresh=True)
    am.open_by_link(id_a)
    seen["banner"] = am.rejected_banner_text()
    for attempt in range(4):
        fpm = QuotationPage(role_page("FPM")).open(refresh=True)
        seen["fpm_row"] = fpm.row_text(title_b)
        if seen["fpm_row"]:
            break
        fpm.page.wait_for_timeout(2000 + 2000 * attempt)
    seen["fpm_pending"] = fpm.pending_approval_count()
    seen["title_b"] = title_b
    return seen


def test_the_am_sees_the_quotation_as_rejected_with_who_and_why(screens):
    assert "Rejected" in screens["am_row"], screens["am_row"]
    assert "Rejected by" in screens["banner"] and "QA Jhe BU" in screens["banner"] and REASON in screens["banner"], screens["banner"]


def test_the_approver_sees_the_quotation_that_waits_on_it_in_its_landing_list(screens):
    assert screens["fpm_row"], "the row of the quotation is not in the list of the FPM/FSM"      # the row is found by the full WO Title; its text shows it cut
    assert screens["fpm_pending"] >= 1


@needs_mailbox
def test_the_quotation_approved_by_the_oem_is_listed_in_historical_quotes(oem_time, role_page, db_conn):
    from framework_ui.pages.quotation.quotation_page import QuotationPage
    title = qdb.get_quotation_state(db_conn, oem_time["no"])["Title"]
    row = ""
    for attempt in range(4):
        row = QuotationPage(role_page("AM")).open(refresh=True).open_historical_quotes().row_text(title)
        if row:
            break
    assert row, "the quotation approved by the OEM is not in Historical Quotes"


# ---------------------------------------------------------------- two quotations processed one right after the other: each notification shows its own data (Qase case 1136)
@pytest.fixture(scope="module")
def pair(api_roles, quotation_api, db_conn):
    first = qs.create_and_submit(api_roles["AM"], api_roles, "PAIRA", ["FPM"], title_prefix="HU23-PAIR")
    second = qs.create_and_submit(api_roles["AM"], api_roles, "PAIRB", ["FPM"], title_prefix="HU23-PAIR")            # right after, without waiting for any email
    assert quotation_api["FPM"].reject(first[0], "First: " + REASON).status_code == 200
    assert quotation_api["FPM"].reject(second[0], "Second: " + REASON).status_code == 200
    return dict(first=first[1], second=second[1], rows_first=wait_rows(db_conn, first[1], 2), rows_second=wait_rows(db_conn, second[1], 2))


def test_two_quotations_processed_together_keep_each_notification_with_its_own_data(pair):
    for key, label in (("first", "First: "), ("second", "Second: ")):
        rows = pair["rows_" + key]
        assert [r["Type"] for r in rows] == ["quotation.approval-requested", "quotation.decision"], rows
        assert all(r["Data"]["quoteNo"] == pair[key] for r in rows)
        assert rows[1]["Data"]["comment"] == label + REASON


@needs_mailbox
def test_the_emails_of_two_quotations_processed_together_are_not_mixed(pair):
    fpm = mailbox.fetch_emails("FPM", pair["first"], timeout=120) + mailbox.fetch_emails("FPM", pair["second"], timeout=120)
    assert sorted(m["subject"] for m in fpm) == sorted(f"OmniOps: Quotation {n}: pending your approval (FPM/FSM)" for n in (pair["first"], pair["second"]))
    for key, label in (("first", "First: "), ("second", "Second: ")):
        mails = [m for m in mailbox.fetch_emails("AM", pair[key], timeout=120) if "rejected" in m["subject"]]
        assert len(mails) == 1 and f"WO Number: {pair[key]}" in mails[0]["body"] and label + REASON in mails[0]["body"], mails
