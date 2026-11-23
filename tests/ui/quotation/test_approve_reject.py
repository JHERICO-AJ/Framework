"""Quotation module -- Approve or reject a quotation (OP-31 / HU-22, Qase suite "HU-22: Approve or reject a quotation",
cases #1207-#1249, milestone Release 2.0 Quotation).

Sources: the HU-22 text as updated by the developer, Quotation_Spec V13/V14 (AC-4, AC-9, AC-10.3/10.4, AC-11.x) and the
approvers-and-amounts guide. Each test cites its Qase case id.

Test accounts (one per role, .env QUOTATION_<ROLE>_*): AM submits, FPM / BU / CEO approve. Every quotation is created by
the AM with a fixed route (only the approvers named by the test) and a total under $100,000, so the amount rules add nobody.

Most tests share a few quotations through module-scoped fixtures (so the suite does not submit 40 quotations):
  * pending_*   -- submitted and left waiting; the tests that use them never decide on them;
  * the *scenario* fixtures decide once (approve or reject) and several tests then read the outcome.
Tests that mutate a scenario (E5, E6, D5) are written last for their fixture, in file order.

Confirmed against the QA build of 2026-10-20: the bar is a single-line field (maxlength 1000) + Reject + Approve; the decision is
POST /api/quotations/{id}/approve|reject {"comment": "..."}; the AM sees 'Rejected by <name> <role> <date> : <recommendation>';
a failed save shows 'Could not save this decision.' under the bar. NOT in this build: a history panel on the quotation (HU-06) and any
way to open a quotation by link (the SPA sends deep links to /login), so the 'shows in the quotation's history' and 'opens again from a
saved link' step is checked only through the lists. The history of a decision is the 'Quotation Workflow' panel that opens by clicking the status of the row.
"""
import re
import time
from collections import namedtuple

import pytest
from playwright.sync_api import expect

from framework_ui.pages.quotation.quotation_page import QuotationPage
from shared.datasource.quotation_db_source import (
    get_approver_decisions_by_quote_no, get_events_by_quote_no, get_quotation_id, get_quotation_state)
from tests.ui.quotation.support import open_as_approver, submit_for_approval

pytestmark = pytest.mark.ui

Q = namedtuple("Q", "quote title")
REC = "Reviewed and agreed, the scope and cost are correct."
PENDING_PILL = re.compile(r"Pending approval\s*\(\d+\)")


# ------------------------------------------------------------------------------------------------ helpers
def eventually(fn, timeout=20, step=1.0):
    """Polls fn() until it returns something truthy (the database is written a moment after the screen changes)."""
    end = time.time() + timeout
    value = fn()
    while not value and time.time() < end:
        time.sleep(step)
        value = fn()
    return value


def new(role_page, tag, route):
    return Q(*submit_for_approval(role_page("AM"), tag, route))


def decide(role_page, role, q, outcome, text):
    """The approver opens the quotation from Pending approval, writes the recommendation and clicks Approve/Reject; returns the
    page once the Pending approval list is shown again."""
    qp = open_as_approver(role_page, role, q.title)
    qp.decision_bar().wait_until_visible().decide(outcome, text)
    qp.page.get_by_text(PENDING_PILL).first.wait_for(timeout=25000)
    return qp


def am_page(role_page):
    return QuotationPage(role_page("AM")).open(refresh=True)


def am_open(role_page, q):
    return am_page(role_page).open_listed_quotation(q.title)


def am_row(role_page, q):
    return am_page(role_page).row_text(q.title)


def resubmit(role_page, q):
    """The AM opens the quotation (Returned / Rejected) from Quotes in Progress and submits it again."""
    qp = am_open(role_page, q)
    submit = qp.page.get_by_role("button", name="Submit Quotation", exact=True)
    submit.click(force=True)
    expect(qp.page.get_by_text("WO Snapshot", exact=True)).to_have_count(0, timeout=20000)
    return qp


def not_in_list(role_page, role, q):
    page = QuotationPage(role_page(role)).open(refresh=True).page
    page.wait_for_timeout(2500)
    return q.title not in page.locator("body").inner_text()


def in_list(role_page, role, q):
    page = QuotationPage(role_page(role)).open(refresh=True).page
    page.wait_for_timeout(2500)
    return q.title in page.locator("body").inner_text()


def last_event(db_conn, q, event_type):
    events = [e for e in get_events_by_quote_no(db_conn, q.quote) if e["EventType"] == event_type]
    return events[-1] if events else None


