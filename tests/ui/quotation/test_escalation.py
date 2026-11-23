"""Quotation module -- Escalation of the quotation across approval levels (OP-32 / HU-21, Qase suite "HU-21: Escalation of the quotation across approval levels").

Only the HU-21 text is used for what must happen (Quotation_Spec V13/V14 were read to judge the criteria, not to add any). Every quotation is created by the AM through the API with
the route the test names and driven (approve / reject / resubmit) by the role accounts through the API too; what is checked is what the screen shows:
  - the AM's list: Waiting on, Current step and Status of the row;
  - the Pending approval list of each approver (who has the quotation and who does not);
  - the 'Approved Personnel Settings' window (the route, with the approvers the system added);
  - the 'Quotation Workflow' panel (history) and the Workflow Progress diagram.
The amount rules need exact totals: the default arrangement totals $8,410 with Hotel Cost 1,050, and the total moves one for one with the Hotel Cost, so hotel_for(total) hits any total.
Not testable (they need the OEM to decide, and there is no OEM user): 'Rejected by OEM', the stage 'Ready for Client' and the status 'Approved'.

Run the Quotation UI and API suites one at a time: both ask the system for the next Quote # and can get the same suggestion.
"""
import re

import pytest

from framework_api.client.role_session import RoleApiSession
from framework_api.services.quotation_service import QuotationService
from shared.config.credentials import load_role_credentials
from framework_ui.pages.quotation.quotation_page import QuotationPage

pytestmark = pytest.mark.ui

REC = "Reviewed for the escalation tests."
OEM = "Workflow Progress Test OEM"          # the OEM Name of every test quotation: who the list says is waiting on the OEM
FPM, BU, CEO = "QA Jhe FPM", "QA Jhe BU", "QA Jhe CEO"
D_FPM, D_BU, D_CEO = "QA Default FPM", "QA Default BU", "QA Default CEO"
DATE = re.compile(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}")


def hotel_for(total):
    return {"hotelCost": 1050 + (total - 8410)}


# ------------------------------------------------------------------------------------------------ reading the screen
def parse_row(text):
    """The AM's list row -> {'waiting': name, 'role': 'FPM_FSM'..., 'step': 'BU Reviewing', 'status': 'Submitted'}."""
    lines = [l.strip() for l in text.split("\n") if l.strip()]
    site = lines.index("Valle Verde")
    role = lines[site + 2].lstrip("· ").strip() if lines[site + 2].startswith("·") else ""
    return {"waiting": lines[site + 1], "role": role, "step": lines[-4], "status": lines[-2]}


def am_row(role_page, title):
    """The AM's row of the quotation. The list can take a few seconds to paint after a refresh, so it retries before giving up."""
    for attempt in range(4):
        qp = QuotationPage(role_page("AM")).open(refresh=True)
        qp.page.wait_for_timeout(2000 + 2000 * attempt)
        text = qp.row_text(title)
        if "Valle Verde" in text:
            return parse_row(text)
    return parse_row(text)


def has_it(role_page, role, title):
    """True when the quotation is in the Pending approval list of that approver (retries: the list can take a few seconds to paint)."""
    for attempt in range(3):
        page = QuotationPage(role_page(role)).open(refresh=True).page
        page.wait_for_timeout(2000 + 2000 * attempt)
        if title in page.locator("body").inner_text():
            return True
    return False


def history_text(role_page, title):
    page = role_page("AM")
    qp = QuotationPage(page).open(refresh=True)
    page.wait_for_timeout(1500)
    qp.open_workflow_history(title)
    text = " | ".join(t.strip() for t in qp.workflow_history_text().split("\n") if t.strip())
    page.keyboard.press("Escape")
    page.wait_for_timeout(500)
    return text


def signers_text(role_page, qid):
    """The 'Approved Personnel Settings' window of the quotation, opened by the AM: the route as the system has it."""
    page = QuotationPage(role_page("AM")).open_by_link(qid).page
    page.get_by_role("button", name="Setup Approval Progress").first.click()
    modal = page.locator("div.fixed.inset-0").last
    modal.get_by_text(re.compile("approved personnel settings", re.I)).wait_for(timeout=10000)
    text = " ".join(modal.inner_text().split())
    modal.get_by_role("button", name="Close").first.click()
    page.wait_for_timeout(500)
    return text


