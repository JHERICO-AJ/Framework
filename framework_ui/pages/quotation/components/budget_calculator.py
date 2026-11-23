"""BudgetCalculator -- reusable component: the Budget Calculator sub-window opened by CALCULATE in the FSE Select tab.

Only what HU-15 needs: open it, pick an engineer, type that engineer's figures, confirm, and see which fields can be edited. How it calculates is another story (HU-12).
Observed on the QA build of 2026-10-23: one tab, 'Quotation (Income)'; an engineer selector; Service Fee (hourly rate, total hours, overtime rate, overtime hours), Equipment Purchase
(items: name, qty, price), Travel Expenses (flight, car rental, hotel, meals, gas, parking, toll, other) and Miscellaneous (items); Confirm. The number inputs come in this order:
hourly rate, total hours, overtime rate, overtime hours, equipment qty, equipment price, the eight travel fields, miscellaneous qty, miscellaneous price.
"""
from __future__ import annotations

import re

from framework_ui.base.base_component import BaseComponent

TRAVEL = ["flight", "car", "hotel", "meals", "gas", "parking", "toll", "other"]
SERVICE = ["hourly_rate", "total_hours", "ot_rate", "ot_hours"]


class BudgetCalculator(BaseComponent):
    def __init__(self, page):
        super().__init__(page, root=page)

    def calculate_button(self):
        return self.page.get_by_role("button", name=re.compile("^Calculate$", re.I))

    def modal(self):
        return self.page.locator("div.fixed.inset-0").last

    def open(self):
        self.calculate_button().click()
        self.modal().get_by_text(re.compile(r"^budget calculator$", re.I)).wait_for(timeout=15000)   # the DOM text is mixed case, CSS shows capitals
        self.page.wait_for_timeout(500)
        return self

    def tabs(self):
        return self.modal().evaluate("m => Array.from(m.querySelectorAll('button')).map(b => b.innerText.trim()).filter(t => /Quotation|Expense|Income/i.test(t))")

    def engineer_names(self):
        return self.modal().locator("select option").evaluate_all("o => o.map(x => x.textContent.trim()).filter(t => t && !t.startsWith('—'))")

    def select_engineer(self, name):
        self.modal().locator("select").first.select_option(label=name)
        self.page.wait_for_timeout(400)
        return self

    def numbers(self):
        return self.modal().locator("input[type=number]")

    def fill_figures(self, rate=0, hours=0, ot_rate=0, ot_hours=0, equipment=0, travel=0, misc=0):
        """Types the figures of the selected engineer: equipment and misc as one item of quantity 1 each, `travel` in the Flight field. Zero is left as the screen shows it."""
        n = self.numbers()
        for index, value in enumerate([rate, hours, ot_rate, ot_hours]):
            n.nth(index).fill(str(value))
        if equipment:
            self.modal().get_by_placeholder("Item").first.fill("Tool")
            n.nth(5).fill(str(equipment))
        if travel:
            n.nth(6 + TRAVEL.index("flight")).fill(str(travel))
        if misc:
            self.modal().get_by_placeholder("Item").last.fill("Misc")
            n.nth(15).fill(str(misc))
        self.page.wait_for_timeout(300)
        return self

    def personal_total_text(self):
        return self.modal().get_by_text(re.compile(r"Personal Total:")).first.inner_text()

    def editable_controls(self):
        """Tag names of the inputs, text areas and selects that can be edited."""
        return self.modal().evaluate("m => Array.from(m.querySelectorAll('input,textarea,select')).filter(e => !e.disabled && !e.readOnly).map(e => e.tagName)")

    def disabled_buttons(self):
        return self.modal().evaluate("m => Array.from(m.querySelectorAll('button')).filter(b => b.disabled).map(b => b.innerText.trim())")

    def confirm(self):
        self.modal().get_by_role("button", name="Confirm", exact=True).click()
        self.page.wait_for_timeout(1500)
        return self

    # ---- HU-12: the whole calculator -----------------------------------------------------------------------------------------------------------
    # Fields are found by the block they are in ('1' Service Fee, '2' Equipment Purchase, '3' Travel Expenses, '4' Miscellaneous), not by position: adding a row moves every later input.
    SERVICE_ORDER = ["hourly_rate", "total_hours", "ot_rate", "ot_hours"]
    SECTION_PLUS = {"2": 0, "4": 1}

    def _tag(self):
        self.modal().evaluate("""m => {
            const heads = Array.from(m.querySelectorAll('*')).filter(e => e.children.length === 0 && /^[1-4]\\.\\s/.test(e.textContent.trim()));
            Array.from(m.querySelectorAll('input')).forEach(i => {
                let h = null;
                for (const x of heads) if (x.compareDocumentPosition(i) & Node.DOCUMENT_POSITION_FOLLOWING) h = x;
                i.dataset.qaBlock = h ? h.textContent.trim().charAt(0) : '';
            });
        }""")

    def block_numbers(self, block):
        self._tag()
        return self.modal().locator(f"input[type=number][data-qa-block='{block}']")

    def block_items(self, block):
        self._tag()
        return self.modal().locator(f"input[type=text][data-qa-block='{block}']")

    def service_field(self, name):
        return self.block_numbers("1").nth(self.SERVICE_ORDER.index(name))

    def travel_field(self, name):
        return self.block_numbers("3").nth(TRAVEL.index(name))

    def item_row(self, block, row):
        """(name, qty, price) inputs of row `row` (0-based) of block '2' (Equipment) or '4' (Miscellaneous)."""
        numbers = self.block_numbers(block)
        return self.block_items(block).nth(row), numbers.nth(2 * row), numbers.nth(2 * row + 1)

    def rows(self, block):
        return self.block_items(block).count()

    def plus(self, block):
        return self.modal().locator("button").filter(has_text=re.compile(r"^\+$")).nth(self.SECTION_PLUS[block])

    def type_into(self, field, value):
        field.click()
        field.press("Control+A")
        field.press("Delete")
        field.type(str(value), delay=8)
        return self

    def set_service(self, hourly_rate=None, total_hours=None, ot_rate=None, ot_hours=None):
        for name, value in zip(self.SERVICE_ORDER, (hourly_rate, total_hours, ot_rate, ot_hours)):
            if value is not None:
                self.type_into(self.service_field(name), value)
        return self

    def set_travel(self, **values):
        for name, value in values.items():
            self.type_into(self.travel_field(name), value)
        return self

    def set_item(self, block, row, name=None, qty=None, price=None):
        name_input, qty_input, price_input = self.item_row(block, row)
        if name is not None:
            name_input.fill(name)
        if qty is not None:
            self.type_into(qty_input, qty)
        if price is not None:
            self.type_into(price_input, price)
        return self

    def text(self):
        return re.sub(r"\s+", " ", self.modal().inner_text())

    @staticmethod
    def money(text, label):
        """The number after `label` in `text` ('$1.234' and '$1,234' both read 1234)."""
        m = re.search(label + r"\s*:?\s*\$\s*([\d.,]+)", text)
        assert m, f"{label!r} not found in {text[:300]!r}"
        return int(re.sub(r"[.,]", "", m.group(1)))

    def totals(self):
        """Every total of the sheet in view and of the Grand Total card."""
        t = self.text()
        m = self.money
        return dict(service=m(t, r"(?<!OT )(?<!ALL )SERVICE TOTAL"), ot_service=m(t, r"OT SERVICE TOTAL"), all_service=m(t, r"ALL SERVICE TOTAL"), purchase=m(t, r"Purchase Total"),
                    travel=m(t, r"Travel Total"), misc=m(t, r"Misc Total"), personal=m(t, r"Personal Total"),
                    grand=dict(all_service=m(t, r"All Service"), purchase=m(t, r"Purchase(?! Total)"), travel=m(t, r"Travel(?! Total)"), misc=m(t, r"Misc(?! Total)"), total=m(t, r"Grand Total")))

    def row_total(self, block, row):
        """The TOTAL cell of an item row, read from the rendered text of the row."""
        return int(re.sub(r"[.,]", "", self.item_row(block, row)[1].locator("xpath=ancestor::div[contains(@class,'grid')][1]").inner_text().split("$")[-1].strip() or "0"))

    def selected_engineer(self):
        return self.modal().locator("select").first.evaluate("s => s.options[s.selectedIndex].text")

    def grand_title(self):
        return re.search(r"GRAND TOTAL · ALL ENGINEERS · (QUOTATION \(INCOME\)|EXPENSE)", self.text()).group(0)

    def is_open(self):
        return self.page.get_by_text(re.compile(r"^budget calculator$", re.I)).count() > 0

    def back(self):
        self.modal().get_by_role("button", name=re.compile("Back")).click()
        self.page.wait_for_timeout(500)
        return self

    def escape(self):
        self.page.keyboard.press("Escape")
        self.page.wait_for_timeout(600)
        return self

    def discard_question(self):
        """True while the question 'Discard your budget changes?' is shown."""
        return self.page.get_by_role("button", name="Keep editing").count() > 0 and self.page.get_by_role("button", name="Discard", exact=True).count() > 0

    def keep_editing(self):
        self.page.get_by_role("button", name="Keep editing").click()
        self.page.wait_for_timeout(500)
        return self

    def discard(self):
        self.page.get_by_role("button", name="Discard", exact=True).click()
        self.page.wait_for_timeout(600)
        return self

    def refusal(self):
        """The red message after a refused Confirm ('<Engineer> · <Tab>: Every item ... needs a name.'), or ''."""
        m = re.search(r"[A-Za-z0-9 ]+ · [A-Za-z() ]+: Every item[^.]*\.", re.sub(r"\s+", " ", self.page.locator("body").inner_text()))
        return re.sub(r"^(\d+ )+", "", m.group(0).strip()) if m else ""   # a number typed in a field can be read just before the engineer's name

    def required_marks(self):
        return self.text().count("Required")

    def confirm_button(self):
        return self.modal().get_by_role("button", name="Confirm", exact=True)
