"""base.py — the Auth contract and the internal HTTP helpers shared by every
login mode (timeout + bounded retry on transient network errors)."""
from __future__ import annotations

import json
import re
import time
import urllib.error
import urllib.request
from abc import ABC, abstractmethod
import datetime

DEFAULT_TIMEOUT_S = 10
RETRY_ATTEMPTS = 3          # total tries for a transient network error
RETRY_BACKOFF_S = 0.3       # base backoff; grows linearly per retry


def parse_iso_datetime(iso_text):
    if not iso_text:
        return None
    try:
        iso_text = iso_text.replace("Z", "+00:00")
        iso_text = re.sub(r"(\.\d{6})\d+", r"\1", iso_text)
        return datetime.datetime.fromisoformat(iso_text)
    except Exception:
        return None


def request_json(req, timeout):
    """Runs req and parses the JSON response. Retries a bounded number of
    times on transient network errors (timeouts, connection issues, 5xx).
    Does NOT retry on 4xx — those are the caller's problem (bad auth, etc.)."""
    last_error = None
    for attempt in range(1, RETRY_ATTEMPTS + 1):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as response:
                return json.loads(response.read().decode())
        except urllib.error.HTTPError as e:
            if 400 <= e.code < 500:
                raise
            last_error = e
        except (urllib.error.URLError, TimeoutError) as e:
            last_error = e
        if attempt < RETRY_ATTEMPTS:
            time.sleep(RETRY_BACKOFF_S * attempt)
    raise last_error


class Auth(ABC):
    """The gatekeeper. Any login mode implements authorized_get()."""
    @abstractmethod
    def authorized_get(self, url):
        ...