def diagram(role_page, qid):
    """The Workflow Progress diagram: the 'Current step' text, which nodes carry the current-step glow and how many elements are drawn in red."""
    page = QuotationPage(role_page("AM")).open_by_link(qid).page
    wp = QuotationPage(page).workflow_progress()
    wp.open()
    page.wait_for_timeout(800)
    info = {"current": wp.current_step_text(), "glow": [n for n in ("Manual Creation", "WO Quoting", "BU Review", "OEM Review") if wp.is_node_current(n)],
            "red": wp.svg().evaluate("s => Array.from(s.querySelectorAll('*')).filter(e => { const m = getComputedStyle(e).stroke.match(/rgb\\((\\d+), (\\d+), (\\d+)\\)/); return m && +m[1] > 200 && +m[2] < 130 && +m[3] < 150; }).length")}
    wp.close()
    return info


def title_of(quotation_api, qid):
    return quotation_api["AM"].client.get(f"/api/quotations/{qid}").json()["title"]


def snap(role_page, qid, title, lists=(), signers=False, history=False, diag=False):
    s = {"row": am_row(role_page, title), "lists": {role: has_it(role_page, role, title) for role in lists}}
    if signers:
        s["signers"] = signers_text(role_page, qid)
    if history:
        s["history"] = history_text(role_page, title)
    if diag:
        s["diagram"] = diagram(role_page, qid)
    return s


@pytest.fixture(scope="module")
def default_api():
    sessions = {}
    for role in ("FPM", "BU", "CEO"):
        creds = load_role_credentials(f"DEFAULT_{role}")
        if creds is None:
            pytest.skip(f"QUOTATION_DEFAULT_{role}_* not set in .env")
        sessions[role] = QuotationService(RoleApiSession(creds["email"], creds["password"]))
    return sessions


def ok(r):
    assert r.status_code == 200, f"{r.status_code} {r.text[:200]}"


def create(make_quotation, quotation_api, tag, route, total=None):
    qid, quote = make_quotation(tag, route, arrangement=hotel_for(total) if total else None, title_prefix="HU21")
    return qid, title_of(quotation_api, qid)


# ================================================================================================ the full path: FPM/FSM -> BU -> CEO -> OEM
@pytest.fixture(scope="module")
def path(role_page, make_quotation, quotation_api):
    qid, title = create(make_quotation, quotation_api, "PATH", ["FPM", "BU", "CEO"])
    s = {"id": qid, "title": title}
    s["submitted"] = snap(role_page, qid, title, lists=("FPM", "BU", "CEO"), signers=True)
    ok(quotation_api["FPM"].approve(qid, REC))
    s["returned"] = snap(role_page, qid, title, lists=("FPM", "BU", "CEO"), diag=True)
    ok(quotation_api["AM"].submit(qid))
    s["bu_turn"] = snap(role_page, qid, title, lists=("FPM", "BU", "CEO"), history=True)
    ok(quotation_api["BU"].approve(qid, REC))
    s["ceo_turn"] = snap(role_page, qid, title, lists=("FPM", "BU", "CEO"))
    ok(quotation_api["CEO"].approve(qid, REC))
    s["oem"] = snap(role_page, qid, title, lists=("FPM", "BU", "CEO"), history=True, diag=True)
    return s


def test_the_fpm_fsm_gets_the_quotation_first_and_nobody_else_yet(path):
    """Qase HU21-RT1 -- route FPM/FSM, BU and CEO: after the AM submits, only the FPM/FSM has it."""
    s = path["submitted"]
    assert s["row"]["waiting"] == FPM and s["row"]["role"] == "FPM/FSM", s["row"]
    assert s["lists"] == {"FPM": True, "BU": False, "CEO": False}, s["lists"]


def test_after_the_fpm_fsm_and_the_new_submit_the_bu_has_it_and_the_ceo_does_not(path):
    """Qase HU21-RT3 / RT6 -- only one approver at a time: the BU has it, the CEO and the FPM/FSM do not."""
    s = path["bu_turn"]
    assert s["row"]["waiting"] == BU and s["row"]["role"] == "BU", s["row"]
    assert s["lists"] == {"FPM": False, "BU": True, "CEO": False}, s["lists"]