# ------------------------------------------------------------------------------------------------ shared quotations (never decided)
@pytest.fixture(scope="module")
def pending_fpm(role_page):
    return new(role_page, "PFPM", ["FPM"])


@pytest.fixture(scope="module")
def pending_fpm_bu(role_page):
    return new(role_page, "PFBU", ["FPM", "BU"])


@pytest.fixture(scope="module")
def pending_bu(role_page):
    return new(role_page, "PBU", ["BU"])


@pytest.fixture(scope="module")
def pending_ceo(role_page):
    return new(role_page, "PCEO", ["CEO"])


@pytest.fixture(scope="module")
def keep_1(role_page):
    return new(role_page, "KEEP1", ["FPM"])


@pytest.fixture(scope="module")
def keep_2(role_page):
    return new(role_page, "KEEP2", ["FPM"])


def clear_kept_text(qp):
    qp.decision_bar().type_recommendation("")


# ================================================================================================ A. Decision bar
def test_decision_bar_is_shown_to_the_fpm_approver_whose_turn_it_is(role_page, pending_fpm):
    """Qase #1207 -- HU-22 'Decision bar'."""
    qp = open_as_approver(role_page, "FPM", pending_fpm.title)
    bar = qp.decision_bar().wait_until_visible()
    assert bar.is_visible()
    expect(bar.recommendation()).to_have_attribute("placeholder", "Recommendation (required for Approve/Reject)")


def test_am_opening_a_quotation_waiting_for_an_approver_sees_no_decision_bar(role_page, pending_fpm):
    """Qase #1208 -- HU-22 'Decision bar': anyone else sees the quotation read-only, without the bar."""
    qp = am_open(role_page, pending_fpm)
    expect(qp.decision_bar().recommendation()).to_have_count(0)
    expect(qp.decision_bar().reject_button()).to_have_count(0)
    assert not qp.diagnosis_field("CAUSE").is_editable(), "the AM must see a quotation waiting for an approver read-only"


def test_approver_whose_turn_has_not_come_does_not_get_the_quotation_or_the_bar(role_page, db_conn, pending_fpm_bu):
    """Qase #1209 -- HU-22 'Decision bar'. The BU approver is second in the route: the quotation is not in their Pending approval list
    and, opened by its own link, it is read-only without the bar."""
    assert not_in_list(role_page, "BU", pending_fpm_bu), "the quotation must not be listed for an approver whose turn has not come"
    qp = QuotationPage(role_page("BU")).open_by_link(get_quotation_id(db_conn, pending_fpm_bu.quote))
    expect(qp.decision_bar().recommendation()).to_have_count(0)
    expect(qp.decision_bar().reject_button()).to_have_count(0)
    assert not qp.diagnosis_field("CAUSE").is_editable()


def test_decision_bar_is_shown_to_the_bu_approver_whose_turn_it_is(role_page, pending_bu):
    """Qase #1210"""
    qp = open_as_approver(role_page, "BU", pending_bu.title)
    assert qp.decision_bar().wait_until_visible().is_visible()


def test_decision_bar_is_shown_to_the_ceo_approver_whose_turn_it_is(role_page, pending_ceo):
    """Qase #1211"""
    qp = open_as_approver(role_page, "CEO", pending_ceo.title)
    assert qp.decision_bar().wait_until_visible().is_visible()


# ================================================================================================ B. Diagnosis
DIAG = {"SIGNAL": "Voltage drop on bus 2", "TRIGGER": "Alarm 4012", "CAUSE": "Loose terminal", "NOTES": "Bring torque wrench",
        "SOP / STEPS": "1. Isolate. 2. Tighten."}


def test_fpm_edits_the_diagnosis_and_the_changes_are_saved_when_approving(role_page):
    """Qase #1212 -- HU-22 'Diagnosis'."""
    q = new(role_page, "B1", ["FPM"])
    qp = open_as_approver(role_page, "FPM", q.title)
    for label, value in DIAG.items():
        qp.diagnosis_field(label).fill(value)
    qp.decision_bar().decide("approve", REC)
    qp.page.get_by_text(PENDING_PILL).first.wait_for(timeout=25000)
    am = am_open(role_page, q)
    for label, value in DIAG.items():
        assert am.diagnosis_field(label).input_value() == value, f"{label} typed by the FPM/FSM approver must be saved with the decision"


