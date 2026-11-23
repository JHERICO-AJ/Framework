"""OemDecisionService -- the page an external OEM opens from the link of its email (verified 2026-10-26).

The OEM is not an OmniOps user, so these calls carry no login: the token inside the link is the only credential.
  GET  /api/oem-decision/{token}?action=approve|reject -> the confirmation page; it does NOT decide and does NOT use the link
  POST /api/oem-decision/{token}  (form: action, comment) -> records the decision; a link that was already used answers HTTP 409
The token exists only in the email (the database keeps its hash), so a person copies the link from the email and the tests use it here.
A link is accepted only if it points to this environment, and it is never printed or put in an assertion message."""
from __future__ import annotations

import re
from urllib.parse import urlparse

import requests

from shared.config.settings import BASE_URL, HTTP_TIMEOUT_S

DECISION_PATH = "/api/oem-decision/"
MIN_TIMEOUT_S = 30         # the QA environment is sometimes slow


class OemDecisionService:
    def __init__(self, base_url=BASE_URL, timeout=HTTP_TIMEOUT_S):
        self.base_url = base_url.rstrip("/")
        self.timeout = max(timeout, MIN_TIMEOUT_S)

    def token_from_link(self, link):
        """The token of a decision link. Raises ValueError (without echoing the link) if it is not a link of this environment."""
        parsed = urlparse(link.strip())
        if parsed.netloc != urlparse(self.base_url).netloc or not parsed.path.startswith(DECISION_PATH):
            raise ValueError("the link is not an OEM decision link of this environment")
        token = parsed.path[len(DECISION_PATH):].strip("/")
        if not token:
            raise ValueError("the link has no token")
        return token

    def open_page(self, link, action="approve"):
        """What the OEM sees when it clicks a button of the email."""
        return requests.get(f"{self.base_url}{DECISION_PATH}{self.token_from_link(link)}", params={"action": action}, timeout=self.timeout)

    def decide(self, link, action, comment=""):
        """What the OEM sends with 'Confirm decision'. The answer is returned as it comes: the tests assert the refusals too."""
        return requests.post(f"{self.base_url}{DECISION_PATH}{self.token_from_link(link)}", data={"action": action, "comment": comment}, timeout=self.timeout)

    @staticmethod
    def page_text(response):
        """The readable text of an answer page (no styles, no tags, single spaces)."""
        html = re.sub(r"<(style|script)\b.*?</\1>", " ", response.text, flags=re.S | re.I)
        return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html)).strip()
