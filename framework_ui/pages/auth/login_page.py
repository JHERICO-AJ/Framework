"""LoginPage — login actions. Selectors live in login_locators.py."""
from __future__ import annotations

from framework_ui.base.base_page import BasePage
from framework_ui.pages.auth import login_locators as loc


class LoginPage(BasePage):
    PATH = "/login"

    def login(self, email, password):
        self.goto()
        self.page.fill(loc.EMAIL_INPUT, email)
        self.page.fill(loc.PASSWORD_INPUT, password)
        self.page.click(loc.SUBMIT_BUTTON)
        # esperar a que el login se procese y salgamos de /login.
        # si rebota a /login?session=expired, las credenciales fallaron.
        try:
            self.page.wait_for_url(lambda url: "/login" not in url, timeout=15000)
        except Exception:
            if "session=expired" in self.page.url or "/login" in self.page.url:
                raise RuntimeError(
                    "Login falló: OmniOps rebotó a /login (¿credenciales del .env "
                    "incorrectas, o la cuenta usa login de Microsoft?).")
            raise
        self.wait_loaded()
        return self