def test_after_the_bu_approves_the_ceo_has_it(path):
    """Qase HU21-RT4"""
    s = path["ceo_turn"]
    assert s["row"]["waiting"] == CEO and s["row"]["role"] == "CEO", s["row"]
    assert s["lists"] == {"FPM": False, "BU": False, "CEO": True}, s["lists"]


# ================================================================================================ route order and levels
@pytest.fixture(scope="module")
def wrong_order(role_page, make_quotation, quotation_api):
    qid, title = create(make_quotation, quotation_api, "WORD", ["BU", "FPM"])          # the AM added the BU first and the FPM/FSM second
    return {"id": qid, "title": title, "submitted": snap(role_page, qid, title, lists=("FPM", "BU"), signers=True)}


def test_the_levels_keep_their_order_even_if_the_am_added_the_bu_first(wrong_order):
    """Qase HU21-RT2 -- the BU was added before the FPM/FSM: the FPM/FSM still gets it first."""
    s = wrong_order["submitted"]
    assert s["row"]["waiting"] == FPM and s["lists"] == {"FPM": True, "BU": False}, s


@pytest.fixture(scope="module")
def bu_only(role_page, make_quotation, quotation_api):
    qid, title = create(make_quotation, quotation_api, "BUONLY", ["BU"])
    return {"id": qid, "title": title, "submitted": snap(role_page, qid, title, lists=("FPM", "BU"), signers=True)}


def test_without_a_fpm_fsm_the_quotation_goes_straight_to_the_next_level(bu_only):
    """Qase HU21-RT5 -- route with only the BU: the BU has it at once and nobody is added in front of it."""
    s = bu_only["submitted"]
    assert s["row"]["waiting"] == BU and s["lists"]["BU"] is True, s
    assert D_FPM not in s["signers"] and FPM not in s["signers"], s["signers"]


@pytest.fixture(scope="module")
def same_level(role_page, make_quotation, quotation_api, api_roles, default_api):
    """Two BU approvers at the same level, added in this order: QA Jhe BU, then QA Default BU."""
    sess = api_roles["AM"]
    default_bu = RoleApiSession(**load_role_credentials("DEFAULT_BU"))
    approvers = [{"workflowStage": "", "order": 0, "role": "BU", "userId": api_roles["BU"].user_id, "userName": BU, "email": api_roles["BU"].email, "status": "Pending", "isAutoAssigned": False},
                 {"workflowStage": "", "order": 1, "role": "BU", "userId": default_bu.user_id, "userName": D_BU, "email": default_bu.email, "status": "Pending", "isAutoAssigned": False}]
    from framework_api.services import quotation_setup as qs
    qid, _ = qs.create_and_submit(sess, api_roles, "SAMELVL", ["BU"], title_prefix="HU21", extra={"approvers": approvers})
    title = title_of(quotation_api, qid)
    s = {"id": qid, "title": title, "first": snap(role_page, qid, title)}
    ok(quotation_api["BU"].approve(qid, REC))
    s["second"] = snap(role_page, qid, title)
    return s


def test_approvers_of_the_same_level_review_in_the_order_the_am_added_them(same_level):
    """Qase HU21-RT7 -- two BU approvers: the first one added reviews first, the second one only after."""
    assert same_level["first"]["row"]["waiting"] == BU, same_level["first"]
    assert same_level["second"]["row"]["waiting"] == D_BU, same_level["second"]


# ================================================================================================ the amount rule
AMOUNTS = {"99999": 99999, "100000": 100000, "499999": 499999, "500000": 500000, "500001": 500001}


@pytest.fixture(scope="module")
def amount(role_page, make_quotation, quotation_api, default_api):
    """For each limit: route FPM/FSM only; after the first submit the route as the window shows it; then the FPM/FSM approves, the AM submits again and the row shows who has it."""
    out = {}
    for name, total in AMOUNTS.items():
        qid, title = create(make_quotation, quotation_api, f"AMT{name}", ["FPM"], total)
        s = {"id": qid, "title": title, "total": quotation_api["AM"].client.get(f"/api/quotations/{qid}").json()["totalAmount"]}
        s["route"] = signers_text(role_page, qid)
        ok(quotation_api["FPM"].approve(qid, REC))
        ok(quotation_api["AM"].submit(qid))
        s["next"] = snap(role_page, qid, title)
        if total > 500000:
            ok(default_api["CEO"].approve(qid, REC))
            s["after_ceo"] = snap(role_page, qid, title)
            s["route_after"] = signers_text(role_page, qid)
        out[name] = s
    return out


