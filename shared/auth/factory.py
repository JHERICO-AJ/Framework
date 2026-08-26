"""factory.py — picks the login mode on its own, based on which credentials
file you have created in the folder. Neither mode writes anything to
OmniOps: they only read."""
from __future__ import annotations

import os

from shared.auth.base import DEFAULT_TIMEOUT_S
from shared.auth.cookie_auth import CookieAuth
from shared.auth.token_auth import TokenAuth
from shared.config.credentials import load_credentials


def make_auth(base_url, timeout=DEFAULT_TIMEOUT_S):
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