def test_fpm_diagnosis_changes_are_saved_when_rejecting(role_page):
    """Qase #1213"""
    q = new(role_page, "B2", ["FPM"])
    qp = open_as_approver(role_page, "FPM", q.title)
    qp.diagnosis_field("CAUSE").fill("Rejected: wrong cause")
    qp.decision_bar().decide("reject", "Cause is not correct.")
    qp.page.get_by_text(PENDING_PILL).first.wait_for(timeout=25000)
    assert am_open(role_page, q).diagnosis_field("CAUSE").input_value() == "Rejected: wrong cause"


@pytest.mark.parametrize("role", ["BU", "CEO"])
def test_bu_and_ceo_cannot_edit_the_diagnosis(role_page, pending_bu, pending_ceo, role):
    """Qase #1214 (BU) and #1215 (CEO) -- HU-22 'Diagnosis' / V13 AC-11.3.2."""
    q = pending_bu if role == "BU" else pending_ceo
    qp = open_as_approver(role_page, role, q.title)
    for label in DIAG:
        assert not qp.diagnosis_field(label).is_editable(), f"{label} must be read-only for the {role} approver"


def test_fpm_can_only_edit_the_diagnosis_and_not_the_wo_snapshot_or_the_costs(role_page, pending_fpm):
    """Qase #1216 -- V13 AC-11.2.2."""
    qp = open_as_approver(role_page, "FPM", pending_fpm.title)
    assert qp.diagnosis_field("CAUSE").is_editable()
    assert not qp.wo_snapshot().field("WO Title").is_editable()
    assert not qp.wo_snapshot().field("OEM Name").is_editable()
    fse = qp.fse_arrangement()
    assert not fse.field("Statement of FSE Resource", "Support Engineers").is_editable()
    assert not fse.field("Labor Costs", "Labor Cost / Hour").is_editable()


# ================================================================================================ C. Recommendation
def test_reject_and_approve_stay_disabled_while_the_recommendation_is_empty(role_page, pending_fpm):
    """Qase #1217"""
    qp = open_as_approver(role_page, "FPM", pending_fpm.title)
    bar = qp.decision_bar().wait_until_visible()
    bar.type_recommendation("")
    assert not bar.approve_button().is_enabled()
    assert not bar.reject_button().is_enabled()


def test_reject_and_approve_are_enabled_once_a_recommendation_is_entered(role_page, pending_fpm):
    """Qase #1218"""
    qp = open_as_approver(role_page, "FPM", pending_fpm.title)
    bar = qp.decision_bar().wait_until_visible()
    bar.type_recommendation(REC)
    assert bar.approve_button().is_enabled() and bar.reject_button().is_enabled()
    bar.type_recommendation("")
    assert not bar.approve_button().is_enabled() and not bar.reject_button().is_enabled()


def test_a_recommendation_with_only_spaces_keeps_the_buttons_disabled(role_page, pending_fpm):
    """Qase #1219"""
    qp = open_as_approver(role_page, "FPM", pending_fpm.title)
    bar = qp.decision_bar().wait_until_visible()
    bar.type_recommendation("     ")
    assert not bar.approve_button().is_enabled() and not bar.reject_button().is_enabled()
    bar.recommendation().press_sequentially("a")
    assert bar.approve_button().is_enabled() and bar.reject_button().is_enabled()
    bar.type_recommendation("")


def test_the_recommendation_accepts_up_to_1000_characters_and_not_more(role_page, pending_fpm):
    """Qase #1221"""
    qp = open_as_approver(role_page, "FPM", pending_fpm.title)
    bar = qp.decision_bar().wait_until_visible()
    bar.paste_recommendation("a" * 1000)
    assert len(bar.value()) == 1000
    bar.recommendation().press_sequentially("z")
    assert len(bar.value()) == 1000, "the 1001st character must not be added"
    bar.paste_recommendation("b" * 1100)
    assert len(bar.value()) == 1000, "a longer text keeps only the first 1000 characters"
    bar.type_recommendation("")


def test_emoji_are_removed_from_the_recommendation_as_they_are_typed_or_pasted(role_page, pending_fpm):
    """Qase #1222 (the saved text is checked in the rejected-by-FPM scenario below)."""
    qp = open_as_approver(role_page, "FPM", pending_fpm.title)
    bar = qp.decision_bar().wait_until_visible()
    bar.paste_recommendation("Great \U0001F600 job \U0001F44D")
    assert bar.value() == "Great  job "
    bar.type_recommendation("Typed \U0001F600 too")
    assert bar.value() == "Typed  too"
    bar.type_recommendation("")


