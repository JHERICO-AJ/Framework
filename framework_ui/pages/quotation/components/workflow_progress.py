"""WorkflowProgress -- reusable component: the Workflow Progress widget
(OP-25 / HU-07), reachable via the "Open workflow progress" button in the
WO Creation form's header.

See workflow_progress_locators.py's module docstring for everything
confirmed live about this widget (columns, node states, read-only
behavior, the two distinct error states).
"""
from __future__ import annotations

from framework_ui.base.base_component import BaseComponent
from framework_ui.pages.quotation.components import workflow_progress_locators as loc


class WorkflowProgress(BaseComponent):
    def __init__(self, page):
        super().__init__(page, root=page)

    def trigger_button(self):
        return self.page.get_by_role("button", name=loc.TRIGGER_BUTTON_ACCESSIBLE_NAME, exact=False)

    def open(self):
        self.trigger_button().click()
        return self

    def close(self):
        self.page.get_by_role("button", name=loc.MODAL_CLOSE_BUTTON_TEXT, exact=True).click()
        return self

    def current_step_text(self):
        """The modal's own "Current step: X" text (distinct from the
        header trigger button, which embeds the same text in its
        accessible name)."""
        return self.page.locator("p", has_text=loc.CURRENT_STEP_TEXT_PREFIX).inner_text()

    def svg(self):
        return self.page.get_by_role("img", name=loc.SVG_ACCESSIBLE_NAME)

    def node(self, title_text):
        """The clickable node group for a given title (e.g. "WO Quoting"),
        scoped to the diagram so it never collides with the header button
        or the "Current step:" text that repeats the same words."""
        return self.svg().get_by_text(title_text, exact=True)

    def node_status_text(self, title_text):
        """The node's own status line (a real timestamp once completed,
        "Pending" for the current step and any not-yet-reached step).
        Uses text_content(), not inner_text() -- SVG <text> elements don't
        expose the layout box inner_text() relies on."""
        group = self.node(title_text).locator("xpath=..")
        return group.locator("text").nth(2).text_content()

    def is_node_current(self, title_text):
        """True only for the node carrying the current-step glow filter --
        NOT the same as a bright/completed border, which looks similar at
        a glance but has no filter attribute."""
        group = self.node(title_text).locator("xpath=..")
        return group.get_attribute("filter") == f"url(#{loc.CURRENT_GLOW_FILTER_ID})"

    def column_headings(self):
        return [self.svg().get_by_text(h, exact=True) for h in loc.COLUMN_HEADINGS]
