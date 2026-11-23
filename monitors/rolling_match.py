"""RollingMatch -- keeps a short history of simulator samples and tells whether a UI value matches any of them."""

from __future__ import annotations

import time
from collections import deque

# How much recent simulator history to keep per field, and for how long a
# match is still considered "in sync" rather than stale -- same numbers as
# the pytest convergence window (POWER_HISTORY_DURATION_S/MAX_LATENCY_S).
HISTORY_WINDOW_S = 120
STALE_AFTER_S = 300


class RollingMatch:
    """Keeps a rolling window of (timestamp, value) simulator samples for
    one field, and reports whether a given reading matches ANY sample still
    within HISTORY_WINDOW_S -- the live equivalent of the pytest
    convergence-window loop, but never stops: old samples just age out."""

    def __init__(self, tolerance):
        self.tolerance = tolerance
        self.samples = deque()  # [(monotonic_time, value), ...]

    def add_sample(self, value):
        now = time.monotonic()
        self.samples.append((now, value))
        while self.samples and now - self.samples[0][0] > HISTORY_WINDOW_S:
            self.samples.popleft()

    def check(self, reading):
        """Returns (ok, latency_s, matched_sim_value) -- the matched value
        is what makes two independently-timed reads visually "go hand in
        hand": even though the UI/API number was captured a few seconds
        after that simulator sample, printing THAT exact matched number
        next to it proves they're the same underlying reading, not a
        coincidence of rounding."""
        if reading is None:
            return None, None, None
        match = next(((t, v) for t, v in reversed(self.samples) if abs(v - reading) <= self.tolerance), None)
        if match is None:
            return False, None, None
        matched_time, matched_value = match
        latency_s = time.monotonic() - matched_time
        return latency_s <= STALE_AFTER_S, latency_s, matched_value
