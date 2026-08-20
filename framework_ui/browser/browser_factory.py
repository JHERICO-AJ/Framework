"""BrowserFactory — abre/cierra Playwright en un solo lugar.

Saca el ciclo de vida del navegador de la lógica de lectura (antes vivía dentro
de UiSession). Se usa como context manager, ideal para una fixture de pytest:

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
        # ignore_https_errors: el hub SignalR usa cert de desarrollo
        self.context = self.browser.new_context(ignore_https_errors=True)
        self.page = self.context.new_page()
        return self.page

    def __exit__(self, *exc):
        for paso in (getattr(self.context, "close", None),
                     getattr(self.browser, "close", None),
                     getattr(self._pw, "stop", None)):
            try:
                if paso:
                    paso()
            except Exception:
                pass
        return False
