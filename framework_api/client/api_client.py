"""ApiClient — el ÚNICO punto que habla HTTP con OmniOps.

Auth, base URL, timeout y parseo viven acá. Ningún service ni test hace HTTP
directo: todos pasan por este client. Reusa el auth de shared/.
"""
from __future__ import annotations

from shared.auth.auth import make_auth
from shared.utils.logger import get_logger

log = get_logger("api-client")


class ApiClient:
    def __init__(self, base_url, auth=None):
        self.base_url = base_url.rstrip("/")
        self.auth = auth or make_auth(self.base_url)

    def get(self, path, **params):
        url = self.base_url + path
        log.debug("GET %s %s", url, params or "")
        # authorized_get de shared.auth acepta la URL ya armada
        return self.auth.authorized_get(url)
