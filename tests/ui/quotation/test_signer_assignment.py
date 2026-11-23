"""Quotation module -- Setup Approval Progress / Signer assignment (OP-24 /
HU-16, Qase suite 46).

Cross-checked against Jira OP-24's own 10 Acceptance Criteria (HUsACC is
missing AC#9 entirely -- its own AC#9 text actually matches Jira's AC#10),
Quotation_Spec_bilingual_V13/V14 (documents 3 separate approver groups --
Quote/BU/OEM Approving Personnel -- and a signing-status audit table), and
the Sprint 1 Test Plan / Sprint Planning doc (HU-16 is Sprint 1 Week 3,
3 days, with an explicit "HU-16 -> HU-13: Submit validates the assigned
signers" dependency -- so the Submit-blocking behavior tested here is
squarely in this story's own scope, not a mix with another sprint).

Regression 2026-10-08 against the build after development's fixes. OP-24 was changed on 2026-10-05: AC #2
(approver groups with Name/Email and '+') was replaced by a general search bar, BU Manager / COO became BU Office /
CEO Office, and the audit-record AC was removed. The modal now shows a DEFAULT APPROVER FOR THIS AMOUNT block and
Submit adds the default approver (Approvers.EsAutoAsignado = 1). Still open: Qase defects #120 (pending Arbi), #122 and #142.
"""
import time

import pytest
from playwright.sync_api import expect

import framework_ui.pages.quotation.components.fse_arrangement_locators as fse_loc
from tests.ui.quotation.support import submit_a_full_quotation

from tests.ui.quotation.am_page import quotation_page  # noqa: F401  (runs as the AM, not the admin)

pytestmark = pytest.mark.ui


@pytest.fixture(autouse=True)
def _close_form_after_each_test(quotation_page):
    """Every test here leaves the WO Creation form open (either as a
    finished quotation or a still-open draft) -- without closing it, its
    "fixed inset-0 z-50 ..." overlay intercepts the next test's fixture-
    level click on the sidebar Quotation link (logged_in_page is
    session-scoped, so this leaks across tests otherwise)."""
    yield
    try:
        page = quotation_page.page
        page.keyboard.press("Escape")
        page.wait_for_timeout(300)
        close_btn = page.get_by_role("button", name="CLOSE", exact=True)
        if close_btn.count() > 0:
            close_btn.first.click()
            page.wait_for_timeout(500)
    except Exception:
        pass


def _set_total(quotation_page, labor_cost_per_hour):
    """Sets a clean, controlled quotation total via FSE Arrangement alone
    (Support Engineers=1, 8h/day, 1 day), without selecting a Customer/Site
    -- avoids OP-20's known Hotel Cost/Per Diem pre-fill defect (#113)
    polluting the total."""
    page = quotation_page.page
    page.get_by_role("button", name=fse_loc.TAB_FSE_ARRANGEMENT, exact=True).click()
    page.wait_for_timeout(500)
    fse = quotation_page.fse_arrangement()
    fse.field(fse_loc.SECTION_HEADING_STATEMENT, fse_loc.LABEL_SUPPORT_ENGINEERS).fill("1")
    fse.field(fse_loc.SECTION_HEADING_STATEMENT, fse_loc.LABEL_WORKING_HOUR_TECH_DAY).fill("8")
    fse.field(fse_loc.SECTION_HEADING_STATEMENT, fse_loc.LABEL_ESTIMATED_WORKING_DAYS).fill("1")
    fse.field(fse_loc.SECTION_HEADING_LABOR, fse_loc.LABEL_LABOR_COST_HOUR).fill(str(labor_cost_per_hour))
    page.wait_for_timeout(500)


# --- PASS: Qase #931 ---
def test_modal_opens_with_added_signers_panel(quotation_page):
    quotation_page.create_quotation()
    signers = quotation_page.signer_assignment().open()
    assert "ADDED SIGNERS" in signers.body_text()
    signers.close_without_saving()


@pytest.mark.skip(reason="OUT OF SCOPE OF HU-16 (decision of 2026-11-09, Qase case 932 deprecated): the directory search of the approver modal was discarded (OP-24 AC #2); only the default approver and the OEM contact remain.")
def test_directory_search_returns_match_with_autofilled_role_and_email(quotation_page):
    pass


