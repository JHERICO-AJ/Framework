"""Quotation module -- the decision of the external OEM from the link of its email, API + database + the AM's screen (OP-32 / HU-21 and OP-31 / HU-22; Qase cases OEM2-OEM8 and OEMB1).

SEMI-AUTOMATIC. The framework does everything except one step: the decision link exists only in the email (the database keeps its hash) and Google does not let it read the QA test
mailbox, so a person copies the link. One run sends ONE real email to the test mailbox (framework_api.services.quotation_setup.OEM_TEST_EMAIL) and asks for TWO links:
  1. the link of the first email -> the OEM rejects (first without a reason, then with one) and the same link is tried again;
  2. the link of the second email, sent after the AM submits again -> the OEM approves.
Run it alone, in a terminal:  OEM_EMAIL_TESTS=1 python -m pytest tests/cross_layer/test_quotation_oem_decision.py -q
(or set OEM_LINK_1 and OEM_LINK_2 in the environment when the links are already at hand). See the internal QA note 'OEM_Guia_de_pruebas'.

What the system does (verified 2026-10-26): the page of the link only shows a form; a rejection needs a reason; a used link answers 409; a rejection leaves the quotation OemRejected / Quoting
with the internal approvals kept; the AM's new submit goes straight back to the OEM with a NEW link; an approval leaves it Approved / Ready for Client, listed under 'Historical Quotes'.
Never put a link in a message or a log: it decides for the OEM."""
import os
from datetime import datetime, timezone

import pytest

from framework_api.services import quotation_setup as qs
from framework_api.services.oem_decision_service import OemDecisionService
from framework_ui.pages.quotation import quotation_locators as loc
from framework_ui.pages.quotation.quotation_page import QuotationPage
from shared.config.settings import NOTIFICATION_SENDER_EMAIL
from shared.datasource import quotation_db_source as qdb
from shared.utils import oem_mailbox

pytestmark = [pytest.mark.cross_layer, pytest.mark.oem_email,
              pytest.mark.skipif(not os.environ.get("OEM_EMAIL_TESTS"), reason="semi-automatic: sends one email to the OEM test mailbox and asks for two links; set OEM_EMAIL_TESTS=1")]

REASON = "Price is above the approved budget"
REASON_REQUIRED = "A reason is required to reject this quotation."
INTERNAL_LEVELS = [("FPM_FSM", "Approved"), ("BU", "Approved"), ("CEO", "Approved")]


def db_snapshot(db_conn, quote_no):
    return dict(state=qdb.get_quotation_state(db_conn, quote_no), approvers=qdb.get_approver_decisions_by_quote_no(db_conn, quote_no),
                tokens=qdb.get_oem_decision_tokens_by_quote_no(db_conn, quote_no), events=qdb.get_events_by_quote_no(db_conn, quote_no))


def route_of(snapshot):
    return [(a["Rol"], a["Estado"]) for a in snapshot["approvers"]]


def stage_of(snapshot):
    return snapshot["state"]["EstadoCotizacion"], snapshot["state"]["EtapaWorkflow"]


@pytest.fixture(scope="module")
def flow(api_roles, quotation_api, db_conn, role_page, make_waiting_on_oem, ask_oem_link):
    """Runs the whole path once and keeps what was seen at each step; the tests only assert on it."""
    oem = OemDecisionService()
    quotation_id, quote_no = make_waiting_on_oem("FLOW", title_prefix="HU21-OEM")
    seen = dict(id=quotation_id, quote_no=quote_no, waiting=db_snapshot(db_conn, quote_no))
    title = seen["waiting"]["state"]["Title"]

    rejection_link = ask_oem_link(f"the email of {quote_no} (the first one; the OEM rejects with it)")
    seen["email1"] = oem_mailbox.fetch_email(quote_no, 1)
    seen["page"] = oem.open_page(rejection_link, "reject")
    seen["after_open"] = db_snapshot(db_conn, quote_no)
    seen["no_reason"] = oem.decide(rejection_link, "reject", "")
    seen["after_no_reason"] = db_snapshot(db_conn, quote_no)
    seen["rejected"] = oem.decide(rejection_link, "reject", REASON)
    seen["after_reject"] = db_snapshot(db_conn, quote_no)
    seen["reused_page"] = oem.open_page(rejection_link, "reject")
    seen["reused_decision"] = oem.decide(rejection_link, "approve", "")
    seen["after_reuse"] = db_snapshot(db_conn, quote_no)

    am = QuotationPage(role_page("AM")).open(refresh=True)
    for attempt in range(4):                     # the list can take a few seconds to paint after a refresh
        seen["list_row"] = am.row_text(title)
        if seen["list_row"]:
            break
        am = QuotationPage(role_page("AM")).open(refresh=True)
        am.page.wait_for_timeout(2000 + 2000 * attempt)
    am.open_workflow_history(title)
    seen["panel"] = am.workflow_history_text()
    am = QuotationPage(role_page("AM")).open(refresh=True)
    am.open_by_link(quotation_id)
    seen["banner"] = am.rejected_banner_text()
    seen["can_submit"] = am.page.get_by_role("button", name=loc.SUBMIT_QUOTATION_BUTTON_TEXT).count() > 0

    am_api = api_roles["AM"]                      # the AM raises the Hotel Cost 1,050 -> 1,150 before submitting again: the total goes 8,410 -> 8,510
    body = am_api.session.get(f"{am_api.base_url}/api/quotations/{quotation_id}", timeout=60).json()
    body["arrangement"]["hotelCost"] = 1150
    seen["edit"] = am_api.session.put(f"{am_api.base_url}/api/quotations/{quotation_id}", json=body, timeout=60)
    seen["resubmit"] = quotation_api["AM"].submit(quotation_id)
    seen["after_resubmit"] = db_snapshot(db_conn, quote_no)

    seen["email2"] = oem_mailbox.fetch_email(quote_no, 2)
    approval_link = ask_oem_link(f"the NEW email of {quote_no} (the second one, sent after the new submit; the OEM approves with it)")
    seen["approved"] = oem.decide(approval_link, "approve", "")
    seen["after_approve"] = db_snapshot(db_conn, quote_no)
    seen["old_link_after_approval"] = oem.decide(rejection_link, "approve", "")
    seen["historical_row"] = QuotationPage(role_page("AM")).open(refresh=True).open_historical_quotes().row_text(title)
    return seen


