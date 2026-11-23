"""Quotation module -- Historical Quotes tab: view, filters and search, screen side (OP-12 / HU-05; Qase suite "HU-05: Quotation history view and filtering", cases HQ-*).

Only the HU-05 text decides what must happen (V13/V14 describe an old prototype of this area -- Category, Search button and a WO NUMBER dropdown -- that the story's table replaces).
Observed on the QA build of 2026-10-26: GET /api/quotations?page&pageSize=10&includeClosed=true is the Historical tab (false is "Quotes in Progress"), with the filters oemName,
siteName and typeOfWork and the search. Each AM sees only its own quotations, so every expectation here is read from the API as the SAME user instead of being hard-coded: the tests
keep working when the data or the visibility rules change.
Data the story needs and the QA may not have: more than 10 historical quotations (paging), a historical quotation older than a day (Age), one created from an alarm (Alarm ID) and one with
a device. A test that needs data that does not exist is SKIPPED with the reason, never failed (see tools/oem_quotation.py seed-historical).
Not testable on this build: the status "Closed" (not implemented, developer 2026-10-26). "A later refresh fails" is tested (HQ-ST6): the list reloads after Save Draft (developer 2026-10-27).
The tests that simulate a slow or failing list use route interception on the shared page and always remove it.
"""
import re
from datetime import datetime

import pytest
from playwright.sync_api import Error as PlaywrightError

from framework_ui.pages.quotation import quotation_locators as quotation_loc
from framework_ui.pages.quotation.components import historical_quotes_locators as loc
from framework_ui.pages.quotation.quotation_page import QuotationPage

pytestmark = pytest.mark.ui

LIST_ROUTE = re.compile(r".*/api/quotations\?.*")
HISTORICAL_ROUTE = re.compile(r".*/api/quotations\?.*includeClosed=true.*")
NOT_FINAL = ["Draft", "Awaiting", "Returned", "Rejected", "OemRejected"]
EMPTY_LIST = '{"items":[],"totalCount":0,"pageNumber":1,"pageSize":10,"totalPages":0,"hasPreviousPage":false,"hasNextPage":false}'
SLOW_MS = 3500


# ---- the API as the same user (ground truth) ------------------------------------------------------------------------------------------
def api_list(api_roles, closed, page=1, page_size=10, **params):
    response = api_roles["AM"].get("/api/quotations", page=page, pageSize=page_size, includeClosed="true" if closed else "false", **params)
    assert response.status_code == 200, f"{response.status_code} {response.text[:200]}"
    return response.json()


def api_all(api_roles, closed, **params):
    """Every item of a list, read 100 at a time."""
    items, page = [], 1
    while True:
        data = api_list(api_roles, closed, page=page, page_size=100, **params)
        items += data["items"]
        if not data["hasNextPage"]:
            return items
        page += 1


def need_historical(api_roles, minimum, why):
    total = api_list(api_roles, True)["totalCount"]
    if total < minimum:
        pytest.skip(f"needs {minimum} or more historical quotations of the AM to {why}; there are {total} (python tools/oem_quotation.py seed-historical)")
    return total


def quote_numbers(rows):
    return [row["quote_no"] for row in rows]


def status_of(row):
    return row["status"].split("↦")[0].strip()


def local_date(iso_text):
    return datetime.fromisoformat(iso_text.replace("Z", "+00:00")).astimezone().date()


def age_label(created_at, ended_at):
    """The Age the story asks for: calendar days from the creation to `ended_at`, as 'Today', '1 day' or 'N days'."""
    days = (local_date(ended_at) - local_date(created_at)).days
    return "Today" if days == 0 else "1 day" if days == 1 else f"{days} days"


def delay_list(page, delay_ms=SLOW_MS):
    """Makes every list call take `delay_ms` longer. Returns the handler, to give to page.unroute (the page may move on while the call waits)."""
    def handler(route):
        page.wait_for_timeout(delay_ms)
        try:
            route.continue_()
        except PlaywrightError:
            pass
    page.route(LIST_ROUTE, handler)
    return handler


# ---- fixtures -------------------------------------------------------------------------------------------------------------------------
@pytest.fixture
def landing(role_page):
    """The AM's Quotation landing list, freshly loaded."""
    page = QuotationPage(role_page("AM")).open(refresh=True)
    page.historical_quotes().settle()
    yield page
    page.historical_quotes().detach()
    for pattern in (LIST_ROUTE, HISTORICAL_ROUTE):
        page.page.unroute(pattern)


@pytest.fixture
def historical(landing):
    """The component with the 'Historical Quotes' tab open."""
    component = landing.historical_quotes()
    component.open_historical()
    return component


def role_landing(role_page, role):
    page = QuotationPage(role_page(role)).open(refresh=True)
    return page, page.historical_quotes()