def test_below_100000_no_level_is_added_and_the_quotation_goes_to_the_oem_review(amount):
    """Qase HU21-AM1 -- $99,999"""
    s = amount["99999"]
    assert s["total"] == 99999 and D_BU not in s["route"] and D_CEO not in s["route"], s["route"]
    assert s["next"]["row"]["waiting"] == OEM and s["next"]["row"]["step"] == "OEM Review", s["next"]


def test_exactly_100000_already_requires_a_bu(amount):
    """Qase HU21-AM2 -- $100,000: the default BU is added after the FPM/FSM and has the quotation next."""
    s = amount["100000"]
    assert s["total"] == 100000 and D_BU in s["route"] and D_CEO not in s["route"], s["route"]
    assert s["next"]["row"]["waiting"] == D_BU and s["next"]["row"]["role"] == "BU", s["next"]


def test_just_below_500000_a_bu_is_required_and_a_ceo_is_not(amount):
    """Qase HU21-AM3 -- $499,999"""
    s = amount["499999"]
    assert D_BU in s["route"] and D_CEO not in s["route"], s["route"]
    assert s["next"]["row"]["waiting"] == D_BU, s["next"]


def test_exactly_500000_still_requires_only_a_bu(amount):
    """Qase HU21-AM4 -- $500,000 exactly: the default BU is added and has the quotation next; no CEO (the CEO starts at $500,001, OP-112 fix)."""
    s = amount["500000"]
    assert s["total"] == 500000 and D_BU in s["route"] and D_CEO not in s["route"], s["route"]
    assert s["next"]["row"]["waiting"] == D_BU and s["next"]["row"]["role"] == "BU", s["next"]


def test_above_500000_a_ceo_is_required_and_the_bu_is_not_added(amount):
    """Qase HU21-AM5 -- $500,001"""
    s = amount["500001"]
    assert D_CEO in s["route"] and D_BU not in s["route"], s["route"]
    assert s["next"]["row"]["waiting"] == D_CEO and s["after_ceo"]["row"]["waiting"] == OEM, s


@pytest.fixture(scope="module")
def no_approver(role_page, make_quotation, quotation_api):
    q1, t1 = create(make_quotation, quotation_api, "NOAPP", [])
    q2, t2 = create(make_quotation, quotation_api, "NOAPP150", [], 150000)
    return {"small": snap(role_page, q1, t1, signers=True), "big": snap(role_page, q2, t2, signers=True)}


def test_with_no_approver_below_100000_the_default_fpm_fsm_is_added(no_approver):
    """Qase HU21-AM6"""
    s = no_approver["small"]
    assert s["row"]["waiting"] == D_FPM and s["row"]["role"] == "FPM/FSM", s["row"]
    assert D_FPM in s["signers"]


def test_with_no_approver_from_100000_only_the_bu_is_added(no_approver):
    """Qase HU21-AM7 -- the default FPM/FSM is added only when the route has no approver at all and the amount is below $100,000."""
    s = no_approver["big"]
    assert s["row"]["waiting"] == D_BU and D_BU in s["signers"] and D_FPM not in s["signers"], s


@pytest.fixture(scope="module")
def big_with_bu(role_page, make_quotation, quotation_api, default_api):
    qid, title = create(make_quotation, quotation_api, "BIGBU", ["FPM", "BU"], 600000)
    s = {"route": signers_text(role_page, qid)}
    ok(quotation_api["FPM"].approve(qid, REC))
    ok(quotation_api["AM"].submit(qid))
    s["bu_turn"] = snap(role_page, qid, title)
    ok(quotation_api["BU"].approve(qid, REC))
    s["ceo_turn"] = snap(role_page, qid, title)
    return s


def test_at_600000_with_a_bu_added_by_the_am_the_ceo_is_added_and_the_bu_stays(big_with_bu):
    """Qase HU21-AM8 -- the BU reviews because the AM added it, then the CEO."""
    s = big_with_bu
    assert BU in s["route"] and D_CEO in s["route"], s["route"]
    assert s["bu_turn"]["row"]["waiting"] == BU and s["ceo_turn"]["row"]["waiting"] == D_CEO, s


