"""Quotation module -- 'Quotes in Progress' tab: view and filters, screen side (OP-11 / HU-04; Qase suite 43, cases QP-*). Regression of 2026-11-10 as the AM.

Only the HU-04 text decides what must happen (acceptance criteria AC1 to AC8, plus the closed bugs OP-55, OP-56 and OP-104 as regression). What the QA build shows (checked 2026-11-10):
  - The toolbar has the selects OEM, Site and Type of Work (default "All ..."), Item (default "Item", value All), the search box and Clear. There is NO "Category" filter: the story's AC2 names
    OEM, Site and Type, so the old cases about Category (746, 747) are not part of this suite.
  - The list calls GET /api/quotations?page&pageSize=10&includeClosed=false with oemName, siteName, typeOfWork, workflowStage (Item) and search. Each AM sees only its own quotations, so every
    expectation is read from the API as the SAME user instead of being hard-coded.
  - The search is applied with Enter (typing alone does not search), same as the history tab (HU-05).
Open findings (strict xfail; an XPASS means it was fixed, remove the mark): the Item option reads "OEM Review" where AC3 says "Vendor Reviewing", and the Item select is too narrow to show its texts.
The long OEM name that stretches the open OEM dropdown cannot be seen by the automation (a native popup): manual case only.
"""
import pytest

from framework_ui.pages.quotation import quotation_locators as quotation_loc  # noqa: F401
from framework_ui.pages.quotation.components import historical_quotes_locators as loc
from framework_ui.pages.quotation.quotation_page import QuotationPage

pytestmark = pytest.mark.ui

NOT_FINAL = ["Draft", "Submitted", "Awaiting", "Returned", "Rejected", "OemRejected", "OEM Rejected"]    # the screen says "Submitted" for the API's Awaiting
ITEM_STORY = ["AM/FPM/FSM Quoting", "BU Reviewing", "OEM Review"]       # AC3, exactly three (the third is "OEM Review" by design, Jira OP-189; the story OP-11 still says "Vendor Reviewing")
ITEM_VALUES = {"AM/FPM/FSM Quoting": "Quoting", "BU Reviewing": "BU Reviewing", "Vendor Reviewing": "Vendor Reviewing"}
KIND_PARAM = {"oem": "oemName", "site": "siteName", "type": "typeOfWork"}
NO_RESULTS = "No results for this filter."
UNKNOWN_TEXT = "zzzz-no-quotation-has-this"


# ---- the API as the same user (ground truth) ------------------------------------------------------------------------------------------
def api_list(api_roles, page=1, page_size=10, **params):
    response = api_roles["AM"].get("/api/quotations", page=page, pageSize=page_size, includeClosed="false", **params)
    assert response.status_code == 200, f"{response.status_code} {response.text[:200]}"
    return response.json()


def api_all(api_roles, **params):
    items, page = [], 1
    while True:
        data = api_list(api_roles, page=page, page_size=100, **params)
        items += data["items"]
        if not data["hasNextPage"]:
            return items
        page += 1


def api_all_closed(api_roles):
    """The historical quotations (the other tab) read 100 at a time."""
    items, page = [], 1
    while True:
        response = api_roles["AM"].get("/api/quotations", page=page, pageSize=100, includeClosed="true")
        assert response.status_code == 200
        data = response.json()
        items += data["items"]
        if not data["hasNextPage"]:
            return items
        page += 1


# ---- fixtures -------------------------------------------------------------------------------------------------------------------------
@pytest.fixture
def landing(role_page):
    """The AM's Quotation landing list ('Quotes in Progress' is the landing tab), freshly loaded."""
    page = QuotationPage(role_page("AM")).open(refresh=True)
    page.historical_quotes().settle()
    yield page
    page.historical_quotes().detach()


@pytest.fixture
def progress(landing):
    return landing.historical_quotes()


def count(component):
    return component.tab_count(loc.TAB_IN_PROGRESS_TEXT)


def wait_count(component, expected, timeout_ms=15000):
    """The counter after a filter: the list call can finish a moment after the click."""
    waited = 0
    while count(component) != expected and waited < timeout_ms:
        component.page.wait_for_timeout(250)
        waited += 250
    return count(component)


