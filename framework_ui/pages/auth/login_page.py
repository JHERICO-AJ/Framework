"""LoginPage — login actions. The selectors live in login_locators.py."""
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
        self.wait_loaded()
        return self
