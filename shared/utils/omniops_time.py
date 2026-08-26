"""
omniops_time.py — OmniOps time parsing, in one place.

`parse_epoch` used to be duplicated in the two watchers. Now it lives here.
Reuses `parse_iso_datetime` from shared.auth.base (which already knew how to
handle the 'Z' and the microseconds).
"""

from __future__ import annotations

from shared.auth.base import parse_iso_datetime


def parse_dt(ts):
    """OmniOps ISO text -> datetime (or None)."""
    return parse_iso_datetime(ts)


def parse_epoch(ts):
    """OmniOps ISO text -> epoch in seconds (float), or None."""
    dt = parse_iso_datetime(ts)
    return dt.timestamp() if dt else None