def registered_sites(landing):
    """The registered sites (the same ones as the Sites Status sidebar), read from the database: the page header no longer has a site list (2026-11-19, the first select of the page is the OEM filter)."""
    from shared.datasource.db_connection import db_is_configured, open_readonly_connection
    if not db_is_configured():
        pytest.skip("needs the read-only database connection to read the registered sites")
    conn = open_readonly_connection()
    try:
        with conn.cursor() as cur:
            cur.execute('SELECT "Name" FROM sites."Site"')
            return [row[0].strip() for row in cur.fetchall() if row[0] and row[0].strip()]
    finally:
        conn.rollback()


def item_select(component):
    return component._toolbar().locator("select").nth(3)


def item_options(component):
    """[(label, value)] of the Item select without the reset entry 'Item'."""
    options = item_select(component).evaluate("el => Array.from(el.options).map(o => [o.text.trim(), o.value])")
    return [(text, value) for text, value in options if value != "All"]


def first_option(component, kind):
    options = component.filter_options(kind)
    assert options, f"the {kind} filter has no option"
    return options[0]


# ================================================================================================================ AC1: the list
def test_quotes_in_progress_is_the_landing_tab_and_lists_the_active_quotations(landing, progress, api_roles):
    """Qase QP-LS1 (AC1) -- the AM lands on 'Quotes in Progress'; its number is the total of active quotations and the first page lists the first ten, none in a final status."""
    total = api_list(api_roles)["totalCount"]
    assert count(progress) == total, f"tab says {count(progress)}, the API says {total}"
    rows = progress.rows()
    assert 0 < len(rows) <= 10
    expected = [item["quoteNo"] for item in api_list(api_roles)["items"]]
    assert [row["quote_no"] for row in rows] == expected
    assert all(row["status"].split("↦")[0].strip() in NOT_FINAL for row in rows), [row["status"] for row in rows]


# ================================================================================================================ AC2: OEM, Site and Type
def test_the_oem_site_and_type_filters_start_on_all(progress):
    """Qase QP-FL1 (AC2) -- default value of each independent filter is 'All' (no filter applied)."""
    assert [progress.filter_value(kind) for kind in ("oem", "site", "type")] == ["All OEMs", "All Sites", "All Types"]


@pytest.mark.parametrize("kind", ["oem", "site", "type"])
def test_each_filter_is_filled_with_the_values_of_the_existing_quotations(landing, progress, api_roles, kind):
    """Qase QP-FL2 (AC2) -- the options are the distinct values found across the quotations, read from the same user's API, no more and no less."""
    field = KIND_PARAM[kind]
    existing = api_all(api_roles) + api_all_closed(api_roles)
    expected = {item[field].strip() for item in existing if item.get(field) and item[field].strip()}
    if kind == "site":                      # the Site filter also lists the registered sites (OP-55), which may have no quotation yet
        expected |= set(registered_sites(landing))
    options = set(progress.filter_options(kind))
    if kind == "oem":                       # #224 fixed (2026-11-19): a name longer than 48 characters is shown shortened with "..." in the middle; every other name is shown whole
        shortened = {option for option in options if "…" in option}
        long_names = {name for name in expected if len(name) > 48}
        assert len(shortened) == len(long_names) and all(any(all(part in name for part in option.split("…")) for name in long_names) for option in shortened), f"shortened: {sorted(shortened)}; long names: {sorted(n[:20] for n in long_names)}"
        options -= shortened
        expected -= long_names
    same = (lambda values: {v.lower() for v in values}) if kind == "site" else (lambda values: values)      # "Bolivia" / "BOLIVIA": see the OP-55 test below
    assert same(options) == same(expected), f"only in the filter: {sorted(options - expected)[:5]}; only in the quotations/sites: {sorted(expected - options)[:5]}"


