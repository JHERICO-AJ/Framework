"""factory.py — picks the login mode on its own.

Since the 2026-08-28 SSO migration, OmniOps' native email/password endpoint
(/api/ExternalUserAuth/login, used by TokenAuth) returns 401 for a
Microsoft-SSO-only account -- it can't validate a Microsoft password
itself. LOGIN_METHOD (same setting framework_ui's LoginPage uses) picks
between the two real modes:
  "native"    -> TokenAuth (MODE 1: POST email/password -> JWT bearer token)
  "microsoft" -> CookieAuth (MODE 2: reuse the browser's SSO session cookie)
CookieAuth's cookie file is generated automatically by a real Playwright
SSO login (see shared/auth/browser_cookie_export.py + tests/conftest.py's
api_client fixture) -- not a manual copy-paste anymore.
"""
from __future__ import annotations

import os

from shared.auth.base import DEFAULT_TIMEOUT_S
from shared.auth.cookie_auth import CookieAuth
from shared.auth.token_auth import TokenAuth
from shared.config.credentials import load_credentials
from shared.config.settings import LOGIN_METHOD


def make_auth(base_url, timeout=DEFAULT_TIMEOUT_S):
    if LOGIN_METHOD == "microsoft":
        return CookieAuth(timeout=timeout)  # cookie file prepared by the api_client fixture
    # Credentials are resolved by credentials.load_credentials(): first the
    # .env / environment variables, and as a compatibility fallback,
    # omniops_login.txt.
    try:
        load_credentials()
    except RuntimeError as e:
        if os.path.exists("omniops_cookie.txt"):
            return CookieAuth(timeout=timeout)
        raise FileNotFoundError(
            f"{e}\n(or, alternatively, an 'omniops_cookie.txt' for Microsoft mode)")
    return TokenAuth(base_url, timeout=timeout)  # uses load_credentials() internally
