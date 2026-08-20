"""
omniops_time.py — parseo de tiempo de OmniOps, en un solo lugar.

Antes `parse_epoch` estaba copiado en los dos watchers. Ahora vive acá.
Reusa `_parse_dt` de auth.py (que ya sabía manejar la 'Z' y los microsegundos).
"""

from __future__ import annotations

from shared.auth.auth import _parse_dt


def parse_dt(ts):
    """Texto ISO de OmniOps -> datetime (o None)."""
    return _parse_dt(ts)


def parse_epoch(ts):
    """Texto ISO de OmniOps -> epoch en segundos (float), o None."""
    dt = _parse_dt(ts)
    return dt.timestamp() if dt else None
