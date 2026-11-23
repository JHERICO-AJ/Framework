"""Quotation module -- roles and permissions on screen (HU-25, Qase suite "HU-25: Quotation roles and permissions", cases RL-LV*, RL-AM*, RL-AP*, RL-NR*, RL-OA*).

Only the HU-25 text and its two mockups decide what must happen. ADMIN is out of scope (the developer said it is future work, no requirement yet), so there are no ADMIN cases.
Accounts (.env QUOTATION_<ROLE>_*): AM (Jherico), AM2 (a second AM, Sebastian), FPM, BU and CEO approvers, and NOROLE (a user with no Quotation role). The quotations of the "other AM"
are created through the API with the AM2 account (titles start with 'Workflow Progress test HU25-'), so nobody else's data is touched.
Confirmed on the QA build of 2026-10-29: a link to a quotation the user cannot open keeps the landing view and shows the red message 'Access Denied Only the responsible AM or an approver
on this quotation's current route can view it.'; the approvers can open (read-only) a quotation of their route even when it is not their turn.
"""
import re

import pytest
from playwright.sync_api import expect

from framework_api.services import quotation_setup as qs
from framework_ui.pages.auth.login_page import LoginPage
from framework_ui.pages.quotation.quotation_page import QuotationPage
from shared.config.credentials import load_role_credentials
from shared.config.settings import BASE_URL
from shared.datasource.db_connection import open_readonly_connection

pytestmark = pytest.mark.ui

SUBTITLE_AM = "Landing view: active quotations and current approval workflow status."
SUBTITLE_APPROVER = "Landing view: quotations pending your approval action."
SUBTITLE_NO_ROLE = "No Quotation role is assigned to your account. Contact an administrator if you need access."
MESSAGE_NO_ROLE = "Quotation access requires an AM, FPM/FSM, BU, or CEO role assignment."  # fixed by the developer (2026-11-05 answer, deployed 2026-11-09)
DENIED = re.compile(r"Access Denied.*Only the responsible AM or an approver on this quotation.s current route can view it", re.S)
PENDING_PILL = re.compile(r"Pending approval\s*\(\d+\)")
QUOTE_NO = re.compile(r"\bFS[A-Z]\d{8}\b")
AM_COLUMNS = ["WO / QUOTE #", "WO TITLE", "SITE", "WAITING ON", "AGE", "CURRENT STEP", "SOURCE", "STATUS"]
APPROVER_COLUMNS = ["WO NUMBER", "WO TITLE", "SITE NAME", "RESPONSIBLE AM", "AMOUNT", "AWAITING MY SIGNATURE"]
DIAGNOSIS = ["SIGNAL", "TRIGGER", "CAUSE", "NOTES", "SOP / STEPS"]


# ------------------------------------------------------------------------------------------------ fixtures

@pytest.fixture(scope="module")
def other(api_roles, api_other):
    """Quotations of the other AM (AM2): a Draft and one that waits on FPM/FSM and then BU; and a Draft of the first AM."""
    return {"draft": qs.create_draft(api_other["AM2"], api_roles, "UI-D", title_prefix="HU25")[0],
            "awaiting": qs.create_and_submit(api_other["AM2"], api_roles, "UI-A", ["FPM", "BU"], title_prefix="HU25")[0],
            "am_draft": qs.create_draft(api_roles["AM"], api_roles, "UI-AMD", title_prefix="HU25")[0]}


@pytest.fixture(scope="module")
def turn(api_roles):
    """One quotation per approver that waits on that approver only (it is their turn)."""
    return {role: qs.create_and_submit(api_roles["AM"], api_roles, f"UI-T{role}", [role], title_prefix="HU25")[0] for role in ("FPM", "BU", "CEO")}


@pytest.fixture(scope="module")
def fpm_edit(api_roles):
    return qs.create_and_submit(api_roles["AM"], api_roles, "UI-EDIT", ["FPM"], title_prefix="HU25")[0]


