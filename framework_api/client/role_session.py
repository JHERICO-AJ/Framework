"""RoleApiSession -- an HTTP session logged in (native form endpoint) as ONE Quotation test account.

ApiClient (api_client.py) is GET-only and logs in as the single OmniOps account of .env. The approve/reject rules depend on WHO calls,
so the Quotation API tests need one session per role, able to POST. The login is OmniOps' own POST /api/ExternalUserAuth/login, which
answers 200 and sets the auth_token / refresh_token cookies (confirmed 2026-10-21); the cookies then travel with every call.
Responses are returned as they come (status code + body), because the tests assert the server's refusals.
"""
from __future__ import annotations

import requests

from shared.config.settings import BASE_URL, HTTP_TIMEOUT_S


class RoleApiSession:
    def __init__(self, email, password, base_url=BASE_URL, timeout=HTTP_TIMEOUT_S):
        self.base_url = base_url.rstrip("/")
        self.timeout = max(timeout, 30)
        self.session = requests.Session()
        r = self.session.post(f"{self.base_url}/api/ExternalUserAuth/login", json={"email": email, "password": password}, timeout=self.timeout)
        if r.status_code != 200:
            raise RuntimeError(f"login failed for the role account (HTTP {r.status_code})")
        self.user = r.json()              # id, username, email, role...

    @property
    def user_id(self):
        return self.user["id"]

    @property
    def email(self):
        return self.user["email"]

    def get(self, path, **params):
        return self.session.get(self.base_url + path, params=params or None, timeout=self.timeout)

    def post(self, path, json=None):
        return self.session.post(self.base_url + path, json=json, timeout=self.timeout)

    def post_file(self, path, files=None, timeout=None):
        """A multipart POST (files={'file': (name, bytes, mime)}), for the upload endpoints."""
        return self.session.post(self.base_url + path, files=files, timeout=timeout or self.timeout)


def anonymous_post(path, json=None, base_url=BASE_URL, timeout=HTTP_TIMEOUT_S):
    """A call with no login at all (no cookies)."""
    return requests.post(base_url.rstrip("/") + path, json=json, timeout=max(timeout, 30))