def test_the_counter_appears_from_900_characters(role_page, pending_fpm):
    """Qase #1224"""
    qp = open_as_approver(role_page, "FPM", pending_fpm.title)
    bar = qp.decision_bar().wait_until_visible()
    bar.paste_recommendation("a" * 899)
    assert bar.counter_text() is None, "no counter below 900 characters"
    bar.paste_recommendation("a" * 900)
    assert bar.counter_text() == "900 / 1000"
    bar.paste_recommendation("a" * 1000)
    assert bar.counter_text() == "1000 / 1000"
    bar.type_recommendation("")


def test_the_typed_recommendation_is_kept_when_the_approver_closes_the_quotation(role_page, keep_1):
    """Qase #1225 -- HU-22 'Recommendation': kept in the browser until the decision is saved."""
    qp = open_as_approver(role_page, "FPM", keep_1.title)
    qp.decision_bar().wait_until_visible().type_recommendation("Pending my final check")
    qp.close_form()
    qp.page.get_by_text(PENDING_PILL).first.wait_for(timeout=15000)
    qp.open_listed_quotation(keep_1.title)
    assert qp.decision_bar().wait_until_visible().value() == "Pending my final check"
    clear_kept_text(qp)


def test_the_typed_recommendation_is_kept_when_the_page_is_reloaded(role_page, keep_2):
    """Qase #1226"""
    qp = open_as_approver(role_page, "FPM", keep_2.title)
    qp.decision_bar().wait_until_visible().type_recommendation("Draft recommendation")
    page = qp.page
    page.reload()
    page.wait_for_timeout(3000)
    if "/login" in page.url:       # the session did not survive the reload: sign in again (native form), the text is in the browser storage
        from framework_ui.pages.auth.login_page import LoginPage
        from shared.config.credentials import load_role_credentials
        creds = load_role_credentials("FPM")
        LoginPage(page).login(creds["email"], creds["password"], method="native")
        page.wait_for_url(lambda url: "/login" not in url, timeout=20000)
    qp = QuotationPage(page).open()
    qp.open_listed_quotation(keep_2.title)
    assert qp.decision_bar().wait_until_visible().value() == "Draft recommendation"
    clear_kept_text(qp)


def test_the_kept_recommendation_belongs_to_one_user_and_one_quotation(role_page, keep_1, keep_2, pending_bu):
    """Qase #1227"""
    qp = open_as_approver(role_page, "FPM", keep_1.title)
    qp.decision_bar().wait_until_visible().type_recommendation("Only for the first quotation")
    qp.close_form()
    qp.page.get_by_text(PENDING_PILL).first.wait_for(timeout=15000)
    qp.open_listed_quotation(keep_2.title)
    assert qp.decision_bar().wait_until_visible().value() == "", "the text of another quotation must not appear"
    qp.close_form()
    qp.page.get_by_text(PENDING_PILL).first.wait_for(timeout=15000)
    bu = open_as_approver(role_page, "BU", pending_bu.title)
    assert bu.decision_bar().wait_until_visible().value() == "", "the text of another user must not appear"
    qp.open_listed_quotation(keep_1.title)
    clear_kept_text(qp)


def test_the_kept_recommendation_is_deleted_once_the_decision_is_saved(role_page):
    """Qase #1228 -- after the FPM/FSM rejection and the AM's new submit, the approver gets the quotation again with an empty field."""
    q = new(role_page, "C12", ["FPM", "BU"])
    decide(role_page, "FPM", q, "reject", "To be deleted after saving")
    resubmit(role_page, q)
    qp = open_as_approver(role_page, "FPM", q.title)
    assert qp.decision_bar().wait_until_visible().value() == "", "the kept text must be deleted once the decision is saved"


# ================================================================================================ scenarios that decide once
@pytest.fixture(scope="module")
def fpm_rejected(role_page, db_conn):
    """Route FPM -> BU; the FPM/FSM approver rejects with '  <b>cost</b> > budget <emoji> ' (spaces, markup characters and an emoji)."""
    q = new(role_page, "RJ1", ["FPM", "BU"])
    before = QuotationPage(role_page("FPM")).open(refresh=True).pending_approval_count()
    decide(role_page, "FPM", q, "reject", "  <b>cost</b> > budget \U0001F600 ")
    after = QuotationPage(role_page("FPM")).open(refresh=True).pending_approval_count()
    return dict(q=q, before=before, after=after)


@pytest.fixture(scope="module")
def fpm_approved(role_page):
    """Route FPM -> BU; the FPM/FSM approver approves with a plain recommendation."""
    q = new(role_page, "AP1", ["FPM", "BU"])
    before = QuotationPage(role_page("FPM")).open(refresh=True).pending_approval_count()
    decide(role_page, "FPM", q, "approve", "Approved after review.")
    after = QuotationPage(role_page("FPM")).open(refresh=True).pending_approval_count()
    return dict(q=q, before=before, after=after)