@pytest.mark.skip(reason="OUT OF SCOPE OF HU-16 (decision of 2026-11-09, Qase case 933 deprecated): manual entry as a fallback of the directory search no longer exists; the OEM contact is the only manual entry.")
def test_no_match_falls_back_to_manual_entry(quotation_page):
    pass


# --- Qase #934: the OEM contact form (the only manual entry left since 2026-11-05) ---
def test_manual_entry_add_disabled_until_name_and_valid_email(quotation_page):
    quotation_page.create_quotation()
    signers = quotation_page.signer_assignment().open()
    add_btn = signers.add_button()
    expect(add_btn).to_be_disabled()

    signers.manual_name_field().fill("Zzz Validation Test Person")
    expect(add_btn).to_be_disabled()

    signers.manual_email_field().fill("not-an-email")
    expect(add_btn).to_be_disabled()

    signers.manual_email_field().fill("valid@example.com")
    expect(add_btn).to_be_enabled()
    signers.close_without_saving()


# --- Qase #935 ---
def test_remove_button_removes_a_signer(quotation_page):
    quotation_page.create_quotation()
    signers = quotation_page.signer_assignment().open()
    signers.add_manual("Zzz Remove Me", "remove.me@example.com")
    assert "Zzz Remove Me" in signers.body_text()

    signers.remove_button_for("Zzz Remove Me").click()
    quotation_page.page.wait_for_timeout(500)
    assert "No signers added yet." in signers.body_text()
    signers.close_without_saving()


# --- Qase #936: the same email is not added twice (OP-101, developer 2026-10-30: only the email is validated) ---
def test_duplicate_add_prevented_at_state_level(quotation_page):
    quotation_page.create_quotation()
    signers = quotation_page.signer_assignment().open()
    signers.add_manual("Zzz Duplicate", "duplicate@example.com")
    signers.manual_name_field().fill("Zzz Duplicate Again")
    signers.manual_email_field().fill("duplicate@example.com")
    add_btn = signers.add_button()
    if add_btn.count() and add_btn.is_enabled():
        add_btn.click()
        quotation_page.page.wait_for_timeout(500)
    added_rows = quotation_page.page.locator("div.fixed.inset-0").last.get_by_role("button", name="Remove", exact=True)
    assert added_rows.count() == 1
    signers.close_without_saving()


# --- Qase #937 ---
def test_close_discards_unsaved_changes(quotation_page):
    quotation_page.create_quotation()
    signers = quotation_page.signer_assignment().open()
    signers.add_manual("Zzz Discard Me", "discard.me@example.com")
    assert "Zzz Discard Me" in signers.body_text()

    signers.close_without_saving()
    signers.open()
    assert "No signers added yet." in signers.body_text()
    signers.close_without_saving()


# --- Qase #938 ---
def test_save_signers_persists_across_reopen(quotation_page):
    quotation_page.create_quotation()
    signers = quotation_page.signer_assignment().open()
    signers.add_manual("Zzz Persist Me", "persist.me@example.com")
    signers.save()

    signers.open()
    assert "Zzz Persist Me" in signers.body_text()
    signers.close_without_saving()


# --- Qase #939: the OEM contact fields tolerate special characters and very long input ---
def test_search_and_manual_fields_tolerate_special_characters_and_length(quotation_page):
    quotation_page.create_quotation()
    signers = quotation_page.signer_assignment().open()
    page = quotation_page.page
    name, email = signers.manual_name_field(), signers.manual_email_field()

    for payload in ["<script>alert(1)</script>", "' OR '1'='1", "\U0001F600 emoji", "A" * 300]:
        name.fill(payload)
        assert "Server Error" not in signers.body_text()

    huge = "A" * 10000
    name.evaluate(
        """(el, val) => {
            const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
            setter.call(el, val);
            el.dispatchEvent(new Event('input', { bubbles: true }));
        }""",
        huge,
    )
    page.wait_for_timeout(1000)
    assert "Server Error" not in signers.body_text()

    name.fill("<script>alert(1)</script>")
    email.fill("' OR '1'='1@example.com")
    assert "Server Error" not in signers.body_text()
    signers.close_without_saving()