@pytest.fixture(scope="module")
def required_already(role_page, make_quotation, quotation_api):
    q1, _ = create(make_quotation, quotation_api, "REQ150", ["FPM", "BU"], 150000)
    q2, _ = create(make_quotation, quotation_api, "KEEPSMALL", ["FPM", "BU"])
    return {"bu_at_150000": signers_text(role_page, q1), "bu_below_100000": signers_text(role_page, q2)}


def test_a_required_level_that_is_already_in_the_route_is_not_added_again(required_already):
    """Qase HU21-AM9 -- $150,000 with the BU chosen by the AM: no second, default BU."""
    route = required_already["bu_at_150000"]
    assert BU in route and D_BU not in route, route


def test_the_system_never_removes_an_approver_the_am_added(required_already):
    """Qase HU21-AM10 -- a BU added by the AM on a quotation below $100,000 stays in the route."""
    route = required_already["bu_below_100000"]
    assert FPM in route and BU in route, route


# ================================================================================================ stages and statuses
@pytest.fixture(scope="module")
def a_draft(role_page, make_draft, quotation_api):
    qid, _ = make_draft("STDRAFT", title_prefix="HU21")
    return am_row(role_page, title_of(quotation_api, qid))


def test_a_draft_shows_the_status_draft(a_draft):
    """Qase HU21-ST1"""
    assert a_draft["status"] == "Draft", a_draft


def test_after_the_fpm_fsm_approves_the_status_is_returned(path):
    """Qase HU21-ST2"""
    assert path["returned"]["row"]["status"] == "Returned", path["returned"]["row"]


def test_a_quotation_in_review_shows_the_status_submitted_and_the_stage_bu_review(path):
    """Qase HU21-ST3"""
    row = path["submitted"]["row"]
    assert row["status"] == "Submitted" and row["step"] == "BU Review", row


def test_in_the_oem_review_the_status_is_still_submitted(path):
    """Qase HU21-ST4 -- 'While the quotation is in review, including OEM Review, the status shows as Submitted.'"""
    row = path["oem"]["row"]
    assert row["status"] == "Submitted" and row["step"] == "OEM Review", row


@pytest.mark.parametrize("state", ["draft", "returned"])
def test_the_list_shows_the_stage_wo_quoting_while_the_quotation_is_with_the_am(a_draft, path, state):
    """Qase HU21-ST5 (Draft), ST6 (Returned) -- the stage is written 'WO Quoting'."""
    row = a_draft if state == "draft" else path["returned"]["row"]
    assert row["step"] == "WO Quoting", row


def test_the_list_shows_the_stage_wo_quoting_for_a_rejected_quotation(rejected):
    """Qase HU21-ST7 -- a quotation rejected by an internal level is with the AM: the stage is written 'WO Quoting'."""
    assert rejected["rejected"]["row"]["step"] == "WO Quoting", rejected["rejected"]["row"]


def test_the_workflow_shows_the_current_stage_of_each_step(path):
    """Qase HU21-ST8 -- the diagram marks WO Quoting when it is with the AM and OEM Review when it waits on the OEM (BU Review in between, with the diagram's own node names)."""
    assert path["returned"]["diagram"]["glow"] == ["WO Quoting"] and path["returned"]["diagram"]["red"] == 0, path["returned"]["diagram"]
    assert path["oem"]["diagram"]["glow"] == ["OEM Review"], path["oem"]["diagram"]


def test_internal_approvals_never_mark_the_quotation_as_approved(path):
    """Qase HU21-ST9 -- after the FPM/FSM, the BU and the CEO approved, the status is not Approved and the stage is not Ready for Client."""
    row = path["oem"]["row"]
    assert row["status"] != "Approved" and row["step"] != "Ready for Client", row


# ================================================================================================ level 1 (FPM/FSM) and next levels
@pytest.fixture(scope="module")
def fpm_only(role_page, make_quotation, quotation_api):
    qid, title = create(make_quotation, quotation_api, "FPMONLY", ["FPM"])
    ok(quotation_api["FPM"].approve(qid, REC))
    s = {"returned": snap(role_page, qid, title, diag=True)}
    ok(quotation_api["AM"].submit(qid))
    s["resubmitted"] = snap(role_page, qid, title, history=True)
    return s


