"""BasePage — común a toda página (navegar, esperar carga, ¿estoy en login?)."""
from __future__ import annotations

from shared.config.settings import BASE_URL


class BasePage:
    PATH = "/"

    def __init__(self, page):
        self.page = page

    def goto(self, path=None):
        self.page.goto(BASE_URL + (path or self.PATH))
        self.wait_loaded()
        return self

    def wait_loaded(self, timeout=15000):
        # NO usar "networkidle": con SignalR el WebSocket queda abierto y nunca llega.
        self.page.wait_for_load_state("domcontentloaded", timeout=timeout)

    def is_on_login(self):
        return "/login" in self.page.url