def test_leading_and_trailing_spaces_are_removed_when_the_decision_is_saved(db_conn, fpm_rejected):
    """Qase #1220 -- the saved recommendation of the rejected-by-FPM scenario has no outer spaces."""
    ev = eventually(lambda: last_event(db_conn, fpm_rejected["q"], "Rejected"))
    assert ev and ev["Comment"] == ev["Comment"].strip() and ev["Comment"].startswith("<b>")


def test_emoji_are_not_saved_in_the_recommendation(db_conn, fpm_rejected):
    """Qase #1222 (saved part)."""
    ev = eventually(lambda: last_event(db_conn, fpm_rejected["q"], "Rejected"))
    assert ev and "\U0001F600" not in ev["Comment"]


def test_less_than_and_greater_than_are_saved_and_shown_as_plain_text(role_page, db_conn, fpm_rejected):
    """Qase #1223"""
    ev = eventually(lambda: last_event(db_conn, fpm_rejected["q"], "Rejected"))
    assert ev and ev["Comment"] == "<b>cost</b> > budget"
    qp = am_open(role_page, fpm_rejected["q"])
    assert "<b>cost</b> > budget" in qp.rejected_banner_text(), "the markup characters must be shown as typed, not rendered"
    assert qp.page.get_by_text(re.compile("Rejected by")).first.locator("xpath=..").locator("b").count() == 0


# ================================================================================================ D. Approve
def test_fpm_approval_sends_the_quotation_back_to_the_am(role_page, db_conn, fpm_approved):
    """Qase #1229"""
    q = fpm_approved["q"]
    state = eventually(lambda: (s := get_quotation_state(db_conn, q.quote)) and s["EstadoCotizacion"] == "Returned" and s)
    assert state, f"after the FPM/FSM approval the quotation must be Returned to the AM: {get_quotation_state(db_conn, q.quote)}"
    assert "Returned" in am_row(role_page, q)
    qp = am_open(role_page, q)
    assert qp.diagnosis_field("CAUSE").is_editable(), "the AM must be able to edit the returned quotation"


@pytest.fixture(scope="module")
def bu_then_ceo(role_page):
    q = new(role_page, "BC1", ["BU", "CEO"])
    decide(role_page, "BU", q, "approve", REC)
    return q


def test_bu_approval_moves_the_quotation_to_the_next_approver(role_page, db_conn, bu_then_ceo):
    """Qase #1230"""
    assert in_list(role_page, "CEO", bu_then_ceo), "the quotation must be in the CEO approver's Pending approval list"
    qp = open_as_approver(role_page, "CEO", bu_then_ceo.title)
    assert qp.decision_bar().wait_until_visible().is_visible()
    assert get_quotation_state(db_conn, bu_then_ceo.quote)["EstadoCotizacion"] == "Awaiting"


@pytest.mark.parametrize("role", ["BU", "CEO"])
def test_last_internal_approval_leaves_the_quotation_waiting_for_the_oem(role_page, db_conn, role):
    """Qase #1231 (BU) and #1232 (CEO)."""
    q = new(role_page, f"LA{role}", [role])
    decide(role_page, role, q, "approve", REC)
    state = eventually(lambda: (s := get_quotation_state(db_conn, q.quote)) and s["EtapaWorkflow"] == "Vendor Reviewing" and s)
    assert state, f"nobody is left: the quotation must wait for the OEM review (Vendor Reviewing): {get_quotation_state(db_conn, q.quote)}"
    assert not any(a["Estado"] == "Pending" for a in get_approver_decisions_by_quote_no(db_conn, q.quote))
    assert re.search(r"OEM Review|Vendor", am_row(role_page, q))


# ================================================================================================ E. Reject
def test_fpm_rejection_sends_the_quotation_back_to_the_am(role_page, db_conn, fpm_rejected):
    """Qase #1234"""
    q = fpm_rejected["q"]
    state = eventually(lambda: (s := get_quotation_state(db_conn, q.quote)) and s["EstadoCotizacion"] == "Rejected" and s)
    assert state, f"must be Rejected and back with the AM: {get_quotation_state(db_conn, q.quote)}"
    assert "Rejected" in am_row(role_page, q)