def test_opening_the_link_only_shows_the_decision_form(flow):
    """Qase OEM2 -- the page of the link shows the form and records nothing."""
    text = OemDecisionService.page_text(flow["page"])
    assert flow["page"].status_code == 200 and "Review the quotation and record your decision." in text, f"{flow['page'].status_code} {text[:200]}"
    assert "This link works once" in text
    assert [t["UsedAt"] for t in flow["after_open"]["tokens"]] == [None] and stage_of(flow["after_open"]) == ("Awaiting", "Vendor Reviewing")


def test_a_rejection_without_a_reason_is_refused_and_the_link_is_not_used(flow):
    """Qase OEM4 -- the page asks for a reason, nothing is recorded and the link is still usable."""
    text = OemDecisionService.page_text(flow["no_reason"])
    assert REASON_REQUIRED in text, f"{flow['no_reason'].status_code} {text[:200]}"
    assert [t["UsedAt"] for t in flow["after_no_reason"]["tokens"]] == [None] and stage_of(flow["after_no_reason"]) == ("Awaiting", "Vendor Reviewing")


def test_a_rejection_with_a_reason_goes_back_to_the_am_and_keeps_the_internal_approvals(flow):
    """Qase OEM5 -- OemRejected / Quoting, the OEM is Rejected with its reason, FPM/FSM, BU and CEO stay Approved, the history has the event and the link is used once."""
    text = OemDecisionService.page_text(flow["rejected"]).replace(" .", ".")
    assert flow["rejected"].status_code == 200 and f"Your decision on quotation {flow['quote_no']} was recorded: Rejected." in text, f"{flow['rejected'].status_code} {text[:200]}"
    after = flow["after_reject"]
    assert stage_of(after) == ("OemRejected", "Quoting")
    assert route_of(after) == INTERNAL_LEVELS + [("OEM", "Rejected")]
    assert after["approvers"][-1]["Comentario"] == REASON
    last = after["events"][-1]
    assert (last["EventType"], last["ActorRole"], last["Comment"], last["StatusAfter"]) == ("Rejected", "OEM", REASON, "OemRejected"), last
    assert [(t["Decision"], t["UsedAt"] is not None, t["RevokedAt"]) for t in after["tokens"]] == [("Rejected", True, None)]


def test_a_used_link_cannot_decide_again(flow):
    """Qase OEM6 -- opening the link and sending a decision with it both answer 409 and nothing changes."""
    assert (flow["reused_page"].status_code, flow["reused_decision"].status_code) == (409, 409)
    assert stage_of(flow["after_reuse"]) == ("OemRejected", "Quoting") and flow["after_reuse"]["tokens"] == flow["after_reject"]["tokens"]


def test_the_am_sees_the_rejection_by_the_oem(flow):
    """Qase OEMB1 and OEM5 -- the list says 'Rejected by OEM' and the quotation shows the banner with the OEM and its reason, and can be submitted again."""
    assert "Rejected by OEM" in flow["list_row"], flow["list_row"]
    assert "Rejected by" in flow["banner"] and qs.OEM_TEST_NAME in flow["banner"] and REASON in flow["banner"], flow["banner"]
    assert flow["can_submit"], "the AM has no 'Submit Quotation' button on a quotation rejected by the OEM"


def test_the_new_submit_goes_straight_to_the_oem_with_a_new_link(flow):
    """Qase OEM7 and OEM8 -- Awaiting / Vendor Reviewing, the internal approvals kept, the OEM pending again and a second link while the first stays used."""
    assert flow["resubmit"].status_code == 200, flow["resubmit"].status_code
    after = flow["after_resubmit"]
    assert stage_of(after) == ("Awaiting", "Vendor Reviewing")
    assert route_of(after) == INTERNAL_LEVELS + [("OEM", "Pending")]
    assert [(t["Decision"], t["UsedAt"] is not None) for t in after["tokens"]] == [("Rejected", True), (None, False)]


