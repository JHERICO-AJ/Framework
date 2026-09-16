"""TelemetryDataTable — reusable component: the raw telemetry table (Live
mode) next to the Device Status Panel on Data & Monitoring."""
from __future__ import annotations

from framework_ui.base.base_component import BaseComponent
from framework_ui.pages.monitoring.components import telemetry_data_table_locators as loc
from framework_ui.pages.monitoring.components.telemetry_snapshots_modal import TelemetrySnapshotsModal

# Confirmed 2026-09-09: after switching site, the Live table's first real
# batch of rows can take noticeably longer than the Device Status Panel
# cards (~15-18s observed, vs sub-second for the cards) -- this is NOT the
# 20s LOADED_MARKER-style page-shell wait, it's specific to this
# component's own SignalR-fed row list.
ROWS_APPEAR_TIMEOUT_MS = 30000


class TelemetryDataTable(BaseComponent):
    def column_headers(self):
        """The real underlying header text, e.g. "Timestamp" -- read via
        textContent (evaluate), not inner_text(): the header row is styled
        with CSS text-transform:uppercase, and inner_text() reflects that
        rendered/visual text ("TIMESTAMP"), not the actual DOM text."""
        headers = self.page.locator(loc.HEADER_CELL)
        return [headers.nth(i).evaluate("el => el.textContent").strip() for i in range(headers.count())]

    def subsystem_options(self):
        """Option labels in the subsystem filter dropdown, "All Subsystems"
        included. For a Fractal site, confirmed only 3 real subsystems ever
        appear here (EMS IPC & Gateway, PCS / Inverter, Battery / BMS) --
        HVAC/Meter/Network never generate a row, so they never appear as an
        option either (docs/OF-141.txt: no data -> no row, not a blank one)."""
        options = self.page.locator(loc.SUBSYSTEM_SELECT).locator("option")
        return [options.nth(i).inner_text().strip() for i in range(options.count())]

    def selected_subsystem(self):
        """The currently-selected option's real text (via textContent, same
        text-transform caveat as column_headers())."""
        select = self.page.locator(loc.SUBSYSTEM_SELECT)
        return select.locator("option:checked").evaluate("el => el.textContent").strip()

    def select_subsystem(self, label):
        """`label` is the subsystem's stable name (e.g. "Battery / BMS"),
        without the live row-count suffix the real option text carries
        (e.g. "Battery / BMS (84)") -- select_option(label=...) needs an
        exact match, and that count changes every run, so this matches by
        prefix instead and selects the option's underlying value."""
        options = self.page.locator(loc.SUBSYSTEM_SELECT).locator("option")
        for i in range(options.count()):
            option = options.nth(i)
            if option.evaluate("el => el.textContent").strip().startswith(label):
                self.page.locator(loc.SUBSYSTEM_SELECT).select_option(value=option.get_attribute("value"))
                return self
        raise ValueError(f"no subsystem option starting with {label!r} found in: {self.subsystem_options()}")

    def wait_for_rows(self, timeout=ROWS_APPEAR_TIMEOUT_MS, poll_interval_ms=500):
        """Waits for real data rows to appear. Confirmed 2026-09-09: right
        after switching site, the table shows the empty-state message for
        up to ~10-15s BEFORE the Live feed's first real batch lands -- that
        empty state is transient, not the final answer, so this keeps
        polling past it rather than returning the instant is_empty() is
        momentarily true. Only if no row has appeared by `timeout` does it
        give up and let the caller decide what an empty result means.
        Polls via count() rather than `wait_for_function`: CARD's selector
        uses Playwright-only pseudo-classes (`:has`, `:text-is`), which
        `document.querySelector` inside a browser-evaluated function can't
        parse. Returns self."""
        deadline = self.page.evaluate("Date.now()") + timeout
        while self.rows().count() == 0 and self.page.evaluate("Date.now()") < deadline:
            self.page.wait_for_timeout(poll_interval_ms)
        return self

    def is_empty(self):
        return self.page.locator(loc.EMPTY_STATE).count() > 0

    def rows(self):
        """Real data rows only -- excludes the virtualized list's
        `aria-hidden` spacer row (has no `data-index`)."""
        return self.page.locator(loc.ROW)

    def row_count(self):
        return self.rows().count()

    def row_values(self, index):
        """One row as a {column_header: cell_text} dict, using
        column_headers() for the keys -- Quality's cell holds a `.quality`
        badge span, read as its own text, not the raw cell markup."""
        headers = self.column_headers()
        cells = self.rows().nth(index).locator("td")
        return {header: cells.nth(i).inner_text().strip() for i, header in enumerate(headers)}

    def all_row_values(self):
        """Every currently-rendered real row as a row_values() dict, plus
        its raw "_data_index" (int, the virtualized list's position --
        higher means more recently appended, per CA-04's "oldest top,
        newest bottom"). Only the rows the virtualized list currently has
        mounted are returned, not the full Live buffer -- callers that need
        "the latest row for metric X" should scroll/filter first so the
        row they want is actually rendered.

        Reads every row in ONE evaluate() call, not one Playwright
        round-trip per cell per row: confirmed 2026-09-09 that reading rows
        one at a time (count(), then nth(i).get_attribute(), then
        nth(j).inner_text() per cell) raced against the Live feed
        re-rendering the virtualized list mid-loop (~2s push cycle) --
        by the time a later index was fetched, it no longer existed
        ("Locator.get_attribute: Timeout 30000ms exceeded"). A single
        synchronous browser-side snapshot has no such window."""
        headers = self.column_headers()
        raw_rows = self.page.locator(loc.TABLE).evaluate(
            """table => Array.from(table.querySelectorAll('tbody tr[data-index]')).map(tr => ({
                dataIndex: parseInt(tr.getAttribute('data-index'), 10),
                cells: Array.from(tr.querySelectorAll('td')).map(td => td.textContent.trim()),
            }))"""
        )
        results = []
        for raw in raw_rows:
            values = dict(zip(headers, raw["cells"]))
            values["_data_index"] = raw["dataIndex"]
            results.append(values)
        return results

    def scroll_to_bottom(self):
        """CA-04 (docs/OF-141.txt): Live is oldest-top/newest-bottom, and
        the virtualized list only renders rows near the current scroll
        position -- scroll the container to its end so the actually-latest
        rows (highest _data_index) are the ones mounted, not whatever
        happened to render at the default scroll offset."""
        self.page.locator(loc.SCROLL_CONTAINER).evaluate("el => el.scrollTop = el.scrollHeight")
        return self

    def scroll_to_top(self):
        """CA-04 (docs/OF-141.txt): the oldest rows (lowest _data_index)
        are only mounted when the container is scrolled to its start."""
        self.page.locator(loc.SCROLL_CONTAINER).evaluate("el => el.scrollTop = 0")
        return self

    def latest_row_for_metric(self, metric, device=None):
        """Among currently-rendered rows, the one for `metric` (e.g. "SOC",
        "Active Power") -- optionally narrowed to one `device` (e.g.
        "PCS-1") -- with the highest _data_index, i.e. the most recent one
        currently mounted. Returns None if no such row is rendered right
        now. `device` is optional because a site-aggregate metric's Device
        column holds whatever DeviceCode the gateway device happens to be
        registered under (not a stable, predictable label -- confirmed
        2026-09-09 it can be a data-quality placeholder like
        "00:00:00:00:00:00"), so callers that already filtered to a
        subsystem with exactly one real device (e.g. Battery/BMS on a
        Fractal site) don't need to name it."""
        matches = [r for r in self.all_row_values()
                   if r["Metric"] == metric and (device is None or r["Device"] == device)]
        return max(matches, key=lambda r: r["_data_index"]) if matches else None

    def search_recent_row_for_metric(self, metric, device=None, max_steps=60, step_px=150):
        """Like latest_row_for_metric, but not limited to whatever's
        already mounted at the bottom: the virtualized list only renders
        rows near the current scroll position (~220px tall container), and
        with 3 PCS interleaved chronologically across ~9 metrics each, one
        PCS's latest "Active Power" row can easily be scrolled further up
        than the handful of rows visible right at the bottom. Starts at the
        very bottom (the newest data), then walks upward in small steps,
        stopping at the first (i.e. most recent) match -- same search a
        person would do by hand. Returns None only if nothing matched
        anywhere from the bottom up to `max_steps` * `step_px` back, or the
        container hit its scroll top first. `max_steps=60` (not the 25
        this started with): confirmed 2026-09-09 a long-running test
        session accumulates enough interleaved same-subsystem metric rows
        that 25 steps (3750px) could fall short of reaching a target
        metric's true latest row late in a full-suite run, causing
        intermittent "never matched" failures that always passed in
        isolation -- 60 steps (9000px) gives real headroom."""
        self.scroll_to_bottom()
        match = self.latest_row_for_metric(metric, device=device)
        if match:
            return match

        container = self.page.locator(loc.SCROLL_CONTAINER)
        for _ in range(max_steps):
            at_top = container.evaluate(
                f"el => {{ el.scrollTop = Math.max(0, el.scrollTop - {step_px}); return el.scrollTop === 0; }}")
            self.page.wait_for_timeout(100)
            match = self.latest_row_for_metric(metric, device=device)
            if match:
                return match
            if at_top:
                break
        return None

    def is_scrolled_into_view(self):
        """True if the table is at least partially visible in the current
        viewport -- ground truth for CA-16's "...y baja a la tabla" (a
        card's filter link scrolls the page down to this table)."""
        rect = self.page.locator(loc.SCROLL_CONTAINER).evaluate(
            "el => { const r = el.getBoundingClientRect(); "
            "return {top: r.top, bottom: r.bottom}; }")
        return rect["bottom"] > 0 and rect["top"] < self.page.evaluate("window.innerHeight")

    def browse_snapshots(self) -> TelemetrySnapshotsModal:
        self.page.locator(loc.BROWSE_SNAPSHOTS_BUTTON).click()
        return TelemetrySnapshotsModal(self.page)