@pytest.mark.parametrize("role", ["BU", "CEO"])
def test_bu_and_ceo_rejection_send_the_quotation_back_to_the_am(role_page, db_conn, role):
    """Qase #1235 (BU) and #1236 (CEO)."""
    q = new(role_page, f"RJ{role}", [role])
    decide(role_page, role, q, "reject", "Not approved at this amount.")
    state = eventually(lambda: (s := get_quotation_state(db_conn, q.quote)) and s["EstadoCotizacion"] == "Rejected" and s)
    assert state, f"must be Rejected and back with the AM: {get_quotation_state(db_conn, q.quote)}"
    assert "Rejected" in am_row(role_page, q)


def test_the_am_sees_the_rejected_by_banner_with_name_role_date_and_recommendation(role_page, fpm_rejected):
    """Qase #1237"""
    qp = am_open(role_page, fpm_rejected["q"])
    banner = qp.rejected_banner_text()
    assert "QA Jhe FPM" in banner and "FPM/FSM" in banner
    assert re.search(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}", banner), f"the banner must show the date and time: {banner}"
    assert "<b>cost</b> > budget" in banner


@pytest.fixture(scope="module")
def rejected_twice(role_page):
    q = new(role_page, "RJ2X", ["FPM"])
    decide(role_page, "FPM", q, "reject", "First rejection")
    resubmit(role_page, q)
    decide(role_page, "FPM", q, "reject", "Second rejection")
    return q


def test_the_banner_shows_only_the_most_recent_rejection(role_page, rejected_twice):
    """Qase #1238"""
    banner = am_open(role_page, rejected_twice).rejected_banner_text()
    assert "Second rejection" in banner and "First rejection" not in banner


def test_the_banner_disappears_once_the_am_submits_again(role_page, rejected_twice):
    """Qase #1239 (runs after the test above, on the same quotation)."""
    qp = am_open(role_page, rejected_twice)
    assert qp.page.get_by_text(re.compile("Rejected by")).count() > 0
    qp.close_form()
    resubmit(role_page, rejected_twice)
    qp = am_open(role_page, rejected_twice)
    expect(qp.page.get_by_text(re.compile("Rejected by"))).to_have_count(0)


# ================================================================================================ F. After deciding
def test_after_approving_the_quotation_leaves_the_pending_list(role_page, fpm_approved):
    """Qase #1240"""
    assert fpm_approved["after"] == fpm_approved["before"] - 1
    assert not_in_list(role_page, "FPM", fpm_approved["q"])


def test_after_rejecting_the_quotation_leaves_the_pending_list(role_page, fpm_rejected):
    """Qase #1241"""
    assert fpm_rejected["after"] == fpm_rejected["before"] - 1
    assert not_in_list(role_page, "FPM", fpm_rejected["q"])


def test_an_approval_is_recorded_with_approver_outcome_recommendation_and_date(db_conn, fpm_approved):
    """Qase #1242 (database part; the screen part is test_the_approval_shows_in_the_quotation_history)."""
    q = fpm_approved["q"]
    ev = eventually(lambda: last_event(db_conn, q, "Approved"))
    assert ev and ev["ActorRole"] == "FPM_FSM" and ev["ActorName"] == "QA Jhe FPM"
    assert ev["Comment"] == "Approved after review." and ev["OccurredAt"] is not None
    row = [a for a in get_approver_decisions_by_quote_no(db_conn, q.quote) if a["Rol"] == "FPM_FSM"][0]
    assert row["Estado"] == "Approved" and row["Comentario"] == "Approved after review." and row["FechaRespuesta"] is not None


def test_a_rejection_is_recorded_with_approver_outcome_recommendation_and_date(db_conn, fpm_rejected):
    """Qase #1243 (database part)."""
    q = fpm_rejected["q"]
    ev = eventually(lambda: last_event(db_conn, q, "Rejected"))
    assert ev and ev["ActorRole"] == "FPM_FSM" and ev["ActorName"] == "QA Jhe FPM"
    assert ev["Comment"] == "<b>cost</b> > budget" and ev["OccurredAt"] is not None
    row = [a for a in get_approver_decisions_by_quote_no(db_conn, q.quote) if a["Rol"] == "FPM_FSM"][0]
    assert row["Estado"] == "Rejected" and row["Comentario"] == "<b>cost</b> > budget"


def test_an_approver_who_already_decided_sees_the_quotation_without_the_bar_when_opening_it_again(role_page, db_conn, fpm_approved):
    """Qase #1244 -- out of their list, and opened by its own link it is read-only with no decision bar."""
    assert not_in_list(role_page, "FPM", fpm_approved["q"])
    qp = QuotationPage(role_page("FPM")).open_by_link(get_quotation_id(db_conn, fpm_approved["q"].quote))
    expect(qp.decision_bar().recommendation()).to_have_count(0)
    expect(qp.decision_bar().approve_button()).to_have_count(0)
    assert not qp.diagnosis_field("CAUSE").is_editable()