# ================================================================================================================ permissions and roles
def test_the_am_sees_the_historical_tab_next_to_quotes_in_progress(landing):
    """Qase HQ-PM1 -- the AM has both tabs, 'Quotes in Progress' first."""
    component = landing.historical_quotes()
    assert component.has_tab(loc.TAB_IN_PROGRESS_TEXT) and component.has_tab(loc.TAB_HISTORICAL_TEXT)
    tabs = landing.page.get_by_role("button").filter(has_text=re.compile(rf"^\s*({loc.TAB_IN_PROGRESS_TEXT}|{loc.TAB_HISTORICAL_TEXT})")).all_inner_texts()
    assert [" ".join(t.split()).split(" (")[0] for t in tabs[:2]] == [loc.TAB_IN_PROGRESS_TEXT, loc.TAB_HISTORICAL_TEXT], tabs


@pytest.mark.parametrize("role", ["FPM", "BU", "CEO"])
def test_an_approver_lands_on_pending_approval_and_has_no_historical_tab(role_page, role):
    """Qase HQ-PM2 (FPM/FSM), HQ-PM3 (BU), HQ-PM4 (CEO) -- they land on 'Pending approval' and do not see 'Historical Quotes'."""
    landing_page, component = role_landing(role_page, role)
    try:
        assert component.wait_for_text(loc.PENDING_APPROVAL_TEXT), component.body_text()[-300:]
        assert not component.has_tab(loc.TAB_HISTORICAL_TEXT)
    finally:
        component.detach()


def test_a_user_without_a_quotation_role_sees_the_access_message_and_no_list(role_page):
    """Qase HQ-PM5 -- the page shows 'Quotation access requires an AM, FPM/FSM, BU, or CEO role assignment.' (the four roles, the CEO included) and no tabs."""
    landing_page, component = role_landing(role_page, "NOROLE")
    try:
        component.wait_for_text("Quotation access requires")
        body = component.body_text()
        assert loc.MESSAGE_NO_ROLE in body, f"message in the page: {body[body.find('Quotation access'):][:120]!r}"
        assert not component.has_tab(loc.TAB_IN_PROGRESS_TEXT) and not component.has_tab(loc.TAB_HISTORICAL_TEXT)
    finally:
        component.detach()


# ================================================================================================================ content
def test_the_historical_tab_lists_the_approved_quotations(historical, api_roles):
    """Qase HQ-CT1 -- every quotation of the first page is the one the API lists as historical, and all of them are Approved or Closed."""
    expected = api_list(api_roles, True)["items"]
    rows = historical.rows()
    assert quote_numbers(rows) == [item["quoteNo"] for item in expected], (quote_numbers(rows), [i["quoteNo"] for i in expected])
    assert {status_of(row) for row in rows} <= {"Approved", "Closed"}, rows


@pytest.mark.parametrize("status", NOT_FINAL)
def test_a_quotation_that_is_not_final_is_in_quotes_in_progress_and_not_in_historical(landing, api_roles, status):
    """Qase HQ-CT2 (Draft), CT3 (Awaiting / Submitted), CT4 (Returned), CT5 (Rejected), CT6 (OEM Rejected) -- still active, so not in Historical Quotes."""
    items = [item for item in api_list(api_roles, False, status=status)["items"] if item["status"] == status]
    if not items:
        pytest.skip(f"the AM has no quotation in the status {status}")
    quote_no = items[0]["quoteNo"]
    component = landing.historical_quotes()
    component.search_with_enter(quote_no)
    assert quote_no in quote_numbers(component.rows()), f"{quote_no} ({status}) is not in Quotes in Progress"
    component.open_historical()
    component.search_with_enter(quote_no)
    assert quote_no not in quote_numbers(component.rows()), f"{quote_no} ({status}) is in Historical Quotes"


def test_the_table_shows_the_columns_in_the_story_order(historical):
    """Qase HQ-CT7 -- WO / Quote #, WO Title, Site, Waiting on, Age, Current step, Source, Status."""
    assert [text.lower() for text in historical.column_headers()] == [text.lower() for text in loc.HEADER_TEXTS]


def test_an_approved_quotation_shows_a_dash_ready_for_client_and_approved(historical, api_roles):
    """Qase HQ-CT8 -- 'Waiting on' shows '—', 'Current step' shows 'Ready for Client' and 'Status' shows 'Approved'."""
    approved = [row for row in historical.rows() if status_of(row) == "Approved"]
    if not approved:
        pytest.skip("the AM has no Approved quotation")
    for row in approved:
        assert (row["waiting_on"], row["current_step"], status_of(row)) == ("—", "Ready for Client", "Approved"), row


def test_the_quotations_are_sorted_by_creation_date_most_recent_first(historical, api_roles):
    """Qase HQ-CT9 -- the order of the rows follows the creation date, newest first."""
    items = api_list(api_roles, True)["items"]
    created = [item["createdAt"] for item in items]
    assert created == sorted(created, reverse=True), created
    assert quote_numbers(historical.rows()) == [item["quoteNo"] for item in items]