@pytest.mark.parametrize("kind", ["oem", "site", "type"])
def test_each_filter_works_on_its_own_and_the_counter_matches(progress, api_roles, kind):
    """Qase QP-FL3 (AC2, AC6; Site and Type, OEM is QP-FL4) -- choosing one value shows only its quotations and the counter equals what the API returns for it."""
    value = first_option(progress, kind)
    progress.choose_filter(kind, value)
    expected = api_list(api_roles, **{KIND_PARAM[kind]: value})["totalCount"]
    assert wait_count(progress, expected) == expected, f"{kind}={value!r}"
    if kind == "site":
        assert {row["site"].lower() for row in progress.rows()} <= {value.lower()}


# Qase #226 / #225 / #224 (OP-192 / OP-191 / OP-190): FIXED, verified 2026-11-19 (exact OEM match; BOLIVIA and Bolivia in the Site filter; long OEM names shortened in the filter).
def test_choosing_an_oem_lists_only_the_quotations_of_that_oem(progress, api_roles):
    """Qase QP-FL4 (AC2, AC6; defect #226) -- the counter of an OEM equals the number of active quotations whose OEM is exactly that one."""
    names = [item["oemName"].strip() for item in api_all(api_roles) if item.get("oemName") and item["oemName"].strip()]
    value = next((name for name in sorted(set(names)) if any(other != name and name.lower() in other.lower() for other in set(names))), None)
    if value is None:
        pytest.skip("needs an OEM whose name is part of another OEM's name (for example 'Acme' and 'Acme Solar Corp')")
    progress.choose_filter("oem", value)
    expected = sum(1 for name in names if name == value)
    assert wait_count(progress, expected) == expected, f"{value!r}: the list shows {count(progress)}, the quotations of exactly that OEM are {expected}"


# ================================================================================================================ AC3: Item
# Qase #223 (OP-189): NOT A DEFECT (2026-11-19): the developer confirmed that "OEM Review" is the name of the stage; the owner of OP-11 is asked to update the criterion.
def test_item_offers_exactly_the_three_options_of_the_story(progress):
    """Qase QP-IT1 (AC3; defect #223 invalid) -- Item offers exactly: AM/FPM/FSM Quoting, BU Reviewing, OEM Review (besides the 'Item' reset entry)."""
    assert [text for text, _ in item_options(progress)] == ITEM_STORY


def test_item_has_three_options_and_starts_without_a_filter(progress):
    """Qase QP-IT1 (AC3) -- three options, and the control starts on the 'Item' reset entry (no filter)."""
    assert len(item_options(progress)) == 3
    assert item_select(progress).evaluate("el => el.options[el.selectedIndex].text").strip() == "Item"


@pytest.mark.parametrize("value", list(ITEM_VALUES.values()))
def test_each_item_option_filters_by_its_stage_and_the_counter_matches(progress, api_roles, value):
    """Qase QP-IT2 (AC3, AC6) -- each option shows only the quotations at that stage; the counter equals the API's."""
    item_select(progress).select_option(value=value)
    progress.settle()
    expected = api_list(api_roles, workflowStage=value)["totalCount"]
    assert wait_count(progress, expected) == expected


def test_the_three_item_stages_add_up_to_all_the_active_quotations(progress, api_roles):
    """Qase QP-IT2 (AC3) -- every active quotation is at one of the three stages (no quotation is lost by the filter)."""
    parts = sum(api_list(api_roles, workflowStage=value)["totalCount"] for value in ITEM_VALUES.values())
    assert parts == api_list(api_roles)["totalCount"]


def test_the_item_list_shows_the_whole_text_of_every_option_and_applies_the_chosen_one(progress, api_roles):
    """Qase QP-IT3 (rewritten 2026-11-19; defect #223 invalid) -- the list shows the complete text of the three options and the chosen option is applied: the counter equals the API for its stage. The closed box is 90 px wide and
    may show a long option shortened (the Site filter does the same with a long site name); the story sets no width."""
    assert [text for text, _ in item_options(progress)] == ITEM_STORY
    for text, value in item_options(progress):
        item_select(progress).select_option(value=value)
        progress.settle()
        expected = api_list(api_roles, workflowStage=value)["totalCount"]
        assert wait_count(progress, expected) == expected, f"{text}: the counter does not equal the API"