def history_of(role_page, q):
    qp = am_page(role_page).open_workflow_history(q.title)
    return qp.workflow_history_text()


def test_the_approval_shows_in_the_quotation_history(role_page, fpm_approved):
    """Qase #1242 (screen part) -- the status of the row opens the Quotation Workflow panel with the decision."""
    text = history_of(role_page, fpm_approved["q"])
    assert "QA Jhe FPM" in text and "FPM/FSM" in text and "Approved" in text and "Approved after review." in text
    assert text.index("QA Jhe FPM") < text.index("Approved after review.")
    assert re.search(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}", text[text.index("QA Jhe FPM"):])


def test_the_rejection_shows_in_the_quotation_history(role_page, fpm_rejected):
    """Qase #1243 (screen part)."""
    text = history_of(role_page, fpm_rejected["q"])
    assert "QA Jhe FPM" in text and "FPM/FSM" in text and "Rejected" in text
    assert "<b>cost</b> > budget" in text, "the recommendation is shown as typed, as plain text"
    assert re.search(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}", text[text.index("QA Jhe FPM"):])


# ================================================================================================ G. One decision per turn
def test_a_double_click_on_approve_saves_only_one_decision(role_page, db_conn):
    """Qase #1245"""
    q = new(role_page, "G1", ["FPM", "BU"])
    qp = open_as_approver(role_page, "FPM", q.title)
    bar = qp.decision_bar().wait_until_visible()
    bar.type_recommendation(REC)
    bar.approve_button().dblclick()
    qp.page.get_by_text(PENDING_PILL).first.wait_for(timeout=25000)
    time.sleep(2)
    approved = [e for e in get_events_by_quote_no(db_conn, q.quote) if e["EventType"] == "Approved"]
    assert len(approved) == 1, f"exactly one Approved event expected, found {len(approved)}"


@pytest.fixture(scope="module")
def second_tab_attempt(role_page, db_conn):
    """Route FPM -> BU. The FPM/FSM approver has the quotation open in two tabs, approves in the first and then tries to reject in the second."""
    q = new(role_page, "G2", ["FPM", "BU"])
    first = open_as_approver(role_page, "FPM", q.title)
    tab2 = role_page("FPM").context.new_page()
    tab2.goto(first.page.url)                      # the quotation's own link, in a second tab of the same session
    second = QuotationPage(tab2)
    second.decision_bar().wait_until_visible()
    first.decision_bar().decide("approve", REC)
    first.page.get_by_text(PENDING_PILL).first.wait_for(timeout=25000)
    second.decision_bar().type_recommendation("Second tab attempt")
    tab2.evaluate("""() => { window.__seen = []; new MutationObserver(ms => { for (const m of ms) for (const n of m.addedNodes) { const tx = (n.textContent || '').trim();
        if (tx && tx.length < 300) window.__seen.push(tx); } }).observe(document.body, {childList: true, subtree: true, characterData: true}); }""")
    second.decision_bar().reject_button().click()
    tab2.wait_for_timeout(5000)
    yield dict(q=q, tab2=tab2, second=second, seen=tab2.evaluate("window.__seen"))
    tab2.close()


def test_a_decision_from_a_second_tab_shows_an_error_and_is_not_saved(db_conn, second_tab_attempt):
    """Qase #1246 (error part) -- the second tab is told that the quotation was already decided ("This quotation was already approved." since the build of 2026-11-09; it said "Only
    quotations awaiting approval can be approved or rejected." before) and only the first decision is saved. The message is shown for a moment, so the page is watched from before the click."""
    q, seen = second_tab_attempt["q"], second_tab_attempt["seen"]
    assert any("already approved" in text for text in seen), f"no message that the quotation was already decided; the page showed: {seen[:8]}"
    kinds = [e["EventType"] for e in get_events_by_quote_no(db_conn, q.quote)]
    assert kinds.count("Approved") == 1 and kinds.count("Rejected") == 0, f"only the first decision must be saved: {kinds}"