def test_the_table_shows_ten_quotations_per_page(historical, api_roles):
    """Qase HQ-CT10 -- ten rows on the first page when there are more than ten."""
    need_historical(api_roles, 11, "see a full page")
    assert len(historical.rows()) == 10 and historical.last_call()["pageSize"] == "10"


# ================================================================================================================ age
def test_age_follows_the_story_rule_for_every_historical_quotation(historical, api_roles):
    """Qase HQ-AG1 -- 'Today', '1 day' or 'N days' counted in calendar days from the creation to the day the quotation reached its final status, so it does not keep growing."""
    items = {item["quoteNo"]: item for item in api_list(api_roles, True)["items"]}
    for row in historical.rows():
        item = items[row["quote_no"]]
        assert row["age"] == age_label(item["createdAt"], item["updatedAt"]), (row["quote_no"], row["age"], item["createdAt"], item["updatedAt"])


def days_to_final(item):
    return (local_date(item["updatedAt"]) - local_date(item["createdAt"])).days


@pytest.mark.parametrize("label,wanted", [
    pytest.param("1 day", lambda days: days == 1),
    ("N days", lambda days: days >= 2),
])
def test_age_shows_one_day_and_n_days_for_older_quotations(historical, api_roles, label, wanted):
    """Qase HQ-AG2 ('1 day') and HQ-AG3 ('N days') -- needs a quotation that took one day, or two or more, to reach its final status."""
    items = {item["quoteNo"]: item for item in api_list(api_roles, True)["items"]}
    found = [row for row in historical.rows() if wanted(days_to_final(items[row["quote_no"]]))]
    if not found:
        pytest.skip(f"no historical quotation of the AM took {'exactly one day' if label == '1 day' else 'two or more days'} to reach its final status yet")
    pattern = r"1 day" if label == "1 day" else r"\d+ days"
    assert all(re.fullmatch(pattern, row["age"]) for row in found), found


# ================================================================================================================ paging and count
def test_the_pager_shows_page_x_of_y_with_previous_and_next_when_there_are_several_pages(historical, api_roles):
    """Qase HQ-PG1 -- 'Page 1 of Y' with Previous and Next."""
    total_pages = api_list(api_roles, True)["totalPages"]
    need_historical(api_roles, 11, "have more than one page")
    assert historical.pager_text() == f"Page 1 of {total_pages}"


def test_previous_is_disabled_on_the_first_page(historical, api_roles):
    """Qase HQ-PG2 -- Previous cannot be used on page 1."""
    need_historical(api_roles, 11, "have more than one page")
    assert not historical.previous_enabled() and historical.next_enabled()


def test_next_is_disabled_on_the_last_page_and_the_last_page_shows_the_remaining_rows(historical, api_roles):
    """Qase HQ-PG3 -- Next cannot be used on the last page, which holds what is left."""
    total = need_historical(api_roles, 11, "have more than one page")
    total_pages = api_list(api_roles, True)["totalPages"]
    for _ in range(total_pages - 1):
        historical.go_next()
    assert historical.pager_text() == f"Page {total_pages} of {total_pages}"
    assert not historical.next_enabled() and historical.previous_enabled()
    assert len(historical.rows()) == total - 10 * (total_pages - 1)


def test_previous_goes_back_to_the_page_before(historical, api_roles):
    """Qase HQ-PG4 -- Next then Previous shows page 1 again with the same rows."""
    need_historical(api_roles, 11, "have more than one page")
    first = quote_numbers(historical.rows())
    historical.go_next()
    assert historical.pager_text().startswith("Page 2 of") and quote_numbers(historical.rows()) != first
    historical.go_previous()
    assert historical.pager_text().startswith("Page 1 of") and quote_numbers(historical.rows()) == first


def test_the_tab_label_counts_every_historical_quotation_across_all_pages(historical, api_roles):
    """Qase HQ-PG5 -- 'Historical Quotes (N)' with N the total, not the rows of the page."""
    assert historical.tab_count(loc.TAB_HISTORICAL_TEXT) == api_list(api_roles, True)["totalCount"]


def test_the_tab_label_counts_the_quotations_that_match_the_filters_and_the_search(historical, api_roles):
    """Qase HQ-PG6 -- after a search the number is the number of matches."""
    items = api_list(api_roles, True)["items"]
    term = items[0]["quoteNo"]
    expected = api_list(api_roles, True, search=term)["totalCount"]
    historical.search_with_enter(term)
    assert historical.tab_count(loc.TAB_HISTORICAL_TEXT) == expected


def test_the_number_of_the_tab_is_hidden_while_the_list_reloads(landing, historical):
    """Qase HQ-PG7 -- while the list loads again the tab shows no number."""
    page = landing.page
    handler = delay_list(page)
    historical.filter_select("type").select_option(label=historical.filter_options("type")[0])
    page.wait_for_timeout(700)
    during = historical.tab_label(loc.TAB_HISTORICAL_TEXT)
    page.unroute(LIST_ROUTE, handler)
    historical.settle()
    assert historical.tab_count(loc.TAB_HISTORICAL_TEXT) is not None
    assert loc.TAB_COUNT_PATTERN.search(during) is None, during


