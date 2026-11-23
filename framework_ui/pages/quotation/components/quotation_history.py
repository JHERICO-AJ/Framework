"""QuotationHistory -- reusable component: the "Quotation workflow" history drawer that opens from the Status of a row of the AM's list (OP-13 / HU-06).

See quotation_history_locators.py for everything confirmed live about its markup. The component reads the drawer as data (summary card, phase groups and entries) so
the tests compare it with what the API says about the same quotation, and it counts the calls to GET /api/quotations/{id}/events to check that every opening reloads.
"""
from __future__ import annotations

import re

from playwright.sync_api import TimeoutError as PlaywrightTimeout

from framework_ui.base.base_component import BaseComponent
from framework_ui.pages.quotation.components import quotation_history_locators as loc

LOAD_TIMEOUT_MS = 30000
CLOSE_TIMEOUT_MS = 5000
OUTSIDE_CLICK_POINT = (300, 420)          # on the table behind the drawer (the drawer takes the right 400 px of a 1600 px wide window)


class QuotationHistory(BaseComponent):
    def __init__(self, page):
        super().__init__(page, root=page)
        self.events_calls = 0
        page.on("request", self._on_request)

    def detach(self):
        self.page.remove_listener("request", self._on_request)

    def _on_request(self, request):
        if request.method == "GET" and loc.EVENTS_API_PATTERN.match(request.url):
            self.events_calls += 1

    # ---- the drawer ------------------------------------------------------------------------------------------------------------
    def dialog(self):
        return self.page.get_by_role(loc.DIALOG_ROLE).first

    def is_open(self):
        dialog = self.page.get_by_role(loc.DIALOG_ROLE)
        return dialog.count() > 0 and dialog.first.is_visible()

    def wait_open(self, timeout_ms=10000):
        self.dialog().wait_for(state="visible", timeout=timeout_ms)
        return self

    def wait_closed(self, timeout_ms=CLOSE_TIMEOUT_MS):
        try:
            self.page.get_by_role(loc.DIALOG_ROLE).first.wait_for(state="detached", timeout=timeout_ms)
            return True
        except PlaywrightTimeout:
            return False

    def wait_loaded(self, timeout_ms=LOAD_TIMEOUT_MS):
        """Waits until the drawer shows the history or the error (not 'Loading history...')."""
        self.wait_open()
        self.page.get_by_text(loc.LOADING_TEXT).wait_for(state="detached", timeout=timeout_ms)
        self.page.wait_for_timeout(300)
        return self

    def text(self):
        return self.dialog().inner_text()

    def lines(self):
        return [line.strip() for line in self.text().split("\n") if line.strip()]

    def is_modal(self):
        return self.dialog().get_attribute("aria-modal") == "true"

    def box(self):
        return self.dialog().bounding_box()

    def backdrop(self):
        """The dark layer behind the drawer: its colour and its box."""
        return self.page.evaluate("""() => {
            const layer = Array.from(document.querySelectorAll('div')).find(e => { const s = getComputedStyle(e);
                return s.position === 'fixed' && e.getAttribute('role') !== 'dialog' && parseFloat(s.zIndex) >= 1000 && e.getBoundingClientRect().width >= window.innerWidth - 2; });
            if (!layer) return null;
            const box = layer.getBoundingClientRect();
            return {color: getComputedStyle(layer).backgroundColor, width: box.width, height: box.height};
        }""")

    # ---- closing -----------------------------------------------------------------------------------------------------------------
    def close_with_button(self):
        self.dialog().get_by_role("button", name=loc.CLOSE_BUTTON_TEXT, exact=True).click()
        return self.wait_closed()

    def close_with_escape(self):
        self.page.keyboard.press("Escape")
        return self.wait_closed()

    def close_by_clicking_outside(self):
        self.page.mouse.click(*OUTSIDE_CLICK_POINT)
        return self.wait_closed()

    def close_quietly(self):
        """Closes the drawer if it is open (cleanup of a test)."""
        if self.is_open():
            self.page.keyboard.press("Escape")
            self.wait_closed()

    # ---- header and summary card -------------------------------------------------------------------------------------------------
    def title(self):
        return self.dialog().locator("h2").first.text_content().strip()        # the screen draws it in capitals with CSS; the text itself is 'Quotation workflow'

    def quote_label(self):
        """The line under the title: the Quote #, or 'Draft · no Quote #'."""
        return self.dialog().locator("header p").first.inner_text().strip()

    def summary(self):
        """{'Status': ..., 'Current phase': ..., 'Waiting on': ...} of the summary card (the colon of 'Waiting on:' is removed)."""
        return self.dialog().evaluate("""dialog => {
            const out = {};
            dialog.querySelectorAll('dl > div').forEach(row => {
                const key = row.querySelector('dt').textContent.trim().replace(/:$/, '');
                out[key] = row.querySelector('dd').innerText.replace(/\\s+/g, ' ').trim();
            });
            return out;
        }""")

    # ---- timeline ----------------------------------------------------------------------------------------------------------------
    def groups(self):
        """The phase groups in screen order: [{'title': ..., 'entries': [{actor, role, here, action, reason, note, date, others}]}]."""
        return self.dialog().evaluate("""dialog => {
            const text = e => (e ? e.innerText.replace(/[ \\t]+\\n/g, '\\n').trim() : '');
            return Array.from(dialog.querySelectorAll(':scope > div > ol > li')).map(group => ({
                title: text(group.querySelector(':scope > h3')),
                entries: Array.from(group.querySelectorAll(':scope > ol > li')).map(li => {
                    const head = li.querySelector(':scope > div');
                    const chips = head ? Array.from(head.querySelectorAll(':scope > span')) : [];
                    const entry = {actor: text(chips[0]), role: text(chips[1]), here: chips.slice(2).some(c => /^here$/i.test(text(c))), action: '', reason: '', note: '', date: '', others: []};
                    Array.from(li.children).forEach(child => {
                        if (child === head || child.tagName === 'SPAN') return;
                        const cls = child.className || '';
                        if (child.tagName === 'P' && cls.includes('inline-flex')) entry.action = text(child);
                        else if (child.tagName === 'P' && cls.includes('font-mono')) entry.date = text(child);
                        else if (child.tagName === 'P' && cls.includes('whitespace-pre-line')) entry.reason = text(child);
                        else if (child.tagName === 'P') entry.note = text(child);
                        else entry.others.push(text(child));
                    });
                    return entry;
                })
            }));
        }""")

    def entries(self):
        """Every entry of the timeline, flat, in screen order, with the title of its phase group."""
        return [{**entry, "phase": group["title"]} for group in self.groups() for entry in group["entries"]]

    def group_titles(self):
        return [group["title"] for group in self.groups()]

    def entries_of(self, action):
        return [entry for entry in self.entries() if entry["action"] == action]

    def here_entries(self):
        return [entry for entry in self.entries() if entry["here"]]

    # ---- long reasons ------------------------------------------------------------------------------------------------------------
    def reason_locator(self, index=0):
        return self.dialog().locator("p.whitespace-pre-line").nth(index)

    def reason_metrics(self, index=0):
        """How the reason is laid out: its box height, the height of its full text, and its width against the width of its text (a text wider than its box is cut)."""
        return self.reason_locator(index).evaluate("""e => {
            const range = document.createRange(); range.selectNodeContents(e);
            return {height: e.getBoundingClientRect().height, fullHeight: e.scrollHeight, width: e.clientWidth, scrollWidth: e.scrollWidth,
                    lineHeight: parseFloat(getComputedStyle(e).lineHeight), text: e.textContent.length};
        }""")

    def toggle_button(self, name):
        return self.dialog().get_by_role("button", name=name, exact=True)

    def has_toggle(self, name):
        return self.toggle_button(name).count() > 0

    def click_toggle(self, name):
        self.toggle_button(name).click()
        self.page.wait_for_timeout(250)
        return self

    # ---- scrolling ---------------------------------------------------------------------------------------------------------------
    def scroll_metrics(self):
        """The scroll area of the drawer: its visible height and the height of its content, and the drawer's own height."""
        return self.dialog().evaluate("""dialog => {
            const area = dialog.querySelector(':scope > div');
            return {clientHeight: area.clientHeight, scrollHeight: area.scrollHeight, overflowY: getComputedStyle(area).overflowY, dialogHeight: dialog.getBoundingClientRect().height,
                    scrollWidth: area.scrollWidth, clientWidth: area.clientWidth};
        }""")

    def scroll_to_end(self):
        self.dialog().evaluate("dialog => { const area = dialog.querySelector(':scope > div'); area.scrollTop = area.scrollHeight; }")
        return self