def test_the_second_tab_view_refreshes_after_the_error(second_tab_attempt):
    """Qase #1246 (refresh part; defect #144 / OP-117, fixed in the build of 2026-11-09, Ready for QA 2026-11-06) -- after the error the stale tab is refreshed: no decision bar for a decided quotation
    (HU-22 'One decision per turn': 'The other attempt shows an error and the view refreshes.')."""
    tab2 = second_tab_attempt["tab2"]
    tab2.wait_for_timeout(5000)
    assert second_tab_attempt["second"].decision_bar().recommendation().count() == 0, "the stale tab must refresh: no decision bar for a decided quotation"


# ================================================================================================ H. Save failure
def test_while_saving_the_button_shows_saving_and_the_bar_is_disabled(role_page, pending_fpm):
    """Qase #1247 -- the decision request is held 2.5 s and then dropped, so the quotation is not decided."""
    qp = open_as_approver(role_page, "FPM", pending_fpm.title)
    page = qp.page
    bar = qp.decision_bar().wait_until_visible()

    def slow_abort(route):
        if route.request.method == "GET":
            return route.continue_()
        page.wait_for_timeout(2500)
        route.abort()

    page.route("**/api/**", slow_abort)
    try:
        bar.type_recommendation(REC)
        bar.approve_button().click()
        page.wait_for_timeout(600)
        assert bar.approve_button().inner_text().strip() == "Saving..."
        assert not bar.recommendation().is_enabled() and not bar.reject_button().is_enabled() and not bar.approve_button().is_enabled()
    finally:
        page.wait_for_timeout(3000)
        page.unroute("**/api/**")
    bar.type_recommendation("")


def test_when_the_decision_cannot_be_saved_an_error_is_shown_and_the_quotation_stays_as_it_was(role_page, db_conn, pending_fpm):
    """Qase #1248"""
    qp = open_as_approver(role_page, "FPM", pending_fpm.title)
    page = qp.page
    bar = qp.decision_bar().wait_until_visible()
    page.route("**/api/**", lambda route: route.continue_() if route.request.method == "GET" else route.abort())
    try:
        bar.type_recommendation("Rejected while offline")
        bar.reject_button().click()
        expect(page.get_by_text("Could not save this decision.")).to_be_visible(timeout=10000)
        assert bar.is_visible(), "the quotation stays open with its decision bar"
    finally:
        page.unroute("**/api/**")
    state = get_quotation_state(db_conn, pending_fpm.quote)
    assert state["EstadoCotizacion"] == "Awaiting", f"nothing was saved: {state}"
    bar.type_recommendation("")


# ================================================================================================ I. Server-side rule
def test_the_server_refuses_a_decision_from_a_user_whose_turn_it_is_not(role_page, db_conn, pending_fpm_bu):
    """Qase #1249 -- V13 AC-10.4.5. The BU approver (second in the route) sends the same request the bar sends."""
    bu = role_page("BU")
    quotation_id = db_conn.cursor()
    quotation_id.execute('SELECT "Id" FROM quotation."Quotation" WHERE "QuoteNo" = %s', (pending_fpm_bu.quote,))
    qid = quotation_id.fetchone()[0]
    result = bu.evaluate("""async ([id]) => {
        const token = Object.values(localStorage).find(v => typeof v === 'string' && v.split('.').length === 3);
        const r = await fetch(`/api/quotations/${id}/approve`, {method: 'POST', credentials: 'include',
            headers: {'Content-Type': 'application/json', ...(token ? {Authorization: 'Bearer ' + token} : {})},
            body: JSON.stringify({comment: 'Out of turn'})});
        return {status: r.status};
    }""", [str(qid)])
    assert result["status"] in (400, 401, 403, 409, 422), f"an out-of-turn decision must be refused, got HTTP {result['status']}"
    decisions = get_approver_decisions_by_quote_no(db_conn, pending_fpm_bu.quote)
    assert all(a["Estado"] == "Pending" for a in decisions), f"nobody decided: {decisions}"


# ================================================================================================ D5 (mutates fpm_approved: keep last)
def test_the_am_can_submit_again_after_the_fpm_approval_and_it_continues_to_the_bu_approver(role_page, db_conn, fpm_approved):
    """Qase #1233 -- HU-22 'Approve' / V13 AC-11.2.3."""
    q = fpm_approved["q"]
    resubmit(role_page, q)
    assert in_list(role_page, "BU", q), "the quotation must now be in the BU approver's Pending approval list"
    fpm_row = [a for a in get_approver_decisions_by_quote_no(db_conn, q.quote) if a["Rol"] == "FPM_FSM"][0]
    assert fpm_row["Estado"] == "Approved", "the FPM/FSM approval is kept"
    assert not in_list(role_page, "FPM", q), "the FPM/FSM approver is not asked again"