# ================================================================================================================ opening a quotation
def test_a_click_on_a_row_opens_the_quotation_read_only(landing, historical):
    """Qase HQ-OP1 -- the quotation opens without 'Save Draft' or 'Submit Quotation' and its fields cannot be edited."""
    row = historical.rows()[0]
    historical.open_row(row["quote_no"])
    landing.page.get_by_text(quotation_loc.FORM_LOADED_MARKER_TEXT, exact=True).wait_for(timeout=20000)
    page = landing.page
    assert page.get_by_role("button", name=quotation_loc.SAVE_DRAFT_BUTTON_TEXT).count() == 0
    assert page.get_by_role("button", name=quotation_loc.SUBMIT_QUOTATION_BUTTON_TEXT).count() == 0
    editable = page.locator("input").evaluate_all("els => els.filter(e => !e.disabled && !e.readOnly && e.type !== 'hidden' && e.offsetParent !== null && !/search/i.test(e.placeholder || '')).map(e => e.placeholder || e.type)")
    assert editable == [], f"editable fields in a historical quotation: {editable}"


def test_a_click_on_the_status_opens_the_history_of_that_quotation(landing, historical):
    """Qase HQ-OP2 -- the 'Quotation Workflow' panel opens with the quote number."""
    row = historical.rows()[0]
    historical.open_history(row["quote_no"])
    landing.page.get_by_text(re.compile(r"^quotation workflow$", re.I)).first.wait_for(timeout=10000)
    assert row["quote_no"] in landing.workflow_history_text() or row["quote_no"] in historical.body_text()


# ================================================================================================================ filters
def test_the_toolbar_has_three_filters_with_their_default_labels_and_no_item_filter(historical, landing):
    """Qase HQ-FL1 (three filters 'All OEMs', 'All Sites', 'All Types') and HQ-FL2 (no 'Item' filter in Historical Quotes)."""
    assert [historical.filter_value(kind) for kind in ("oem", "site", "type")] == ["All OEMs", "All Sites", "All Types"]
    assert not historical.has_item_filter()
    historical.open_in_progress()
    assert historical.has_item_filter(), "control: 'Quotes in Progress' does have the Item filter"


def test_the_oem_options_are_the_values_used_in_all_quotations(historical, api_roles):
    """Qase HQ-FL3 -- the OEMs of the quotations in progress and the historical ones, nothing else."""
    expected = {item["oemName"].strip() for item in api_all(api_roles, False) + api_all(api_roles, True) if (item.get("oemName") or "").strip()}   # a name of only spaces is not an option
    assert {option.strip() for option in historical.filter_options("oem")} == expected


def test_the_type_of_work_options_are_the_values_used_in_all_quotations(historical, api_roles):
    """Qase HQ-FL4 -- the types of work of the quotations in progress and the historical ones."""
    expected = {item["typeOfWork"].strip() for item in api_all(api_roles, False) + api_all(api_roles, True) if item.get("typeOfWork")}
    assert {option.strip() for option in historical.filter_options("type")} == expected


def test_the_site_options_combine_the_omniops_sites_and_the_quotation_sites_without_duplicates(historical, api_roles):
    """Qase HQ-FL5 -- OmniOps sites plus the sites of all quotations, each once."""
    omniops = {site["name"].strip() for site in api_roles["AM"].get("/api/Sites/status").json()}
    used = {item["siteName"].strip() for item in api_all(api_roles, False) + api_all(api_roles, True) if item.get("siteName")}
    options = [option.strip() for option in historical.filter_options("site")]
    assert len({option.lower() for option in options}) == len(options), f"duplicates in {options}"
    assert {option.lower() for option in options} == {name.lower() for name in omniops | used}


def test_the_site_filter_says_some_sites_could_not_be_loaded_when_the_omniops_sites_fail(landing):
    """Qase HQ-FL6 -- 'Some sites couldn't be loaded' when the OmniOps sites cannot be read."""
    page = landing.page
    page.route(re.compile(r".*/api/Sites/.*"), lambda route: route.abort())
    try:
        landing.open(refresh=True)
        landing.historical_quotes().settle()
        landing.historical_quotes().open_historical()
        page.wait_for_timeout(2500)
        assert loc.MESSAGE_SITES_ERROR in landing.historical_quotes().body_text()
    finally:
        page.unroute(re.compile(r".*/api/Sites/.*"))


def pick(historical, api_roles, kind, field):
    """A value of the filter that matches some, but not all, of the historical quotations (or None)."""
    items = api_all(api_roles, True)
    values = {item[field] for item in items if item.get(field)}
    for option in historical.filter_options(kind):
        matching = [item for item in items if (item.get(field) or "").strip() == option.strip()]
        if matching and len(matching) < len(items) and len(values) > 1:
            return option, len(matching)
    return None, 0


