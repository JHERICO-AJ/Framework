"""
login_page.py — la pantalla de login (email/contraseña).

Todos los selectores del login viven acá. Si el front los renombra, se toca
solo este archivo.
"""

from __future__ import annotations

from config import BASE_URL
from ui.pages.base_page import BasePage


class LoginPage(BasePage):
    URL = f"{BASE_URL}/login"        # ajustar si la pantalla de login es otra

    # --- selectores ---
    USER = "#loginUser"
    PASSWORD = "#loginPassword"
    SUBMIT = "button.login-submit-button"

    def login(self, email, password):
        self.page.goto(self.URL)
        self.page.locator(self.USER).fill(email)
        self.page.locator(self.PASSWORD).fill(password)
        self.page.locator(self.SUBMIT).click()
        self.esperar_carga()
