"""BudgetSummary -- reusable component: the Budget Summary panel in the footer of a quotation (HU-15 / OP-23)."""
from __future__ import annotations

import re

from framework_ui.base.base_component import BaseComponent
from framework_ui.pages.quotation.components import budget_summary_locators as loc
from framework_ui.pages.quotation.components.sheet_line import SheetLine


def number(text):
    """'$5.500' / '$5,500' / '$5500' / '1 200' -> 5500 / 1200 (the thousands separator depends on the browser language)."""
    digits = re.sub(r"[^\d-]", "", text or "")
    return int(digits) if digits not in ("", "-") else None


class BudgetSummary(BaseComponent):
    def __init__(self, page):
        super().__init__(page, root=page)

    # ---- button and panel -------------------------------------------------------------------------------
    def button(self):
        return self.page.get_by_role("button", name=re.compile(rf"^\W*(Hide )?{loc.BUTTON_OPEN_TEXT}$"))

    def button_text(self):
        return " ".join(self.button().first.inner_text().split()).lstrip("▲▼ ").strip()

    def has_button(self):
        return self.button().count() > 0

    def is_open(self):
        """The panel is open exactly when the footer button reads 'Hide Budget Summary' (the title text 'Budget Summary' also appears inside the
        closed button, and CSS shows the panel title in capitals while the DOM text is mixed case, so the title cannot tell open from closed)."""
        return self.page.get_by_role("button", name=re.compile(rf"{loc.BUTTON_HIDE_TEXT}$")).count() > 0

    def open(self):
        if not self.is_open():
            self.button().first.click()
        self.page.locator(loc.SHEET_TABLE).first.wait_for(timeout=10000)
        self.page.wait_for_timeout(400)
        return self

    def close_with_button(self):
        self.page.get_by_role("button", name=re.compile(rf"^{loc.CLOSE_BUTTON_TEXT}")).first.click()
        self.page.wait_for_timeout(400)
        return self

    # ---- tabs ----------------------------------------------------------------------------------------------
    def select_tab(self, name):
        self.page.get_by_role("button", name=name, exact=True).click()
        self.page.wait_for_timeout(500)
        return self

    def active_tab(self):
        """'OEM View' when the sheet has no header row, otherwise 'BU View' (the two tabs differ in exactly that)."""
        return "BU View" if self.header() else "OEM View"

    def _panel_root(self):
        """The panel element: the closest ancestor of the figures table that also holds the 'Close' button."""
        return self.page.locator(loc.SHEET_TABLE).first.locator("xpath=ancestor::div[.//button[starts-with(normalize-space(.), 'Close')]][1]")

    def input_count(self):
        """How many inputs, text areas and selects the panel holds (the three cards are read-only, so none)."""
        return self._panel_root().locator("input, textarea, select").count()

    def box_of_panel_and_button(self):
        """Bounding boxes of the panel and of the footer button, to check that the panel sits above the footer."""
        return self._panel_root().bounding_box(), self.button().first.bounding_box()

    # ---- the three cards ----------------------------------------------------------------------------------
    def cards(self):
        """{'EST. START TIME': '10/01/2026', 'EST. END TIME': ..., 'SUPPORT ENGINEERS': '2'}"""
        return self.page.evaluate("""() => {
            const out = {};
            for (const label of ['EST. START TIME', 'EST. END TIME', 'SUPPORT ENGINEERS', 'PLANNED CHECK-IN', 'PLANNED CHECK-OUT']) {
                const el = Array.from(document.querySelectorAll('*')).filter(e => e.children.length === 0 && (e.textContent || '').trim().toUpperCase() === label).pop();
                if (el && el.parentElement) {
                    const rest = Array.from(el.parentElement.querySelectorAll('*')).filter(e => e !== el && e.children.length === 0).map(e => e.value || e.textContent.trim()).filter(Boolean);
                    out[label] = rest[0] ?? '';
                }
            }
            return out;
        }""")

    # ---- the sheet ----------------------------------------------------------------------------------------
    def raw_rows(self):
        """Every row of the figures table as {'cells': [text...], 'spans': [colSpan...]}."""
        return self.page.locator(loc.SHEET_TABLE).first.evaluate("""t => Array.from(t.rows).map(r => ({
            cells: Array.from(r.cells).map(c => c.innerText.replace(/\\s+/g, ' ').trim()), spans: Array.from(r.cells).map(c => c.colSpan)}))""")

    def header(self):
        """The header row cells ('Description', 'Quotation/Revenue', 'Expense'), or None when the sheet has no header row (OEM View)."""
        rows = self.raw_rows()
        first = rows[0]["cells"] if rows else []
        return first if first and first[0] == "Description" else None

    def lines(self):
        """The figure lines of the sheet in order, each with its section (taken from the title rows) and its cells."""
        rows = self.raw_rows()
        header = self.header()
        has_expense = bool(header) and len(header) >= 3
        section, out = "", []
        for row in rows[1 if header else 0:]:
            cells, spans = row["cells"], row["spans"]
            if len(cells) == 1 and cells[0] in loc.SECTION_TITLES:
                section = cells[0]
                continue
            if not any(cells):
                continue
            label = cells[0]
            quotation = cells[1] if len(cells) > 1 else ""
            expense = cells[2] if len(cells) > 2 else ("" if has_expense else None)
            out.append(SheetLine('' if label == 'Total Cost' else section, label, quotation, expense, spans_both=len(cells) == 2 and spans[1] > 1))
        return out

    def line(self, section, label):
        found = [ln for ln in self.lines() if ln.label == label and (section is None or ln.section == section)]
        if len(found) != 1:
            raise AssertionError(f"expected one '{label}' line in section {section!r}, found {len(found)}")
        return found[0]

    def footer_total(self):
        """The text of the quotation Total shown in the footer (e.g. '$8.410' or '—'); the 'Total' cells inside the sheet are skipped."""
        return self.page.evaluate("""() => {
            const leaves = Array.from(document.querySelectorAll('*')).filter(e => e.children.length === 0 && !e.closest('table') && (e.textContent || '').trim().toUpperCase() === 'TOTAL');   // not the 'Total' cells of the sheet
            const el = leaves[leaves.length - 1];
            if (!el || !el.parentElement) return '';
            return el.parentElement.innerText.replace(/TOTAL/i, '').trim();
        }""")

    # ---- the FSE Select (Variable Rate) sheet ---------------------------------------------------------------
    def select_sheet(self):
        """The sheet of an FSE Select quotation: {'header': [...], 'has_expense': bool, 'blocks': [{'name', 'lines': {label: (quotation, expense|None)}}], 'final': (quotation, expense|None)}.
        The first row is ['', '', 'Quotation'(, 'Expense')]; every engineer block starts with a row ['<name>', 'Service Fee', ...] and ends with 'Total'; the last row is ['', 'Final Total', ...]."""
        rows = [r["cells"] for r in self.raw_rows()]
        header = rows[0]
        has_expense = len(header) >= 4
        blocks, final = [], None
        for cells in rows[1:]:
            if len(cells) > 1 and cells[1] == "Final Total":
                final = (cells[2], cells[3] if has_expense else None)
            elif len(cells) > 1 and cells[1] == "Service Fee":
                blocks.append({"name": cells[0], "lines": {"Service Fee": (cells[2], cells[3] if has_expense else None)}})
            elif blocks and cells:
                blocks[-1]["lines"][cells[0]] = (cells[1], cells[2] if has_expense else None)
        return {"header": header, "has_expense": has_expense, "blocks": blocks, "final": final}

    def empty_sheet_message(self):
        """The text shown instead of the sheet when no engineer is selected ('' if the sheet is shown)."""
        texts = self.page.evaluate("() => Array.from(document.querySelectorAll('*')).filter(e => e.children.length === 0).map(e => e.textContent.trim()).filter(t => /No engineers selected yet - pick/i.test(t))")
        return texts[0] if texts else ""
