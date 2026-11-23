"""HistoricalQuotes -- reusable component: the landing list of the Quotation module with its tabs, filters, search, table and pager
(OP-12 / HU-05). The list of "Quotes in Progress" is the same component, so the same methods read both tabs.

See historical_quotes_locators.py for everything confirmed live about the markup. The component also listens to the list calls
(GET /api/quotations?...) so the tests can wait until the list has finished loading and can assert WHEN a call is made (for example:
typing in the search box must not search, pressing Enter or leaving the box must) and WITH WHAT (page 1 after a change, the filter values).
"""
from __future__ import annotations

import re
from urllib.parse import parse_qs, urlparse

from playwright.sync_api import TimeoutError as PlaywrightTimeout

from framework_ui.base.base_component import BaseComponent
from framework_ui.pages.quotation.components import historical_quotes_locators as loc

SETTLE_TIMEOUT_MS = 30000
SETTLE_POLL_MS = 100
SETTLE_FIRST_REQUEST_MS = 500
TAB_WAIT_MS = 8000


class HistoricalQuotes(BaseComponent):
    def __init__(self, page):
        super().__init__(page, root=page)
        self.list_calls = []                  # the query of every list call seen since this object was created, as a dict of strings
        self._in_flight = set()
        page.on("request", self._on_request)
        page.on("requestfinished", self._on_request_done)
        page.on("requestfailed", self._on_request_done)

    def detach(self):
        """Stops listening (a page is shared by many tests, so each test that created the component removes its listeners at the end)."""
        self.page.remove_listener("request", self._on_request)
        self.page.remove_listener("requestfinished", self._on_request_done)
        self.page.remove_listener("requestfailed", self._on_request_done)

    # ---- the list calls ---------------------------------------------------------------------------------------------------------
    def _is_list_call(self, request):
        return loc.LIST_API_PATH in request.url and request.method == "GET"

    def _on_request(self, request):
        if self._is_list_call(request):
            self._in_flight.add(request)
            self.list_calls.append({key: values[0] for key, values in parse_qs(urlparse(request.url).query, keep_blank_values=True).items()})

    def _on_request_done(self, request):
        self._in_flight.discard(request)

    def settle(self, timeout_ms=SETTLE_TIMEOUT_MS):
        """Waits until the list is not loading: a short wait for a call to start, then until no list call is in flight."""
        self.page.wait_for_timeout(SETTLE_FIRST_REQUEST_MS)
        waited = 0
        while self._in_flight:
            if waited >= timeout_ms:
                raise TimeoutError("the list was still loading after %d ms" % timeout_ms)
            self.page.wait_for_timeout(SETTLE_POLL_MS)
            waited += SETTLE_POLL_MS
        return self

    def last_call(self):
        return self.list_calls[-1] if self.list_calls else {}

    def calls_since(self, mark):
        """The list calls made after `mark` (a value taken earlier from len(component.list_calls))."""
        return self.list_calls[mark:]

    # ---- tabs --------------------------------------------------------------------------------------------------------------------
    def _tab(self, name):
        return self.page.get_by_role("button").filter(has_text=re.compile(rf"^\s*{re.escape(name)}")).first

    def has_tab(self, name):
        """True when the tab is shown. Waits for it (a slow load must not read as 'no tab'); a role that does not see it waits the full time."""
        try:
            self._tab(name).wait_for(timeout=TAB_WAIT_MS)
            return True
        except PlaywrightTimeout:
            return False

    def tab_label(self, name):
        return " ".join(self._tab(name).inner_text().split())

    def tab_count(self, name):
        """The number in the tab label, or None when the tab shows no number."""
        match = loc.TAB_COUNT_PATTERN.search(self.tab_label(name))
        return int(match.group(1)) if match else None

    def open_historical(self):
        self._tab(loc.TAB_HISTORICAL_TEXT).click()
        return self.settle()

    def open_in_progress(self):
        self._tab(loc.TAB_IN_PROGRESS_TEXT).click()
        return self.settle()

    # ---- toolbar: filters, search, clear ------------------------------------------------------------------------------------------
    def _toolbar(self):
        return self.page.locator("div").filter(has=self.page.get_by_role("button", name=loc.CLEAR_BUTTON_TEXT, exact=True)).filter(has=self.page.locator("select")).last

    def filter_select(self, kind):
        return self._toolbar().locator("select").nth(loc.FILTER_POSITION[kind])

    def filter_options(self, kind):
        """The options of a filter, without the 'All ...' entry and without the 'Loading...' placeholder."""
        self.page.wait_for_function("(el) => !el.disabled", arg=self.filter_select(kind).element_handle(), timeout=20000)
        texts = [text.strip() for text in self.filter_select(kind).locator("option").all_inner_texts()]
        return [text for text in texts if text and text != loc.FILTER_ALL_LABELS[kind] and text != "Loading..."]

    def filter_value(self, kind):
        """The label of the selected option of a filter."""
        return self.filter_select(kind).evaluate("el => el.options[el.selectedIndex].text").strip()

    def has_item_filter(self):
        """True when the toolbar offers the 'Item' (workflow stage) filter -- only 'Quotes in Progress' does."""
        return self._toolbar().locator("select").filter(has=self.page.locator("option", has_text=re.compile(rf"^{loc.ITEM_FILTER_ALL_LABEL}$"))).count() > 0

    def choose_filter(self, kind, label):
        self.filter_select(kind).select_option(label=label)
        return self.settle()

    def search_box(self):
        return self._toolbar().locator("input").first

    def search_placeholder(self):
        return self.search_box().get_attribute("placeholder")

    def search_value(self):
        return self.search_box().input_value()

    def type_in_search(self, text):
        """Types in the search box WITHOUT sending it (no Enter, the box keeps the focus). Returns what the box holds afterwards."""
        box = self.search_box()
        box.click()
        box.fill("")
        box.press_sequentially(text)
        return self.search_value()

    def search_with_enter(self, text):
        self.type_in_search(text)
        self.search_box().press("Enter")
        return self.settle()

    def search_by_leaving(self, text):
        """Types the text and leaves the box with the Tab key."""
        self.type_in_search(text)
        self.search_box().press("Tab")
        return self.settle()

    def search_by_clicking_away(self, text):
        """Types the text and leaves the box by clicking on the list's own title area."""
        self.type_in_search(text)
        self.page.get_by_text("Quotation (WO) Creation").first.click()
        return self.settle()

    def has_search_button(self):
        return self._toolbar().get_by_role("button", name=re.compile(r"search", re.I)).count() > 0

    def clear(self):
        self._toolbar().get_by_role("button", name=loc.CLEAR_BUTTON_TEXT, exact=True).click()
        return self.settle()

    # ---- table -------------------------------------------------------------------------------------------------------------------
    def column_headers(self):
        header = self.page.get_by_text(loc.HEADER_TEXTS[0], exact=True).first.locator("xpath=..")
        return [text.strip() for text in header.locator("> div").all_inner_texts()]

    def rows(self):
        """The rows of the table, in order (the 'Quotes in Progress' tab shows only the quote number in the first cell, so gsp is then empty): dicts with gsp, quote_no, title, site, waiting_on, age, current_step, source and status."""
        return self.page.evaluate("""([rowButton, pill]) => Array.from(document.querySelectorAll(rowButton)).map(b => {
            const cells = Array.from(b.children), clean = e => (e ? e.innerText : '').replace(/\\s+/g, ' ').trim();
            const id = cells[0] ? Array.from(cells[0].querySelectorAll('span')).map(clean) : [];
            const status = b.parentElement.querySelector(pill);
            return {gsp: id.length > 1 ? id[0] : '', quote_no: id.length > 1 ? id[1] : (id[0] || ''), title: clean(cells[1]), site: clean(cells[2]), waiting_on: clean(cells[3]), age: clean(cells[4]),
                    current_step: clean(cells[5]), source: clean(cells[6]), status: clean(status)};
        })""", [loc.ROW_BUTTON, loc.STATUS_PILL])

    def row_for(self, text):
        """The row whose title or quote number contains `text`, or None."""
        return next((row for row in self.rows() if text in row["title"] or text in row["quote_no"] or text in row["gsp"]), None)

    def _row_button(self, text):
        return self.page.locator(loc.ROW_BUTTON).filter(has_text=text).first

    def open_row(self, text):
        self._row_button(text).click()
        return self

    def open_history(self, text):
        self._row_button(text).locator("xpath=..").locator(loc.STATUS_PILL).click()
        return self

    # ---- pager -------------------------------------------------------------------------------------------------------------------
    def pager_text(self):
        """'Page X of Y', or None when the pager is not shown."""
        pager = self.page.get_by_text(loc.PAGER_TEXT_PATTERN).first
        return pager.inner_text().strip() if pager.count() > 0 else None

    def _pager_button(self, text):
        return self.page.get_by_role("button", name=text, exact=True)

    def previous_enabled(self):
        return self._pager_button(loc.PREVIOUS_BUTTON_TEXT).is_enabled()

    def next_enabled(self):
        return self._pager_button(loc.NEXT_BUTTON_TEXT).is_enabled()

    def go_next(self):
        self._pager_button(loc.NEXT_BUTTON_TEXT).click()
        return self.settle()

    def go_previous(self):
        self._pager_button(loc.PREVIOUS_BUTTON_TEXT).click()
        return self.settle()

    # ---- messages ----------------------------------------------------------------------------------------------------------------
    def text_shown(self, text):
        return self.page.get_by_text(text, exact=False).count() > 0

    def wait_for_text(self, text, timeout_ms=20000):
        """True when the text shows up within the time (the page of a role can take a moment to reach the Quotation module)."""
        try:
            self.page.get_by_text(text, exact=False).first.wait_for(timeout=timeout_ms)
            return True
        except PlaywrightTimeout:
            return False

    def body_text(self):
        return self.page.inner_text("body")