# --- PASS: Qase #940 (defect #114 fixed) ---
def test_default_approver_follows_the_quotation_amount(quotation_page):
    """OP-24 AC #1/#3/#6: the modal shows, before submitting, the approver the system assigns for the amount:
    below $100,000 the default approver (FPM/FSM), from $100,000 to $500,000 the BU Office,
    above $500,000 the CEO Office. Qase defect #114 fixed (verified 2026-10-08)."""
    quotation_page.create_quotation()
    expected = [(100, "FPM/FSM"), (30000, "BU"), (70000, "CEO")]
    for labor_cost, role in expected:
        _set_total(quotation_page, labor_cost)
        signers = quotation_page.signer_assignment().open()
        text = signers.default_approver_text()
        assert text.split()[-1] == role, f"labor {labor_cost}: expected the {role} badge in the default approver, got: {text!r}"
        signers.close_without_saving()


# --- Qase #960: approval thresholds at their limits (Test Plan: "approval thresholds at $100,000 and $500,000") ---
_LIMIT_CASES = [
    pytest.param(12499, "$99.992", "FPM/FSM", id="just-below-100k"),
    pytest.param(12500, "$100.000", "BU", id="exactly-100k"),
    pytest.param(62499, "$499.992", "BU", id="just-below-500k"),
    pytest.param(62500, "$500.000", "BU", id="exactly-500k"),   # Qase #142 / OP-112: fixed (verified 2026-11-09)
    pytest.param(62501, "$500.008", "CEO", id="just-above-500k"),
]


@pytest.mark.parametrize("labor_cost, total, role", _LIMIT_CASES)
def test_default_approver_at_the_threshold_limits(quotation_page, labor_cost, total, role):
    """OP-24 AC #3 / V13 AC-2.7.5: below $100,000 no BU approver; from $100,000 up to $500,000 the BU Office; above
    $500,000 the CEO Office. Total = labor cost x 8 h x 1 engineer x 1 day (no Site selected, so nothing is pre-filled)."""
    quotation_page.create_quotation()
    _set_total(quotation_page, labor_cost)
    assert quotation_page.fse_arrangement().total_text() == total
    signers = quotation_page.signer_assignment().open()
    text = signers.default_approver_text()
    assert text.split()[-1] == role, f"total {total}: expected the {role} badge as default approver, got: {text!r}"
    signers.close_without_saving()


@pytest.mark.skip(reason="OUT OF SCOPE OF HU-16 (decision of 2026-11-09, Qase case 959 deprecated): the general search bar of the approver modal was discarded (OP-24 AC #2).")
def test_general_search_bar_finds_by_name_email_and_business_unit(quotation_page):
    pass


@pytest.mark.skip(reason="OUT OF SCOPE OF HU-16 (decision of 2026-11-09, Qase case 942 deprecated): BU Office and CEO Office are only the default approvers by amount; they are no longer searched or assigned by hand (OP-24 AC #4 discarded).")
def test_bu_office_and_ceo_office_are_searchable_directory_roles(quotation_page):
    pass


# --- PASS: Qase #943 (defect #117 fixed) ---
def test_submit_with_no_added_signers_routes_to_the_default_approver(quotation_page, db_conn):
    """OP-24 AC #5: if the AM adds no approver and presses Submit, the quotation is routed to the default next
    approver. The 'Save without approver' bypass is gone: the saved quotation has the system-assigned approver
    (Approvers.EsAutoAsignado = 1) and is never left without one."""
    from shared.datasource.quotation_db_source import get_approvers_by_quote_no
    quotation_page.open(refresh=True)   # a clean landing: the tests before leave the form of their own quotation open
    quote_no = submit_a_full_quotation(quotation_page, f"HU16-NOSIGNER-{int(time.time())}", labor_cost=100)   # a unique title: the system refuses a quotation equal to an existing one
    approvers = get_approvers_by_quote_no(db_conn, quote_no)
    assert approvers, "a submitted quotation must have at least one approver"
    assert all(a["EsAutoAsignado"] == 1 for a in approvers)


@pytest.mark.skip(reason="OUT OF SCOPE OF HU-16 (decision of 2026-11-09, Qase case 944 deprecated): the authorization level of the signer is no longer validated; the approvers are the defaults for the amount (developer, 2026-11-09).")
def test_high_amount_with_a_low_level_signer_also_gets_the_required_approver(quotation_page, db_conn):
    pass


