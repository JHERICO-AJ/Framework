"""BaseService — todos los services reciben el ApiClient y comparten helpers."""
from __future__ import annotations


def unwrap(payload):
    """La API puede devolver un array plano o algo envuelto. Devuelve la lista."""
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        for k in ("items", "data", "results", "alarms", "value"):
            if isinstance(payload.get(k), list):
                return payload[k]
    return []


class BaseService:
    def __init__(self, client):
        self.client = client