@pytest.mark.parametrize("kind,field,param", [("oem", "oemName", "oemName"), ("site", "siteName", "siteName"), ("type", "typeOfWork", "typeOfWork")])
def test_each_filter_narrows_the_list_to_its_value(historical, api_roles, kind, field, param):
    """Qase HQ-FL7 (OEM), HQ-FL8 (Site), HQ-FL9 (Type of Work) -- the table shows what the API gives for that filter; with one value only, every quotation matches it."""
    option, expected_count = pick(historical, api_roles, kind, field)
    if option is None:
        option = next((o for o in historical.filter_options(kind) if any((i.get(field) or "").strip() == o.strip() for i in api_list(api_roles, True)["items"])), None)
        if option is None:
            pytest.skip(f"no historical quotation has a value for the {kind} filter")
    historical.choose_filter(kind, option)
    assert historical.last_call().get(param, "").strip() == option.strip()
    expected = api_list(api_roles, True, **{param: option})
    assert quote_numbers(historical.rows()) == [item["quoteNo"] for item in expected["items"]]
    assert historical.tab_count(loc.TAB_HISTORICAL_TEXT) == expected["totalCount"]


def test_a_filter_with_no_historical_match_shows_no_results(historical, api_roles):
    """Qase HQ-FL10 -- choosing a value that no historical quotation has shows 'No results for this filter.'."""
    items = api_all(api_roles, True)
    used = {(item.get("typeOfWork") or "").strip() for item in items}
    unused = [option for option in historical.filter_options("type") if option.strip() not in used]
    if unused:
        historical.choose_filter("type", unused[0])
    else:
        # every type of work has a historical quotation: an OEM and a site that never appear together give no result
        pairs = {((item.get("oemName") or "").strip(), (item.get("siteName") or "").strip()) for item in items}
        oem, site = next(((o, s) for o in historical.filter_options("oem") for s in historical.filter_options("site") if (o.strip(), s.strip()) not in pairs), (None, None))
        if oem is None:
            pytest.skip("every OEM and site pair has a historical quotation")
        historical.choose_filter("oem", oem)
        historical.choose_filter("site", site)
    assert historical.rows() == [] and historical.text_shown(loc.MESSAGE_NO_RESULTS)


def test_the_filters_combine_with_each_other_and_with_the_search(historical, api_roles):
    """Qase HQ-FL11 -- OEM, Type of Work and a search together give what the API gives for the three."""
    items = api_all(api_roles, True)
    oem = next((i["oemName"] for i in items if i.get("oemName")), None)
    kind = next((i["typeOfWork"] for i in items if i.get("typeOfWork")), None)
    if not oem or not kind:
        pytest.skip("not enough data to combine two filters")
    term = items[0]["title"].split()[0]
    historical.choose_filter("oem", oem.strip())
    historical.choose_filter("type", kind.strip())
    historical.search_with_enter(term)
    call = historical.last_call()
    assert (call.get("oemName"), call.get("typeOfWork"), call.get("search")) == (oem.strip(), kind.strip(), term), call
    expected = api_list(api_roles, True, oemName=oem.strip(), typeOfWork=kind.strip(), search=term)
    assert quote_numbers(historical.rows()) == [item["quoteNo"] for item in expected["items"]]


def test_changing_a_filter_returns_to_page_one(historical, api_roles):
    """Qase HQ-FL12 -- from page 2, a new filter value asks for page 1."""
    need_historical(api_roles, 11, "be on a second page")
    historical.go_next()
    assert historical.last_call()["page"] == "2"
    option = historical.filter_options("type")[0]
    historical.choose_filter("type", option)
    assert historical.last_call()["page"] == "1"
    assert historical.pager_text() is None or historical.pager_text().startswith("Page 1 of")


def test_changing_the_search_returns_to_page_one(historical, api_roles):
    """Qase HQ-FL13 -- from page 2, a new search asks for page 1."""
    need_historical(api_roles, 11, "be on a second page")
    historical.go_next()
    historical.search_with_enter("Workflow")
    assert historical.last_call()["page"] == "1"


def test_clear_resets_every_filter_and_the_search(historical, api_roles):
    """Qase HQ-FL14 -- after Clear the filters say 'All ...', the search box is empty and the list is the full one."""
    items = api_list(api_roles, True)["items"]
    historical.choose_filter("type", next(o for o in historical.filter_options("type")))
    historical.search_with_enter(items[0]["quoteNo"])
    historical.clear()
    assert [historical.filter_value(kind) for kind in ("oem", "site", "type")] == ["All OEMs", "All Sites", "All Types"]
    assert historical.search_value() == ""
    expected = api_list(api_roles, True)
    assert quote_numbers(historical.rows()) == [item["quoteNo"] for item in expected["items"]]
    assert historical.tab_count(loc.TAB_HISTORICAL_TEXT) == expected["totalCount"]


