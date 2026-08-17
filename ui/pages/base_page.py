"""
base_page.py — lo común a todas las páginas del POM.

No sabe de selectores concretos; solo da utilidades que toda página usa.
"""

from __future__ import annotations


class BasePage:
    def __init__(self, page):
        self.page = page

    def esta_en_login(self):
        """True si OmniOps nos pateó (o dejó) en la pantalla de login."""
        return "login" in (self.page.url or "")

    def esperar_carga(self, timeout=15000):
        # OJO: NO usar "networkidle". Con SignalR conectado, el WebSocket queda
        # abierto siempre y "networkidle" nunca se cumple -> agota el timeout.
        # Esperamos que el DOM cargue; el dato lo espera el wait_for del elemento.
        self.page.wait_for_load_state("domcontentloaded", timeout=timeout)
