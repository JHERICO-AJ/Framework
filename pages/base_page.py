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
        self.page.wait_for_load_state("networkidle", timeout=timeout)