def test_switching_between_the_tabs_resets_the_filters_and_the_search(historical):
    """Qase HQ-FL15 -- filters and search are cleared when the user goes to the other tab and back."""
    historical.choose_filter("type", historical.filter_options("type")[0])
    historical.search_with_enter("Workflow")
    historical.open_in_progress()
    assert [historical.filter_value(kind) for kind in ("oem", "site", "type")] == ["All OEMs", "All Sites", "All Types"] and historical.search_value() == ""
    historical.choose_filter("type", historical.filter_options("type")[0])
    historical.open_historical()
    assert [historical.filter_value(kind) for kind in ("oem", "site", "type")] == ["All OEMs", "All Sites", "All Types"] and historical.search_value() == ""


# ================================================================================================================ search
def first_item_with(api_roles, field):
    return next((item for item in api_all(api_roles, True) if item.get(field)), None)


@pytest.mark.parametrize("field,make_term", [
    ("title", lambda value: value[len("Workflow Progress test "):][:12].upper() if value.startswith("Workflow Progress test ") else value[2:10].upper()),
    ("quoteNo", lambda value: value[2:9].lower()),
    ("gsp", lambda value: value[1:9].lower()),
    ("siteName", lambda value: value[1:5].upper()),
    ("device", lambda value: value[1:5].lower()),
])
def test_the_search_matches_part_of_the_field_ignoring_case(historical, api_roles, field, make_term):
    """Qase HQ-SR2 (WO Title), SR3 (Quote #), SR4 (GSP #), SR5 (Site), SR6 (Device) -- a piece of the value, in other case, finds the quotation."""
    item = first_item_with(api_roles, field)
    if item is None:
        pytest.skip(f"no historical quotation has a {field}")
    term = make_term(item[field])
    historical.search_with_enter(term)
    assert item["quoteNo"] in quote_numbers(historical.rows()) or historical.tab_count(loc.TAB_HISTORICAL_TEXT) > len(historical.rows()), (field, term, quote_numbers(historical.rows()))
    expected = api_list(api_roles, True, search=term)
    assert quote_numbers(historical.rows()) == [i["quoteNo"] for i in expected["items"]]


@pytest.mark.skip(reason="OUT OF SCOPE: AC25 of HU-05 says the Alarm ID logic is discarded ('Quotation is no longer linked to Alarms'); the case is deprecated in Qase")
def test_the_search_matches_the_start_of_the_alarm_id_from_its_first_eight_characters(historical, api_roles):
    """Qase HQ-SR7 -- the first 8 characters of the Alarm ID find the quotation made from that alarm."""
    item = first_item_with(api_roles, "alarmId")
    if item is None:
        pytest.skip("no historical quotation was created from an alarm")
    historical.search_with_enter(item["alarmId"][:8])
    assert item["quoteNo"] in quote_numbers(historical.rows())


@pytest.mark.skip(reason="OUT OF SCOPE: AC25 of HU-05 says the Alarm ID logic is discarded ('Quotation is no longer linked to Alarms'); the case is deprecated in Qase")
def test_the_search_does_not_match_the_alarm_id_with_fewer_than_eight_characters(historical, api_roles):
    """Qase HQ-SR8 -- 7 characters of the Alarm ID find nothing."""
    item = first_item_with(api_roles, "alarmId")
    if item is None:
        pytest.skip("no historical quotation was created from an alarm")
    historical.search_with_enter(item["alarmId"][:7])
    assert item["quoteNo"] not in quote_numbers(historical.rows())


def test_typing_does_not_search_and_enter_does(historical):
    """Qase HQ-SR9 -- no list call while typing; Enter sends exactly one."""
    mark = len(historical.list_calls)
    historical.type_in_search("Workflow")
    historical.page.wait_for_timeout(1500)
    assert len(historical.calls_since(mark)) == 0, historical.calls_since(mark)
    historical.search_box().press("Enter")
    historical.settle()
    assert [call.get("search") for call in historical.calls_since(mark)] == ["Workflow"]


@pytest.mark.parametrize("how", ["tab", "click"])
def test_leaving_the_search_box_applies_the_search(historical, how):
    """Qase HQ-SR10 -- leaving the box with the Tab key or by clicking elsewhere searches."""
    mark = len(historical.list_calls)
    (historical.search_by_leaving if how == "tab" else historical.search_by_clicking_away)("Workflow")
    assert [call.get("search") for call in historical.calls_since(mark)] == ["Workflow"]


def test_there_is_no_search_button(historical):
    """Qase HQ-SR11 -- the toolbar has no search button."""
    assert not historical.has_search_button()


def test_spaces_at_the_start_and_the_end_of_the_search_are_ignored(historical, api_roles):
    """Qase HQ-SR12 -- '  term  ' gives the same list as 'term'."""
    term = api_list(api_roles, True)["items"][0]["quoteNo"]
    historical.search_with_enter(f"   {term}   ")
    padded = quote_numbers(historical.rows())
    historical.clear()
    historical.search_with_enter(term)
    assert padded == quote_numbers(historical.rows()) and term in padded