def test_when_the_fpm_fsm_is_the_only_approver_the_quotation_still_goes_back_to_the_am(fpm_only):
    """Qase HU21-L1 -- FPM/FSM alone in the route: Returned, with the AM, and the workflow on WO Quoting."""
    s = fpm_only["returned"]
    assert s["row"]["status"] == "Returned" and s["row"]["waiting"] == "Jherico Ascencio" and s["row"]["role"] == "AM", s["row"]
    assert s["diagram"]["glow"] == ["WO Quoting"], s["diagram"]


def test_when_the_am_submits_again_after_the_only_fpm_fsm_it_waits_on_the_oem(fpm_only):
    """Qase HU21-L2 -- no internal approver is left: the stage is OEM Review."""
    row = fpm_only["resubmitted"]["row"]
    assert row["step"] == "OEM Review" and row["status"] == "Submitted" and row["waiting"] == OEM, row


def test_the_fpm_fsm_approval_is_kept_after_the_am_submits_again(path):
    """Qase HU21-L3 -- the history still shows the FPM/FSM approval when the BU has the quotation."""
    history = path["bu_turn"]["history"]
    assert re.search(rf"{FPM} \| FPM/FSM \| Approved", history), history


def test_the_quotation_stays_in_review_when_no_internal_approver_is_left(path):
    """Qase HU21-NX1 -- after the CEO, the quotation waits on the OEM and the workflow marks OEM Review."""
    s = path["oem"]
    assert s["row"]["waiting"] == OEM and s["diagram"]["glow"] == ["OEM Review"], s
    assert s["lists"] == {"FPM": False, "BU": False, "CEO": False}, s["lists"]


# ================================================================================================ rejection by an internal level
def drive_to(level, make_quotation, quotation_api, tag):
    """Creates a FPM/FSM, BU, CEO route and brings the quotation to the turn of `level` ('FPM', 'BU' or 'CEO')."""
    qid, title = create(make_quotation, quotation_api, tag, ["FPM", "BU", "CEO"])
    if level in ("BU", "CEO"):
        ok(quotation_api["FPM"].approve(qid, REC)); ok(quotation_api["AM"].submit(qid))
    if level == "CEO":
        ok(quotation_api["BU"].approve(qid, REC))
    return qid, title


@pytest.fixture(scope="module", params=["FPM", "BU", "CEO"])
def rejected(request, role_page, make_quotation, quotation_api):
    level = request.param
    qid, title = drive_to(level, make_quotation, quotation_api, f"REJ{level}")
    ok(quotation_api[level].reject(qid, f"{level} rejects it."))
    s = {"level": level, "id": qid, "title": title, "name": {"FPM": FPM, "BU": BU, "CEO": CEO}[level]}
    s["rejected"] = snap(role_page, qid, title, lists=("FPM", "BU", "CEO"), history=True, diag=True)
    ok(quotation_api["AM"].submit(qid))
    s["again"] = snap(role_page, qid, title, lists=("FPM", "BU", "CEO"), history=True)
    return s


def test_a_rejection_by_an_internal_level_sends_the_quotation_back_to_the_am(rejected):
    """Qase HU21-RJ1 (FPM/FSM), RJ2 (BU), RJ3 (CEO) -- status Rejected, with the AM, and the workflow on WO Quoting."""
    s = rejected["rejected"]
    assert s["row"]["status"] == "Rejected" and s["row"]["waiting"] == "Jherico Ascencio" and s["row"]["role"] == "AM", s["row"]


def test_the_levels_after_the_one_that_rejected_do_not_receive_the_quotation(rejected):
    """Qase HU21-RJ4 (FPM/FSM), RJ5 (BU), RJ6 (CEO) -- nobody has it in their Pending approval list."""
    assert rejected["rejected"]["lists"] == {"FPM": False, "BU": False, "CEO": False}, rejected["rejected"]["lists"]


def test_a_rejected_quotation_shows_the_red_return_in_the_workflow(rejected):
    """Qase HU21-RJ7 (FPM/FSM), RJ8 (BU), RJ9 (CEO) -- the mockup: WO Quoting drawn in red with the return arrow, not the blue current-step glow."""
    d = rejected["rejected"]["diagram"]
    assert d["red"] > 0 and d["glow"] == [], d


