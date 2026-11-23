"""LoginPage — login actions. The selectors live in login_locators.py.

OmniOps' /login page offers BOTH a native email/password form and a
"Sign in with Microsoft" button (confirmed 2026-08-28) -- see
login_locators.py's docstring. LOGIN_METHOD (shared/config/settings.py,
.env) picks which one login() uses; defaults to "microsoft" since that's
the credentials currently in .env (a Microsoft account, no MFA on it).
"""
from __future__ import annotations

from framework_ui.base.base_page import BasePage
from framework_ui.pages.auth import login_locators as loc
from shared.config.settings import LOGIN_METHOD


class LoginPage(BasePage):
    PATH = "/login"

    def login(self, email, password, method=None):
        method = method or LOGIN_METHOD
        if method == "native":
            return self._login_native(email, password)
        if method == "microsoft":
            return self._login_microsoft(email, password)
        raise ValueError(f"LOGIN_METHOD must be 'native' or 'microsoft', got {method!r}")

    def _login_native(self, email, password):
        self.goto()
        self.page.fill(loc.EMAIL_INPUT, email)
        self.page.fill(loc.PASSWORD_INPUT, password)
        self.page.click(loc.SUBMIT_BUTTON)
        self.wait_loaded()
        return self

    def _login_microsoft(self, email, password):
        """The "Sign in with Microsoft" button opens the identity platform
        in a POPUP window (confirmed 2026-08-28), not a same-page redirect
        -- MSAL's default popup flow. The opener page (self.page) picks up
        the auth result once the popup completes/closes itself."""
        self.goto()
        with self.page.context.expect_page() as popup_info:
            self.page.click(loc.MS_SIGNIN_BUTTON)
        popup = popup_info.value
        popup.wait_for_load_state()

        popup.fill(loc.MS_EMAIL_INPUT, email)
        popup.click(loc.MS_NEXT_BUTTON)

        popup.fill(loc.MS_PASSWORD_INPUT, password)
        popup.click(loc.MS_SIGNIN_SUBMIT)

        # "Stay signed in?" only shows up sometimes -- don't fail if it doesn't.
        try:
            popup.locator(loc.MS_STAY_SIGNED_IN_NO).wait_for(timeout=5000)
            popup.click(loc.MS_STAY_SIGNED_IN_NO)
        except Exception:
            pass

        # MSAL's popup flow closes the popup itself once auth completes.
        # Don't fail if it stays open -- fall through to wait_loaded() on
        # the main page either way, since that's what proves login worked.
        try:
            popup.wait_for_event("close", timeout=15000)
        except Exception:
            pass

        self.wait_loaded()
        return self