@pytest.mark.parametrize("text", ["", "     "])
def test_an_empty_search_shows_every_historical_quotation_that_matches_the_filters(historical, api_roles, text):
    """Qase HQ-SR13 (empty) and HQ-SR14 (only spaces) -- the list is the one without a search."""
    historical.search_with_enter("zzzzzzzz")
    assert historical.rows() == []
    historical.search_with_enter(text)
    assert quote_numbers(historical.rows()) == [item["quoteNo"] for item in api_list(api_roles, True)["items"]]


@pytest.mark.parametrize("text", ["<b>bold</b>", "<script>window.__ran = true</script>", "'; DROP TABLE quotations; --", "' OR '1'='1"])
def test_the_search_text_is_plain_text_and_never_runs_or_breaks_the_list(historical, landing, api_roles, text):
    """Qase HQ-SR15 (HTML), SR16 (script), SR17 (SQL DROP), SR18 (SQL OR) -- shown as typed, no error, and the list still works afterwards."""
    page = landing.page
    page.evaluate("() => { window.__ran = false; }")
    dialogs = []

    def on_dialog(dialog):
        dialogs.append(dialog.message)
        dialog.dismiss()

    page.on("dialog", on_dialog)
    try:
        historical.search_with_enter(text)
        assert historical.search_value() == text
        assert not page.evaluate("() => window.__ran") and dialogs == []
        assert not historical.text_shown(loc.MESSAGE_LOAD_ERROR)
        assert historical.rows() == [] and historical.text_shown(loc.MESSAGE_NO_RESULTS)
    finally:
        page.remove_listener("dialog", on_dialog)
    historical.clear()
    assert quote_numbers(historical.rows()) == [item["quoteNo"] for item in api_list(api_roles, True)["items"]]


def test_the_search_box_accepts_up_to_300_characters(historical):
    """Qase HQ-SR19 -- 300 characters fit in the box."""
    assert len(historical.type_in_search("a" * loc.SEARCH_MAX_LENGTH)) == loc.SEARCH_MAX_LENGTH


def test_the_search_box_does_not_let_the_user_type_more_than_300_characters(historical):
    """Qase HQ-SR20 -- the 301st character is not accepted."""
    assert len(historical.type_in_search("a" * (loc.SEARCH_MAX_LENGTH + 1))) == loc.SEARCH_MAX_LENGTH


# ================================================================================================================ empty states
def test_with_no_historical_quotations_the_table_says_there_are_none_yet(landing):
    """Qase HQ-ES1 -- 'There are no historical quotations yet.' (the historical list is answered empty)."""
    page = landing.page
    page.route(HISTORICAL_ROUTE, lambda route: route.fulfill(status=200, body=EMPTY_LIST, content_type="application/json"))
    try:
        component = landing.historical_quotes()
        component.open_historical()
        assert component.rows() == [] and component.text_shown(loc.MESSAGE_NO_HISTORICAL)
        assert not component.text_shown(loc.MESSAGE_NO_RESULTS)
    finally:
        page.unroute(HISTORICAL_ROUTE)


def test_with_historical_quotations_but_no_match_the_table_says_no_results(historical):
    """Qase HQ-ES2 -- 'No results for this filter.' and not the 'none yet' text."""
    historical.search_with_enter("zzzzzzzzzzzz")
    assert historical.rows() == [] and historical.text_shown(loc.MESSAGE_NO_RESULTS)
    assert not historical.text_shown(loc.MESSAGE_NO_HISTORICAL)


# ================================================================================================================ loading and errors
def test_the_page_says_loading_quotations_while_the_list_loads_for_the_first_time(role_page):
    """Qase HQ-ST1 -- 'Loading quotations...' shows until the first list arrives."""
    page = role_page("AM")
    handler = delay_list(page)
    try:
        page.reload()
        seen = False
        for _ in range(24):
            page.wait_for_timeout(250)
            if loc.MESSAGE_LOADING in page.inner_text("body"):
                seen = True
                break
        assert seen, "'Loading quotations...' never showed"
    finally:
        page.wait_for_timeout(SLOW_MS + 1000)
        page.unroute(LIST_ROUTE, handler)


@pytest.mark.parametrize("change", ["filter", "search", "page"])
def test_loading_quotations_covers_the_table_when_a_filter_the_search_or_the_page_changes(landing, historical, api_roles, change):
    """Qase HQ-ST2 (filter), ST3 (search), ST4 (page) -- 'Loading quotations...' shows until the new results arrive."""
    if change == "page":
        need_historical(api_roles, 11, "change page")
    page = landing.page
    handler = delay_list(page)
    try:
        if change == "filter":
            historical.filter_select("type").select_option(label=historical.filter_options("type")[0])
        elif change == "search":
            historical.type_in_search("Workflow")
            historical.search_box().press("Enter")
        else:
            page.get_by_role("button", name=loc.NEXT_BUTTON_TEXT, exact=True).click()
        seen = False
        for _ in range(12):
            page.wait_for_timeout(250)
            if loc.MESSAGE_LOADING in page.inner_text("body"):
                seen = True
                break
        assert seen, f"'Loading quotations...' did not show when the {change} changed"
    finally:
        page.wait_for_timeout(SLOW_MS + 500)
        page.unroute(LIST_ROUTE, handler)
        historical.settle()