@pytest.fixture
def fresh_page(_role_browser):
    """fresh_page('AM') -> a page of its own (no draft typed before in that browser), closed at the end."""
    pages = []

    def get(role):
        creds = load_role_credentials(role)
        page = _role_browser.new_isolated_page()
        LoginPage(page).login(creds["email"], creds["password"], method="native")
        page.wait_for_url(lambda url: "/login" not in url, timeout=20000)
        pages.append(page)
        return page
    yield get
    for page in pages:
        page.close()


def landing(role_page, role):
    return QuotationPage(role_page(role)).open(refresh=True)


def quote_numbers_of(email):
    conn = open_readonly_connection()
    try:
        with conn.cursor() as cur:
            cur.execute('SELECT "QuoteNo" FROM quotation."Quotation" WHERE lower("CreadoPorEmail") = %s', (email.lower(),))
            return {r[0] for r in cur.fetchall() if r[0]}
    finally:
        conn.close()


def visible_text(page, text, exact=False):
    locator = page.get_by_text(text, exact=exact)
    return any(locator.nth(i).is_visible() for i in range(locator.count()))


def assert_denied_link(page, quotation_id):
    """The link of a quotation the user cannot open: the landing view stays, the red message appears, and no form opens."""
    page.goto(f"{BASE_URL}/quotation/{quotation_id}", timeout=60000)
    expect(page.get_by_text(DENIED).first).to_be_visible(timeout=25000)
    assert page.get_by_text("WO Snapshot", exact=True).count() == 0, "the form of the quotation must not open"


# ------------------------------------------------------------------------------------------------ landing view by role

def test_the_am_lands_on_quotes_in_progress_with_its_subtitle(role_page):
    """Qase RL-LV1 -- AM: Quotes in Progress, subtitle 'Landing view: active quotations and current approval workflow status.'."""
    qp = landing(role_page, "AM")
    page = qp.page
    expect(page.get_by_text("Quotation (WO) Creation", exact=True)).to_be_visible()
    expect(page.get_by_text(SUBTITLE_AM, exact=True)).to_be_visible()
    expect(page.get_by_text(re.compile(r"Quotes in Progress\s*\(\d+\)"))).to_be_visible()
    assert not visible_text(page, SUBTITLE_APPROVER)


@pytest.mark.parametrize("role", ["FPM", "BU", "CEO"])
def test_each_approver_lands_on_pending_approval_with_its_subtitle(role, role_page):
    """Qase RL-LV2 (FPM/FSM), RL-LV3 (BU), RL-LV4 (CEO) -- Pending approval, subtitle 'Landing view: quotations pending your approval action.'."""
    page = landing(role_page, role).page
    expect(page.get_by_text("Quotation (WO) Creation", exact=True)).to_be_visible()
    expect(page.get_by_text(SUBTITLE_APPROVER, exact=True)).to_be_visible()
    expect(page.get_by_text(PENDING_PILL)).to_be_visible()
    assert not visible_text(page, SUBTITLE_AM)


def test_the_am_can_switch_to_historical_quotes(role_page):
    """Qase RL-LV5 -- the AM can switch from Quotes in Progress to Historical Quotes and back."""
    qp = landing(role_page, "AM")
    page = qp.page
    page.get_by_text("Historical Quotes", exact=True).first.click()
    page.wait_for_timeout(2000)
    assert page.get_by_text(re.compile(r"Quotes in Progress")).count() >= 1 and QUOTE_NO.findall(page.locator("main").first.inner_text())
    page.get_by_text(re.compile(r"Quotes in Progress")).first.click()
    page.wait_for_timeout(1500)
    expect(page.get_by_text(SUBTITLE_AM, exact=True)).to_be_visible()


def columns_in_order(page, names):
    xs = []
    for name in names:
        header = page.get_by_text(re.compile(rf"^\s*{re.escape(name)}\s*$", re.I)).first
        header.wait_for(state="visible", timeout=15000)
        xs.append(header.bounding_box()["x"])
    return xs


def test_the_list_of_the_am_has_the_columns_of_the_mockup(role_page):
    """Qase RL-LV6 -- WO / QUOTE #, WO TITLE, SITE, WAITING ON, AGE, CURRENT STEP, SOURCE and STATUS, in that order."""
    xs = columns_in_order(landing(role_page, "AM").page, AM_COLUMNS)
    assert xs == sorted(xs)


