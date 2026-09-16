"""token_auth.py — MODE 1: email/password -> JWT token. Renews itself. Ideal
for automating and running in real time."""
from __future__ import annotations

import datetime
import json
import urllib.error
import urllib.request

from shared.auth.base import Auth, DEFAULT_TIMEOUT_S, parse_iso_datetime, request_json
from shared.config.credentials import load_credentials


class TokenAuth(Auth):
    def __init__(self, base_url, creds_path="omniops_login.txt", timeout=DEFAULT_TIMEOUT_S):
        self.base_url = base_url.rstrip("/")
        self.creds_path = creds_path
        self.timeout = timeout
        self._token = None
        self._expires_at = None

    def login(self):
        creds = load_credentials()
        url = f"{self.base_url}/api/ExternalUserAuth/login"
        body = json.dumps({"email": creds["email"],
                           "password": creds["password"]}).encode()
        req = urllib.request.Request(
            url, data=body, method="POST",
            headers={"Content-Type": "application/json"})
        data = request_json(req, self.timeout)
        self._token = data["token"]
        self._expires_at = parse_iso_datetime(data.get("expiresAt"))
        return self._token

    def _still_valid(self):
        if not self._token:
            return False
        if self._expires_at is None:
            return True
        now = datetime.datetime.now(datetime.timezone.utc)
        return now < self._expires_at - datetime.timedelta(seconds=15)

    def token(self):
        if not self._still_valid():
            self.login()
        return self._token

    def authorized_get(self, url):
        for attempt in (1, 2):
            token = self.token()
            req = urllib.request.Request(
                url, headers={"Authorization": f"Bearer {token}"})
            try:
                return request_json(req, self.timeout)
            except urllib.error.HTTPError as e:
                if e.code == 401 and attempt == 1:
                    self._token = None   # re-login and retry once
                    continue
                raise