def test_a_list_that_fails_to_load_shows_the_error_as_page_text_and_not_a_toast(role_page):
    """Qase HQ-ST5 -- 'Could not load quotations.' stays in the page (it does not disappear like a toast)."""
    page = role_page("AM")
    page.route(LIST_ROUTE, lambda route: route.fulfill(status=500, body='{"message":"error"}', content_type="application/json"))
    try:
        page.reload()
        page.get_by_text(loc.MESSAGE_LOAD_ERROR).first.wait_for(timeout=20000)
        page.wait_for_timeout(8000)
        assert page.get_by_text(loc.MESSAGE_LOAD_ERROR).count() > 0, "the error disappeared: it behaves like a toast"
        assert page.locator("[role=alert], [class*=toast], [class*=Toastify]").filter(has_text=loc.MESSAGE_LOAD_ERROR).count() == 0
    finally:
        page.unroute(LIST_ROUTE)


def test_a_later_refresh_that_fails_keeps_the_results_already_shown(landing):
    """Qase HQ-ST6 -- AC36 ('later refresh' = the same list, same filters, search and page, reloaded when the user comes back to it after Save Draft, Submit, Approve or Reject, answer of the
    developer on 2026-10-27): if that reload fails, the rows already shown stay and no error replaces them. Done with Save Draft of a Draft of the AM (nothing is changed in it)."""
    page, component = landing.page, landing.historical_quotes()
    component.type_in_search("Workflow Progress test")
    page.keyboard.press("Enter")
    component.settle()
    shown = [row["quote_no"] for row in component.rows()]
    assert shown, "the search left no row to open"
    component.open_row(shown[0])
    page.get_by_role("button", name=quotation_loc.SAVE_DRAFT_BUTTON_TEXT).wait_for(timeout=20000)
    mark = len(component.list_calls)
    page.route(LIST_ROUTE, lambda route: route.fulfill(status=500, body='{"message":"error"}', content_type="application/json"))
    try:
        landing.save_draft()
        page.wait_for_timeout(6000)
        assert len(component.list_calls) > mark, "coming back to the list did not reload it"
        assert [row["quote_no"] for row in component.rows()] == shown, "the rows already shown did not stay"
        assert not component.text_shown(loc.MESSAGE_LOAD_ERROR), "an error replaced the rows already shown"
    finally:
        page.unroute(LIST_ROUTE)


def test_a_new_query_that_fails_shows_the_error_and_not_the_old_rows(landing):
    """Qase HQ-ST7 -- the other side of AC36: changing the search is a NEW query; if it fails 'Could not load quotations.' is shown (AC35)."""
    page, component = landing.page, landing.historical_quotes()
    assert component.rows()
    page.route(LIST_ROUTE, lambda route: route.fulfill(status=500, body='{"message":"error"}', content_type="application/json"))
    try:
        component.type_in_search("Workflow")
        page.keyboard.press("Enter")
        assert component.wait_for_text(loc.MESSAGE_LOAD_ERROR), component.body_text()[-300:]
    finally:
        page.unroute(LIST_ROUTE)


def test_the_search_placeholder_names_only_what_the_table_shows_and_each_one_can_be_searched(historical):
    """Qase HQ-SR1 -- (defect #182 closed 2026-11-12: the system is the reference, the story text 'GSP #' is to be changed) what the placeholder names must be in the table, and searching by that value in the table finds the quotation. Placeholder on the build of 2026-11-09:
    'Search WO, Quote #, site...' -> WO (WO / QUOTE # and WO TITLE), Quote # (WO / QUOTE #) and site (SITE)."""
    placeholder = historical.search_placeholder()
    terms = [t.strip().rstrip(".").strip() for t in placeholder.replace("Search", "", 1).split(",") if t.strip().rstrip(".").strip()]
    headers = [h.lower() for h in historical.column_headers()]
    for term in terms:
        assert any(term.lower() in header for header in headers), f"the placeholder names '{term}' and the table has no such column: {headers}"
    row = historical.rows()[0]
    values = {"Quote #": row["quote_no"], "WO (title)": row["title"][:25], "site": row["site"]}
    for label, text in values.items():
        historical.clear()
        historical.search_with_enter(text)
        shown = historical.rows()
        assert row["quote_no"] in [r["quote_no"] for r in shown] or label == "site", f"searching the {label} '{text}' does not find the quotation {row['quote_no']}"
        assert shown, f"searching the {label} '{text}' shows nothing"
        assert all(text.lower() in (r["quote_no"] + " " + r["gsp"] + " " + r["title"] + " " + r["site"]).lower() for r in shown), f"a row shown does not contain '{text}'"