def test_the_pending_approval_list_has_the_columns_of_the_mockup(role_page):
    """Qase RL-LV7 -- WO NUMBER, WO TITLE, SITE NAME, RESPONSIBLE AM, AMOUNT and AWAITING MY SIGNATURE, in that order."""
    xs = columns_in_order(landing(role_page, "FPM").page, APPROVER_COLUMNS)
    assert xs == sorted(xs)


# ------------------------------------------------------------------------------------------------ the AM

def test_the_am_sees_create_quotation_and_upload_file(role_page):
    """Qase RL-AM1 -- the buttons 'Upload file' and 'Create Quotation' are shown."""
    page = landing(role_page, "AM").page
    expect(page.get_by_role("button", name="Create Quotation", exact=True)).to_be_visible()
    expect(page.get_by_text("Upload file", exact=True).first).to_be_visible()


def test_the_am_sees_the_quotation_speed_and_hit_rate_indicators(role_page):
    """Qase RL-AM2 -- the indicators 'Quotation speed' and 'Hit rate' (Last 30 days) are shown."""
    page = landing(role_page, "AM").page
    for text in ("Quotation speed", "Hit rate"):
        expect(page.locator("main").get_by_text(re.compile(rf"^{text}$", re.I)).first).to_be_visible()
    expect(page.locator("main").get_by_text(re.compile(r"^Last 30 days$", re.I)).and_(page.locator(":not(option)")).first).to_be_visible()


def test_current_quote_is_not_offered_when_no_draft_is_in_progress(fresh_page):
    """Qase RL-AM3 -- a browser with no local draft does not show the button 'Current Quote'."""
    qp = QuotationPage(fresh_page("AM")).open()
    qp.page.wait_for_timeout(1500)
    assert qp.page.get_by_role("button", name="Current Quote").count() == 0


def test_current_quote_is_offered_when_a_local_draft_is_in_progress(fresh_page):
    """Qase RL-AM4 -- after typing in a new quotation and closing it without saving, the button 'Current Quote' appears and opens that draft."""
    qp = QuotationPage(fresh_page("AM")).open()
    page = qp.page
    qp.create_quotation()
    page.get_by_placeholder(re.compile("title", re.I)).first.fill("HU25 local draft")
    page.wait_for_timeout(1000)
    page.get_by_role("button", name=re.compile(r"^close$", re.I)).first.click()
    page.wait_for_timeout(2000)
    button = page.get_by_role("button", name="Current Quote")
    expect(button).to_be_visible()
    button.click()
    expect(page.get_by_text("WO Snapshot", exact=True)).to_be_visible(timeout=15000)
    assert page.get_by_placeholder(re.compile("title", re.I)).first.input_value() == "HU25 local draft"


def test_the_am_does_not_see_the_pending_approval_list(role_page):
    """Qase RL-AM5 -- no 'Pending approval' list, no subtitle of the approvers."""
    page = landing(role_page, "AM").page
    page.wait_for_timeout(1500)
    assert page.get_by_text(re.compile(r"Pending approval")).count() == 0
    assert not visible_text(page, SUBTITLE_APPROVER)


@pytest.mark.parametrize("who, other_who", [("AM", "AM2"), ("AM2", "AM")])
@pytest.mark.parametrize("tab", ["Quotes in Progress", "Historical Quotes"])
def test_an_am_sees_only_the_quotations_it_is_responsible_for(who, other_who, tab, role_page, other):
    """Qase RL-AM6 (AM, Quotes in Progress), RL-AM7 (AM, Historical Quotes), RL-AM8 (AM2, Quotes in Progress), RL-AM9 (AM2, Historical Quotes) --
    every Quote # of the page belongs to the AM of the session (according to the database) and none belongs to the other AM."""
    page = landing(role_page, who).page
    if tab == "Historical Quotes":
        page.get_by_text("Historical Quotes", exact=True).first.click()
        page.wait_for_timeout(2000)
    page.get_by_text(QUOTE_NO).first.wait_for(state="visible", timeout=20000)
    shown = set(QUOTE_NO.findall(page.locator("main").first.inner_text()))
    own, foreign = quote_numbers_of(load_role_credentials(who)["email"]), quote_numbers_of(load_role_credentials(other_who)["email"])
    assert shown, "the list is empty: nothing to check"
    assert shown <= own and not shown & foreign, f"not own: {sorted(shown - own)}"


