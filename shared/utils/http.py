"""http.py -- HTTP helper shared by every login mode: a JSON request with timeout and bounded retry on transient network errors."""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request

RETRY_ATTEMPTS = 3          # total tries for a transient network error
RETRY_BACKOFF_S = 0.3       # base backoff; grows linearly per retry


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