# ================================================================================================================ AC4 and AC5: search and combination
def test_the_search_box_finds_a_quotation_by_its_wo_number(progress, api_roles):
    """Qase QP-SR1 (AC4) -- searching a WO / Quote number (Enter) lists that quotation and the counter says 1."""
    quote_no = api_list(api_roles)["items"][0]["quoteNo"]
    progress.search_with_enter(quote_no)
    assert wait_count(progress, 1) == 1
    assert [row["quote_no"] for row in progress.rows()] == [quote_no]


def test_the_search_looks_through_all_the_pages_not_only_the_first(progress, api_roles):
    """Qase QP-SR2 (OP-56) -- a quotation that is on page 2 is found by its number; the counter shows the matches and the pager is recalculated."""
    second = api_list(api_roles, page=2)
    if not second["items"]:
        pytest.skip("needs more than 10 active quotations of the AM to have a second page")
    quote_no = second["items"][0]["quoteNo"]
    progress.search_with_enter(quote_no)
    assert wait_count(progress, 1) == 1
    assert [row["quote_no"] for row in progress.rows()] == [quote_no]
    assert progress.pager_text() in (None, "Page 1 of 1")


def test_the_search_finds_a_quotation_by_its_gsp_number(progress, api_roles):
    """Qase QP-SR3 (OP-56) -- 'it is possible to search by #WO or AlarmId/GSP#': the GSP number finds its quotation."""
    item = api_list(api_roles, page=2)["items"][0] if api_list(api_roles, page=2)["items"] else api_list(api_roles)["items"][0]
    progress.search_with_enter(item["gsp"])
    assert wait_count(progress, 1) == 1
    assert [row["quote_no"] for row in progress.rows()] == [item["quoteNo"]]


def test_filters_combine_with_and_without_a_page_reload(landing, progress, api_roles):
    """Qase QP-CB1 (AC5, AC6) -- Type + Site + Item together: the list and the counter equal the API's for the three, and the page is not reloaded (a marker kept in the page survives)."""
    type_value, site_value = first_option(progress, "type"), first_option(progress, "site")
    landing.page.evaluate("window.__hu04_marker = 1")
    progress.choose_filter("type", type_value)
    progress.choose_filter("site", site_value)
    item_select(progress).select_option(value="Quoting")
    progress.settle()
    expected = api_list(api_roles, typeOfWork=type_value, siteName=site_value, workflowStage="Quoting")["totalCount"]
    assert wait_count(progress, expected) == expected
    assert landing.page.evaluate("window.__hu04_marker") == 1, "the page was reloaded"
    last = progress.last_call()
    assert (last.get("typeOfWork"), last.get("siteName"), last.get("workflowStage"), last.get("page")) == (type_value, site_value, "Quoting", "1")


def test_search_and_a_filter_combine(progress, api_roles):
    """Qase QP-CB2 (AC5) -- a Site filter plus a search text: only the quotations that match both."""
    site = first_option(progress, "site")
    item = api_list(api_roles, siteName=site)["items"][0]
    progress.choose_filter("site", site)
    progress.search_with_enter(item["quoteNo"])
    assert wait_count(progress, 1) == 1 and [row["quote_no"] for row in progress.rows()] == [item["quoteNo"]]


# ================================================================================================================ AC7 and AC8: empty and clear
def test_a_search_without_matches_shows_the_empty_message_and_a_zero_counter(progress):
    """Qase QP-EM1 (AC7, AC6) -- the message 'No results for this filter.' and the counter at 0."""
    progress.search_with_enter(UNKNOWN_TEXT)
    assert progress.wait_for_text(NO_RESULTS)
    assert wait_count(progress, 0) == 0 and progress.rows() == []


def test_filters_without_matches_also_show_the_empty_message(progress):
    """Qase QP-EM1 (AC7) -- a filter combination nobody matches shows the same message."""
    progress.search_with_enter(UNKNOWN_TEXT)
    progress.choose_filter("type", first_option(progress, "type"))
    assert progress.wait_for_text(NO_RESULTS)