# ------------------------------------------------------------------------------------------------ the approvers

@pytest.mark.parametrize("role", ["FPM", "BU", "CEO"])
def test_the_approvers_do_not_see_create_quotation_or_upload_file(role, role_page):
    """Qase RL-AP1 (FPM/FSM), RL-AP2 (BU), RL-AP3 (CEO) -- no 'Create Quotation' and no 'Upload file'."""
    page = landing(role_page, role).page
    page.wait_for_timeout(1500)
    assert page.get_by_role("button", name="Create Quotation").count() == 0 and page.get_by_text("Upload file", exact=True).count() == 0


@pytest.mark.parametrize("role", ["FPM", "BU", "CEO"])
def test_the_approvers_have_only_the_pending_approval_list(role, role_page):
    """Qase RL-AP4 (FPM/FSM), RL-AP5 (BU), RL-AP6 (CEO) -- no Quotes in Progress, no Historical Quotes, no Current Quote, no Quotation speed / Hit rate."""
    page = landing(role_page, role).page
    page.wait_for_timeout(1500)
    for text in ("Quotes in Progress", "Historical Quotes", "Quotation speed", "Hit rate"):
        assert page.get_by_text(re.compile(text, re.I)).count() == 0, text
    assert page.get_by_role("button", name="Current Quote").count() == 0


def test_an_approver_opens_a_quotation_read_only_and_without_the_decision_bar_when_it_is_not_their_turn(role_page, other):
    """Qase RL-AP7 -- the BU of the route opens the quotation of the other AM while the FPM/FSM is the one pending: read-only and no decision bar."""
    qp = QuotationPage(role_page("BU")).open(refresh=True).open_by_link(other["awaiting"])
    for label in DIAGNOSIS:
        assert not qp.diagnosis_field(label).is_editable(), f"{label} must be read-only"
    assert not qp.wo_snapshot().field("WO Title").is_editable()
    assert not qp.decision_bar().is_visible()


def test_the_fpm_sees_the_decision_bar_when_it_is_their_turn(role_page, turn):
    """Qase RL-AP8 -- the FPM/FSM opens a quotation that waits on them: the recommendation field and the buttons Reject and Approve are shown."""
    qp = QuotationPage(role_page("FPM")).open(refresh=True).open_by_link(turn["FPM"])
    assert qp.decision_bar().wait_until_visible().is_visible()


@pytest.mark.parametrize("role", ["BU", "CEO"])
def test_the_bu_and_the_ceo_see_the_decision_bar_but_cannot_edit_anything(role, role_page, turn):
    """Qase RL-AP9 (BU), RL-AP10 (CEO) -- on their turn they decide, and every field including the five of the diagnosis is read-only."""
    qp = QuotationPage(role_page(role)).open(refresh=True).open_by_link(turn[role])
    assert qp.decision_bar().wait_until_visible().is_visible()
    for label in DIAGNOSIS:
        assert not qp.diagnosis_field(label).is_editable(), f"{label} must be read-only for the {role}"
    assert not qp.wo_snapshot().field("WO Title").is_editable()


def test_the_fpm_can_edit_only_the_five_fields_of_the_diagnosis_on_their_turn(role_page, turn):
    """Qase RL-AP11 -- the exception of the story: Signal, Trigger, Cause, Notes and SOP/Steps are editable; WO Title and OEM Name are not."""
    qp = QuotationPage(role_page("FPM")).open(refresh=True).open_by_link(turn["FPM"])
    for label in DIAGNOSIS:
        assert qp.diagnosis_field(label).is_editable(), f"{label} must be editable for the FPM/FSM"
    assert not qp.wo_snapshot().field("WO Title").is_editable() and not qp.wo_snapshot().field("OEM Name").is_editable()