def test_when_the_am_submits_again_it_goes_back_to_the_approver_who_rejected_it(rejected):
    """Qase HU21-RJ10 (FPM/FSM), RJ11 (BU), RJ12 (CEO)"""
    s = rejected["again"]
    assert s["row"]["waiting"] == rejected["name"] and s["row"]["status"] == "Submitted", s["row"]
    assert [r for r, has in s["lists"].items() if has] == [rejected["level"]], s["lists"]


def test_the_earlier_approvals_are_kept_when_the_am_submits_again_after_a_rejection(rejected):
    """Qase HU21-RJ13 (FPM/FSM, nothing earlier), RJ14 (BU), RJ15 (CEO) -- the history still shows every earlier approval."""
    history = rejected["again"]["history"]
    if rejected["level"] in ("BU", "CEO"):
        assert re.search(rf"{FPM} \| FPM/FSM \| Approved", history), history
    if rejected["level"] == "CEO":
        assert re.search(rf"{BU} \| BU \| Approved", history), history
    assert "Rejected" in history, history


# ================================================================================================ submitting again after changes (the AM edits on the screen)
def edit_and_submit(role_page, title, fields):
    """The AM opens the Returned quotation from the list, changes fields of the FSE Arrangement and submits it again from the screen."""
    page = role_page("AM")
    qp = QuotationPage(page).open(refresh=True).open_listed_quotation(title)
    fse = qp.fse_arrangement()
    for (section, label), value in fields.items():
        fse.field(section, label).fill(str(value))
    page.wait_for_timeout(500)
    page.get_by_role("button", name="Submit Quotation", exact=True).click(force=True)
    page.get_by_text("WO Quoting", exact=True)
    page.wait_for_timeout(500)
    from playwright.sync_api import expect
    expect(page.get_by_text("WO Snapshot", exact=True)).to_have_count(0, timeout=25000)


LABOR = ("Labor Costs", "Labor Cost / Hour")
HOTEL = ("Onsite Support Costs", "Hotel Cost")


@pytest.fixture(scope="module")
def changes(role_page, make_quotation, quotation_api, default_api):
    out = {}
    # the amount goes up to $100,000 or more (labor 2,913 -> $100,026)
    qid, title = create(make_quotation, quotation_api, "CHG100", ["FPM"])
    ok(quotation_api["FPM"].approve(qid, REC))
    out["locked"] = signers_text(role_page, qid)
    edit_and_submit(role_page, title, {LABOR: 2913})
    out["to_bu"] = dict(snap(role_page, qid, title, history=True), total=quotation_api["AM"].client.get(f"/api/quotations/{qid}").json()["totalAmount"], route=signers_text(role_page, qid))
    # up to $500,000 or more (labor 18,537 -> $599,994)
    qid, title = create(make_quotation, quotation_api, "CHG500", ["FPM"])
    ok(quotation_api["FPM"].approve(qid, REC))
    edit_and_submit(role_page, title, {LABOR: 18537})
    out["to_ceo"] = dict(snap(role_page, qid, title), route=signers_text(role_page, qid))
    # down again: a BU was added at $150,000 and the amount drops to about $8,410
    qid, title = create(make_quotation, quotation_api, "CHGDOWN", ["FPM"], 150000)
    ok(quotation_api["FPM"].approve(qid, REC))
    edit_and_submit(role_page, title, {HOTEL: 1050})
    out["down"] = dict(snap(role_page, qid, title), total=quotation_api["AM"].client.get(f"/api/quotations/{qid}").json()["totalAmount"], route=signers_text(role_page, qid))
    return out


def test_after_the_first_decision_the_am_cannot_change_the_route_by_hand(changes):
    """Qase HU21-RC1 -- the window says 'Locked after the first approval decision' and offers no search or add control."""
    text = changes["locked"]
    assert "Locked after the first approval decision" in text, text
    assert "Search" not in text and "Add" not in text.replace("ADDED SIGNERS", ""), text


