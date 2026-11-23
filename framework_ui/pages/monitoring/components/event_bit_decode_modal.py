"""EventBitDecodeModal -- the modal opened from its card."""

from __future__ import annotations

from framework_ui.base.base_component import BaseComponent
from framework_ui.pages.monitoring.components import raw_event_bit_viewer_locators as loc


class EventBitDecodeModal(BaseComponent):
    def title(self):
        return self.page.locator(loc.MODAL_TITLE).inner_text().strip()

    def subtitle(self):
        return self.page.locator(loc.MODAL_SUBTITLE).inner_text().strip()

    def summary_words(self):
        """{"Evt1": "—", "Evt2": "—", "PcsEvt1": "00000010"} -- the 3
        compacted words repeated at the top of the modal (CA-12)."""
        words = self.page.locator(loc.DECODE_SUMMARY_WORD)
        values = {}
        for i in range(words.count()):
            w = words.nth(i)
            label = w.locator(loc.BIT_LABEL).inner_text().strip()
            value = w.locator(loc.BIT_VALUE).inner_text().strip()
            values[label] = value
        return values

    def snapshot_meta_text(self):
        """"Snapshot · {local date/time}" (CA-13), or None if no
        timestamp is present in the snapshot."""
        meta = self.page.locator(loc.DECODE_SUMMARY_META)
        return meta.inner_text().strip() if meta.count() else None

    def set_bit_count_text(self):
        """The "N set bit(s)" summary line above the grouped tables."""
        el = self.page.locator(loc.DECODE_COUNT)
        return el.inner_text().strip() if el.count() else None

    def groups(self):
        return self.page.locator(loc.DECODE_GROUP)

    def group_field_names(self):
        titles = self.page.locator(f"{loc.DECODE_GROUP} {loc.DECODE_GROUP_FIELD_TITLE}")
        return [titles.nth(i).inner_text().strip() for i in range(titles.count())]

    def rows_for_group(self, field_name):
        group = self.groups().filter(has=self.page.locator(loc.DECODE_GROUP_FIELD_TITLE, has_text=field_name))
        return group.locator(loc.DECODE_TABLE_ROW)

    def row_values(self, field_name, index):
        """[Bit, Label, Alarm rule, Raw] for one row in a field's group table."""
        cells = self.rows_for_group(field_name).nth(index).locator("td")
        return [cells.nth(i).inner_text().strip() for i in range(cells.count())]

    def close(self):
        self.page.locator(loc.MODAL_CLOSE_BUTTON).first.click()
        self.page.locator(loc.OVERLAY).wait_for(state="hidden")
        return self
