"""BrowserFactory — opens/closes Playwright in one place.

Takes the browser's lifecycle out of the reading logic (it used to live inside
UiSession). Used as a context manager, ideal for a pytest fixture:

    with BrowserFactory(headless=True) as page:
        ...
"""
from __future__ import annotations

from shared.config.settings import HEADLESS


class BrowserFactory:
    def __init__(self, headless=HEADLESS):
        self.headless = headless
        self._pw = None
        self.browser = None
        self.context = None
        self.page = None

    def __enter__(self):
        from playwright.sync_api import sync_playwright
        self._pw = sync_playwright().start()
        self.browser = self._pw.chromium.launch(headless=self.headless)
        # ignore_https_errors: the SignalR hub uses a development cert.
        # viewport: confirmed 2026-08-31 that Playwright's default (1280x720)
        # is narrow enough that fixed UI elements (KPI cards, topbar) overlap
        # the Fleet Map region, blocking real (non-force) clicks on markers
        # -- 1920x1080 matches a normal desktop and clears that up.
        self.context = self.browser.new_context(
            ignore_https_errors=True, viewport={"width": 1920, "height": 1080})
        self.context.tracing.start(screenshots=True, snapshots=True, sources=True)
        self.page = self.context.new_page()
        return self.page

    def __exit__(self, *exc):
        for step in (getattr(self.context, "close", None),
                     getattr(self.browser, "close", None),
                     getattr(self._pw, "stop", None)):
            try:
                if step:
                    step()
            except Exception:
                pass
        return False
