"""cookie_auth.py — MODE 2: reuses the browser's session cookie (for company
Microsoft login). Reads 'omniops_cookie.txt'."""
from __future__ import annotations

import os
import urllib.error
import urllib.request

from shared.auth.base import Auth, DEFAULT_TIMEOUT_S, request_json


class CookieAuth(Auth):
    def __init__(self, cookie_path="omniops_cookie.txt", timeout=DEFAULT_TIMEOUT_S):
        self.cookie_path = cookie_path
        self.timeout = timeout

    def _load_cookie(self):
        if not os.path.exists(self.cookie_path):
            raise FileNotFoundError(
                f"Missing '{self.cookie_path}'. Paste the session cookie "
                "copied from the browser there (see instructions).")
        cookie = open(self.cookie_path, encoding="utf-8").read().strip()
        if not cookie:
            raise ValueError(f"'{self.cookie_path}' is empty.")
        return cookie

    def authorized_get(self, url):
        req = urllib.request.Request(
            url, headers={"Cookie": self._load_cookie()})
        try:
            return request_json(req, self.timeout)
        except urllib.error.HTTPError as e:
            if e.code in (401, 403):
                raise RuntimeError(
                    "The cookie expired or is not valid. Copy it again from "
                    "the browser into 'omniops_cookie.txt'.") from e
            raise