def test_the_changes_of_the_fpm_are_saved_with_their_decision(role_page, fpm_edit, api_roles):
    """Qase RL-AP12 -- the FPM/FSM edits the Cause, approves, and the quotation keeps the new Cause."""
    qp = QuotationPage(role_page("FPM")).open(refresh=True).open_by_link(fpm_edit)
    qp.diagnosis_field("CAUSE").fill("Cause written by the FPM/FSM (HU25)")
    bar = qp.decision_bar().wait_until_visible()
    bar.type_recommendation("Agreed, with my cause.")
    bar.approve_button().click()
    qp.page.wait_for_timeout(4000)
    assert api_roles["AM"].get(f"/api/quotations/{fpm_edit}").json()["cause"] == "Cause written by the FPM/FSM (HU25)"


# ------------------------------------------------------------------------------------------------ a user with no Quotation role

def test_a_user_with_no_role_sees_the_subtitle_and_the_message_of_the_story(role_page):
    """Qase RL-NR1 -- subtitle 'No Quotation role is assigned to your account. Contact an administrator if you need access.' and, in place of the list,
    'Quotation access requires an AM, FPM/FSM, BU, or CEO role assignment.' (the CEO was added by the developer; fixed, Qase defect #181)."""
    page = landing(role_page, "NOROLE").page
    expect(page.get_by_text(SUBTITLE_NO_ROLE, exact=True)).to_be_visible()
    expect(page.get_by_text(MESSAGE_NO_ROLE, exact=True)).to_be_visible()


def test_a_user_with_no_role_has_no_list_and_no_actions(role_page):
    """Qase RL-NR2 -- no pills, no filters, no rows, no Create Quotation, no Upload file, no Current Quote, no indicators."""
    page = landing(role_page, "NOROLE").page
    page.wait_for_timeout(1500)
    for text in ("Quotes in Progress", "Historical Quotes", "Pending approval", "Quotation speed", "Hit rate", "Upload file"):
        assert page.get_by_text(re.compile(text, re.I)).count() == 0, text
    for name in ("Create Quotation", "Current Quote"):
        assert page.get_by_role("button", name=name).count() == 0, name
    assert not QUOTE_NO.findall(page.locator("main").first.inner_text())


def test_a_user_with_no_role_cannot_open_a_quotation_by_its_link(role_page, other):
    """Qase RL-NR3 -- the link of a quotation shows the red message of the refusal and the message of the story, never the form."""
    page = role_page("NOROLE")
    assert_denied_link(page, other["awaiting"])
    expect(page.get_by_text(MESSAGE_NO_ROLE, exact=True)).to_be_visible()


# ------------------------------------------------------------------------------------------------ the quotations of another AM, by link

@pytest.mark.parametrize("who, key", [("AM", "draft"), ("AM", "awaiting"), ("AM2", "am_draft")])
def test_an_am_cannot_open_the_quotation_of_another_am_by_its_link(who, key, role_page, other):
    """Qase RL-OA1 (AM, a Draft of the other AM), RL-OA2 (AM, one that waits on an approver), RL-OA3 (AM2, a Draft of the first AM) --
    the landing view stays, the red message appears and the form does not open."""
    page = role_page(who)
    QuotationPage(page).open(refresh=True)
    assert_denied_link(page, other[key])


@pytest.mark.parametrize("key", ["draft", "awaiting"])
def test_an_approver_that_is_not_on_the_route_cannot_open_the_quotation_by_its_link(key, role_page, other):
    """Qase RL-OA4 (CEO, a quotation of the route FPM/FSM and BU), RL-OA5 (CEO, a Draft) -- red message and no form."""
    page = role_page("CEO")
    QuotationPage(page).open(refresh=True)
    assert_denied_link(page, other[key])


def test_the_link_of_a_quotation_that_does_not_exist_opens_no_form(role_page):
    """Qase RL-OA6 -- an id that does not exist: the landing view stays and no form opens."""
    page = role_page("AM")
    QuotationPage(page).open(refresh=True)
    page.goto(f"{BASE_URL}/quotation/00000000-0000-0000-0000-000000000000", timeout=60000)
    page.wait_for_timeout(4000)
    assert page.get_by_text("WO Snapshot", exact=True).count() == 0


# ------------------------------------------------------------------------------------------------ the create form has no address of its own

