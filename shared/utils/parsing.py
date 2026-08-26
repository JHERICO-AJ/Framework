"""parsing.py — shared pure parsing/format helpers used across layers."""
from __future__ import annotations

import datetime
import re


def parse_kw(text):
    """'2.486,5 kW' / '2486.5' -> 2486.5 (or None)."""
    if not text:
        return None
    m = re.search(r"-?\d[\d,]*\.?\d*", text.replace(",", ""))
    return float(m.group()) if m else None


def parse_api_datetime(text):
    """'2026-08-18 13:29:15' (UTC) -> UTC-aware datetime (or None)."""
    if not text:
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S.%f"):
        try:
            return datetime.datetime.strptime(text, fmt).replace(
                tzinfo=datetime.timezone.utc)
        except ValueError:
            continue
    return None


def extreme_raw_value(dir_, type_):
    """Extreme raw value to inject depending on direction and type (crosses the
    threshold with any reasonable scale factor). For a negative int16 we use
    two's complement.
    """
    if dir_ == "high":
        return 60000 if type_ == "uint16" else 30000
    # low
    if type_ == "uint16":
        return 0
    return (-30000) & 0xFFFF        # very negative int16, in 16 bits