# --- OPEN: Qase #946, defect #120 ---
@pytest.mark.xfail(
    strict=True,
    reason="OPEN DEFECT (Qase #946, defect #120): the manual-entry panel's own copy says an external, role-less "
           "signer is added 'One at a time only', but a second such entry can be added right after the first "
           "with the Add button never blocked (re-verified 2026-10-08).",
)
def test_only_one_manual_external_signer_can_exist_at_a_time(quotation_page):
    quotation_page.create_quotation()
    signers = quotation_page.signer_assignment().open()

    signers.add_manual("Zzz First Manual", "first@example.com")

    signers.manual_name_field().fill("Zzz Second Manual")
    signers.manual_email_field().fill("second@example.com")
    quotation_page.page.wait_for_timeout(700)
    add_btn = signers.add_button()
    assert add_btn.is_disabled() or add_btn.count() == 0, (
        "a 2nd manual/external entry should be blocked while one already exists"
    )


# --- PASS: Qase #947 (defect #121 no longer reproduces) ---
def test_manual_entry_email_removes_emoji_so_only_a_valid_email_can_be_added(quotation_page):
    """V13 AC-2.7.9: a valid email address is required for every added approver. Retested 2026-10-08: the email field
    removes emoji (typed, filled or pasted), so what is added is a valid email."""
    quotation_page.create_quotation()
    signers = quotation_page.signer_assignment().open()
    signers.manual_name_field().fill("Zzz Emoji Email Test")
    email = signers.manual_email_field()
    for value in ["😀emoji@example.com", "jua😀n@example.com", "juan@example.com😀"]:
        email.fill(value)
        kept = email.input_value()
        assert all(ord(ch) < 0x1F000 for ch in kept), f"the emoji must be removed, the field keeps {kept!r}"
        assert "@" in kept and "." in kept.split("@")[-1]
        expect(signers.add_button()).to_be_enabled()


# --- OPEN: Qase #948, defect #122 ---
# Qase #948 / defect #122: fixed (verified 2026-11-09, the Add button stays disabled with 10,000+ characters)
def test_maxlength_limits_are_enforced_by_the_application_not_just_html(quotation_page):
    quotation_page.create_quotation()
    signers = quotation_page.signer_assignment().open()
    page = quotation_page.page

    huge_name = "N" * 10000
    huge_email = "e" * 10000 + "@example.com"
    for field, value in [(signers.manual_name_field(), huge_name), (signers.manual_email_field(), huge_email)]:
        field.evaluate(
            """(el, val) => {
                const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
                setter.call(el, val);
                el.dispatchEvent(new Event('input', { bubbles: true }));
            }""",
            value,
        )
    page.wait_for_timeout(500)

    assert not signers.add_button().is_enabled(), (
        "the application should reject an oversized name/email instead of allowing it to be added"
    )


# --- PASS: Qase defect #123 (fixed; verified 2026-10-12) ---
def test_waiting_on_column_truncates_a_very_long_approver_name_inside_its_cell(quotation_page):
    """A manual approver name of 200 characters (the maximum the field allows) must not break the "Quotes in
    Progress" row: the WAITING ON cell shortens it with an ellipsis and the text stays inside its own column."""
    name = "Zzz" + "N" * 197

    def add_long_named_signer():
        signers = quotation_page.signer_assignment().open()
        signers.add_manual(name, "long.name.signer@example.com")
        signers.save()

    wo_number = f"HU16-LONGNAME-{int(time.time())}"
    submit_a_full_quotation(quotation_page, wo_number, before_submit=add_long_named_signer)
    page = quotation_page.page
    page.wait_for_timeout(3000)
    geometry = page.evaluate(
        """(name) => {
            const cell = [...document.querySelectorAll('*')].find(e => e.children.length === 0 && e.textContent.trim() === name);
            if (!cell) return null;
            const box = cell.getBoundingClientRect();
            const style = getComputedStyle(cell);
            let next = null;
            for (const e of document.querySelectorAll('*')) {
                if (e.children.length === 0 && e.textContent.trim() && e !== cell) {
                    const b = e.getBoundingClientRect();
                    if (b.top < box.bottom && b.bottom > box.top && b.left >= box.right - 1 && (next === null || b.left < next)) next = b.left;
                }
            }
            return {right: box.right, nextLeft: next, textOverflow: style.textOverflow, truncated: cell.scrollWidth > cell.clientWidth};
        }""",
        name,
    )
    assert geometry, "the pending approver's name should be listed in the WAITING ON column"
    assert geometry["textOverflow"] == "ellipsis" and geometry["truncated"], f"the long name should be shortened: {geometry}"
    assert geometry["nextLeft"] is None or geometry["right"] <= geometry["nextLeft"], (
        f"the name overlaps the next column: {geometry}"
    )