def test_the_am_opens_a_blank_form_that_can_be_edited(role_page):
    """Qase RL-AM10 -- 'Create Quotation' opens the blank form of the AM: WO Title and Customer are empty and editable."""
    qp = QuotationPage(role_page("AM")).open(refresh=True)
    qp.create_quotation()
    assert qp.wo_snapshot().field("WO Title").is_editable() and qp.wo_snapshot().field("WO Title").input_value() == ""
    qp.page.get_by_role("button", name=re.compile(r"^close$", re.I)).first.click()


@pytest.mark.parametrize("role", ["FPM", "BU", "CEO", "NOROLE"])
def test_no_address_opens_the_create_form_for_who_is_not_an_am(role, role_page):
    """Qase RL-OA7 -- the create form has no address of its own (it stays on /quotation); the addresses a person could guess
    (/quotation/new, /quotation/create, /quotation?view=create) open no form for an approver or a user with no role."""
    page = role_page(role)
    for path in ("/quotation/new", "/quotation/create", "/quotation?view=create"):
        page.goto(f"{BASE_URL}{path}", timeout=60000)
        page.wait_for_timeout(2500)
        assert page.get_by_text("WO Snapshot", exact=True).count() == 0, f"{role} opened a form with {path}"
        assert page.get_by_role("button", name="Create Quotation").count() == 0


# ------------------------------------------------------------------------------------------------ the names of the roles

FORBIDDEN_NAMES = ("BU Office", "CEO Office", "BU Manager", "COO")


def role_labels(role_page, api_roles, role):
    """The text of the three places that name the approver's role for a quotation that waits only on `role`: the 'Waiting on' column of the landing list,
    the 'Quotation Workflow' panel and the window 'Approved Personnel Settings'."""
    qid, _ = qs.create_and_submit(api_roles["AM"], api_roles, f"UI-NAMES{role}", [role], title_prefix="HU25")
    title = api_roles["AM"].get(f"/api/quotations/{qid}").json()["title"]
    qp = QuotationPage(role_page("AM")).open(refresh=True)
    page = qp.page
    landing_text = qp._row(title).inner_text()
    qp.open_workflow_history(title)
    panel = qp.workflow_history_text()
    page.get_by_role("button", name="Close", exact=True).first.click()
    qp.open_by_link(qid)
    page.get_by_role("button", name="Setup Approval Progress").click()
    window = page.get_by_text(re.compile(r"^Approved Personnel Settings$", re.I)).first
    window.wait_for(timeout=15000)
    modal = page.locator("div").filter(has=window).filter(has_text="Added signers").last.inner_text()
    return {"landing": landing_text, "panel": panel, "window": modal}


@pytest.mark.parametrize("role, name", [("BU", "BU"), ("CEO", "CEO")])
def test_bu_and_ceo_have_the_same_name_in_every_place_of_the_module(role, name, role_page, api_roles):
    """Qase RL-NM1 (BU), RL-NM2 (CEO) -- 'BU' and 'CEO' (not 'BU Office', 'CEO Office' or 'BU Manager') in the Waiting on column, the workflow panel and the signers window."""
    texts = role_labels(role_page, api_roles, role)
    for place, text in texts.items():
        assert re.search(rf"\b{name}\b", text), f"{place}: no '{name}' in {text[:120]!r}"
        assert not [n for n in FORBIDDEN_NAMES if n in text], f"{place}: {[n for n in FORBIDDEN_NAMES if n in text]}"


def test_fpm_fsm_has_the_same_name_in_every_place_of_the_module(role_page, api_roles):
    """Qase RL-NM3 -- 'FPM/FSM' in the Waiting on column, the workflow panel and the signers window (never the code FPM_FSM)."""
    texts = role_labels(role_page, api_roles, "FPM")
    for place, text in texts.items():
        assert "FPM/FSM" in text and "FPM_FSM" not in text, f"{place}: {text[:140]!r}"


def test_the_message_for_a_user_with_no_role_names_every_approver_role(role_page):
    """Qase RL-NR4 -- the message in the place of the list names the roles that give access, the CEO included (QA comment of 2026-10-16, Qase defect #181)."""
    page = landing(role_page, "NOROLE").page
    expect(page.get_by_text(re.compile(r"^Quotation access requires .*CEO")).first).to_be_visible(timeout=5000)