def test_the_am_can_change_the_amount_and_submit_again_and_a_missing_bu_is_added(changes):
    """Qase HU21-RC2 -- the amount edited on the screen is saved and, at $100,000 or more, the default BU is added and has the quotation."""
    s = changes["to_bu"]
    assert s["total"] >= 100000 and s["total"] < 500000, s["total"]
    assert D_BU in s["route"] and D_CEO not in s["route"], s["route"]
    assert s["row"]["waiting"] == D_BU and s["row"]["status"] == "Submitted", s["row"]


def test_the_fpm_fsm_approval_is_kept_when_a_level_is_added_after_a_change(changes):
    """Qase HU21-RC3"""
    assert re.search(rf"{FPM} \| FPM/FSM \| Approved", changes["to_bu"]["history"]), changes["to_bu"]["history"]


def test_a_new_amount_of_500000_or_more_adds_the_ceo_and_not_the_bu(changes):
    """Qase HU21-RC4"""
    s = changes["to_ceo"]
    assert D_CEO in s["route"] and D_BU not in s["route"], s["route"]
    assert s["row"]["waiting"] == D_CEO, s["row"]


def test_a_lower_amount_does_not_remove_a_level_that_was_added(changes):
    """Qase HU21-RC5 -- the BU added at $150,000 still reviews after the amount drops below $100,000."""
    s = changes["down"]
    assert s["total"] < 100000 and D_BU in s["route"], (s["total"], s["route"])
    assert s["row"]["waiting"] == D_BU, s["row"]


# ================================================================================================ traceability
def test_the_history_records_each_submit_with_the_person_the_date_and_the_outcome(path):
    """Qase HU21-TR1 -- the AM's first submit and the re-submit after the FPM/FSM."""
    h = path["oem"]["history"]
    assert re.search(r"Jherico Ascencio \| AM \| Submitted for review", h) and re.search(r"Jherico Ascencio \| AM \| Re-submitted for review", h), h
    assert len(DATE.findall(h)) >= 6, h


def test_the_history_records_each_approval_with_the_person_the_level_the_reason_and_the_date(path):
    """Qase HU21-TR2 -- FPM/FSM, BU and CEO: name, level, outcome, reason and date."""
    h = path["oem"]["history"]
    for name, level in ((FPM, "FPM/FSM"), (BU, "BU"), (CEO, "CEO")):
        assert re.search(rf"{name} \| {level} \| Approved \| {REC}", h), (name, h)


def test_the_history_records_a_rejection_with_the_person_the_level_the_reason_and_the_date(rejected):
    """Qase HU21-TR3 -- name, level, outcome and reason of the rejection."""
    h = rejected["again"]["history"]
    level = {"FPM": "FPM/FSM", "BU": "BU", "CEO": "CEO"}[rejected["level"]]
    assert re.search(rf"{rejected['name']} \| {level} \| Rejected \| {rejected['level']} rejects it\.", h), h


def test_the_history_shows_where_the_quotation_is_now(path):
    """Qase HU21-TR4 -- the panel marks the current stage (HERE, waiting on the OEM approval)."""
    h = path["oem"]["history"]
    assert "CURRENT PHASE | OEM Review" in h and "HERE" in h, h


# ================================================================================================ saving the decision
def test_when_the_decision_cannot_be_saved_the_user_sees_an_error_and_nothing_changes(role_page, make_quotation, quotation_api):
    """Qase HU21-SV1 -- the call that saves the decision fails: the error is shown and the quotation stays as it was (status Submitted, still waiting on the FPM/FSM)."""
    qid, title = create(make_quotation, quotation_api, "SAVEFAIL", ["FPM", "BU"])
    page = role_page("FPM")
    qp = QuotationPage(page).open(refresh=True).open_listed_quotation(title)
    bar = qp.decision_bar().wait_until_visible()
    bar.type_recommendation(REC)
    page.route("**/api/**", lambda route: route.abort() if route.request.method == "POST" else route.continue_())
    try:
        bar.approve_button().click()
        page.get_by_text("Could not save this decision.").wait_for(timeout=15000)
    finally:
        page.unroute("**/api/**")
    body = quotation_api["AM"].client.get(f"/api/quotations/{qid}").json()
    assert body["status"] == "Awaiting" and sorted((a["order"], a["status"]) for a in body["approvers"]) == [(0, "Pending"), (1, "Pending")], body["approvers"]
    bar.type_recommendation("")