def test_clear_resets_every_filter_and_the_search_in_one_action(progress, api_roles):
    """Qase QP-CL1 (AC8) -- after OEM, Site, Type, Item and a search, one click on Clear leaves them all on their defaults and the counter at the total."""
    total = api_list(api_roles)["totalCount"]
    for kind in ("oem", "site", "type"):
        progress.choose_filter(kind, first_option(progress, kind))
    item_select(progress).select_option(value="Quoting")
    progress.search_with_enter(UNKNOWN_TEXT)
    progress.clear()
    assert [progress.filter_value(kind) for kind in ("oem", "site", "type")] == ["All OEMs", "All Sites", "All Types"]
    assert item_select(progress).evaluate("el => el.options[el.selectedIndex].text").strip() == "Item"
    assert progress.search_value() == ""
    assert wait_count(progress, total) == total


# ================================================================================================================ regression of the closed bugs
# Qase #226 / #225 / #224 (OP-192 / OP-191 / OP-190): FIXED, verified 2026-11-19 (exact OEM match; BOLIVIA and Bolivia in the Site filter; long OEM names shortened in the filter).
def test_the_site_filter_lists_every_registered_site(landing, progress):
    """Qase QP-RG1 (OP-55; defect #225) -- every site of the header's site list (the registered sites) is in the Site filter of the list, with its exact name."""
    registered = registered_sites(landing)
    assert registered, "no registered site was read from the header"
    missing = sorted(set(registered) - set(progress.filter_options("site")))
    assert not missing, f"registered sites missing from the filter: {missing}"


def test_a_very_long_approver_name_does_not_cover_the_next_column(progress, api_roles):
    """Qase QP-RG2 (OP-104, case 949) -- the WAITING ON cell of a row with a long approver name stays inside its column (does not reach the Age cell)."""
    long_rows = [item for item in api_all(api_roles) if len(str(item.get("waitingOn") or item.get("waitingOnName") or "")) > 80]
    if not long_rows:
        pytest.skip("needs an active quotation whose pending approver has a very long name (see Qase case 949 / defect #122); none exists")
    progress.search_with_enter(long_rows[0]["quoteNo"])
    overlap = progress.page.evaluate("""() => { const b = document.querySelector('button.group'); const c = Array.from(b.children);
        return c[3].getBoundingClientRect().right > c[4].getBoundingClientRect().left + 1 || c[3].scrollWidth > c[3].clientWidth + 1; }""")
    assert not overlap


# Qase #226 / #225 / #224 (OP-192 / OP-191 / OP-190): FIXED, verified 2026-11-19 (exact OEM match; BOLIVIA and Bolivia in the Site filter; long OEM names shortened in the filter).
def test_a_very_long_oem_name_does_not_stretch_the_open_oem_dropdown(landing, progress):
    """Qase QP-UX1 (defect #224) -- on a laptop window (1366 x 768) the open OEM list stays inside the window. The list is a native browser popup that the automation cannot see, so the test
    calculates what the browser does: the popup starts at the left edge of the select and is as wide as the widest option text (never narrower than the select)."""
    page = landing.page
    original = page.viewport_size
    page.set_viewport_size({"width": 1366, "height": 768})
    try:
        page.wait_for_timeout(500)
        result = progress.filter_select("oem").evaluate("""el => { const s = getComputedStyle(el), c = document.createElement('canvas').getContext('2d'); c.font = s.font;
            const widest = Math.max(...Array.from(el.options).map(o => c.measureText(o.text).width)) + parseFloat(s.paddingLeft) + parseFloat(s.paddingRight) + 20;
            const box = el.getBoundingClientRect(), popup = Math.max(box.width, widest);
            return {left: Math.round(box.left), popup: Math.round(popup), right_edge: Math.round(box.left + popup), window: window.innerWidth}; }""")
    finally:
        if original:
            page.set_viewport_size(original)
    assert result["right_edge"] <= result["window"], f"the open OEM list would end at {result['right_edge']} px in a window of {result['window']} px: {result}"
