"""ApiClient — the ONLY point that speaks HTTP with OmniOps.

Auth, base URL, timeout, and parsing live here. No service or test makes an
HTTP call directly: they all go through this client. Reuses the auth from
shared/.
"""
from __future__ import annotations

from shared.auth.factory import make_auth
from shared.config.settings import HTTP_TIMEOUT_S
from shared.utils.logger import get_logger

log = get_logger("api-client")


class ApiClient:
    def __init__(self, base_url, auth=None, timeout=HTTP_TIMEOUT_S):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.auth = auth or make_auth(self.base_url, timeout=timeout)

    def get(self, path, **params):
        url = self.base_url + path
        log.debug("GET %s %s", url, params or "")
        # authorized_get from shared.auth accepts the already-built URL
        return self.auth.authorized_get(url)