def test_the_oem_approval_after_the_new_submit(flow):
    """Qase OEM3 and OEM8 -- Approved / Ready for Client with no comment, the second link used, the first one still refused, and the quotation under 'Historical Quotes'."""
    text = OemDecisionService.page_text(flow["approved"]).replace(" .", ".")
    assert flow["approved"].status_code == 200 and f"Your decision on quotation {flow['quote_no']} was recorded: Approved." in text, f"{flow['approved'].status_code} {text[:200]}"
    after = flow["after_approve"]
    assert stage_of(after) == ("Approved", "Ready for Client")
    assert route_of(after) == INTERNAL_LEVELS + [("OEM", "Approved")] and after["approvers"][-1]["Comentario"] is None
    assert [(t["Decision"], t["UsedAt"] is not None) for t in after["tokens"]] == [("Rejected", True), ("Approved", True)]
    assert flow["old_link_after_approval"].status_code == 409
    assert "Ready for Client" in flow["historical_row"] and "Approved" in flow["historical_row"], flow["historical_row"]


def test_the_first_email_has_the_quotation_data_and_the_decision_buttons(flow):
    """Qase OEM1 -- sender, subject, greeting, the quotation data, the amounts and the Approve and Reject buttons, and the one-use link note."""
    if not flow["email1"]:
        pytest.skip("the test mailbox could not be read (run tools/oem_mailbox_login.py once)")
    e = flow["email1"]
    assert e["sender"].lower() == NOTIFICATION_SENDER_EMAIL and e["subject"] == f"OmniOps: Quotation {flow['quote_no']}: awaiting your review", e
    body = e["body"]
    for text in (f"Hi {qs.OEM_TEST_NAME}", f"Quotation {flow['quote_no']} has passed all internal approvals", "Account Manager: Jherico Ascencio", f"Quotation #: {flow['quote_no']}",
                 "$1,600.00", "$3,130.00", "$3,680.00", "TOTAL AMOUNT	$8,410.00", "Approve", "Reject", "The link can be used once and works through"):
        assert text in body, (text, body[:600])


def test_the_workflow_panel_of_a_quotation_rejected_by_the_oem(flow):
    """Qase OEM11 -- status 'Rejected by OEM', phase 'WO Quoting', waiting on the AM, and the OEM Review step with the reason."""
    panel = flow["panel"]
    for text in ("Rejected by OEM", "WO Quoting", "Jherico Ascencio", "OEM Review", "QA Test OEM", "Rejected", REASON):
        assert text in panel, (text, panel[:500])


def test_the_second_email_shows_the_new_amount(flow):
    """Qase OEM9 -- the AM changes the amount (Hotel Cost 1,050 -> 1,150), submits again and the email shows $8,510; the internal approvals are kept and the final total is 8,510."""
    assert flow["edit"].status_code == 200, flow["edit"].text[:200]
    if not flow["email2"]:
        pytest.skip("the test mailbox could not be read (run tools/oem_mailbox_login.py once)")
    assert "TOTAL AMOUNT	$8,510.00" in flow["email2"]["body"] and "$8,410.00" not in flow["email2"]["body"], flow["email2"]["body"][:900]
    assert flow["email2"]["subject"] == flow["email1"]["subject"] if flow["email1"] else True
    assert float(flow["after_approve"]["state"]["MontoTotal"]) == 8510.0 and route_of(flow["after_approve"])[:3] == INTERNAL_LEVELS, flow["after_approve"]["state"]


def _stamp(ts, local):
    """'YYYY-MM-DD HH:MM' of a database time (UTC), in the zone of this computer (the browser's zone) or in UTC."""
    dt = ts if isinstance(ts, datetime) else datetime.fromisoformat(str(ts))
    dt = dt.replace(tzinfo=timezone.utc)
    return (dt.astimezone() if local else dt).strftime("%Y-%m-%d %H:%M")


def test_the_screens_show_the_local_time_and_the_oem_pages_say_utc(flow):
    """(Its Qase case HU21-T1 was deleted on 2026-11-11 and the test is kept for another story.) The database keeps UTC: the Quotation Workflow panel and the banner of the AM show the local time of the user; the page of a used link and the email of the OEM say 'UTC'."""
    rejected = next(e for e in flow["after_reject"]["events"] if e["EventType"] == "Rejected")["OccurredAt"]
    assert _stamp(rejected, local=True) in flow["panel"], (_stamp(rejected, True), flow["panel"][-400:])
    assert _stamp(rejected, local=True) in flow["banner"], (_stamp(rejected, True), flow["banner"])
    used_page = OemDecisionService.page_text(flow["reused_page"])
    assert f"{_stamp(rejected, local=False)} UTC" in used_page, (_stamp(rejected, False), used_page)
    if flow["email1"]:
        assert "works through" in flow["email1"]["body"] and "(UTC)" in flow["email1"]["body"], flow["email1"]["body"][-300:]
