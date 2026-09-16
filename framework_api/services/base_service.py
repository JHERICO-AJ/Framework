"""BaseService — every service receives the ApiClient and shares helpers."""
from __future__ import annotations


class ApiListResponse:
    """Wraps a raw API payload that may be a plain list, or a dict with the
    list nested under one of a few known keys."""
    LIST_KEYS = ("items", "data", "results", "alarms", "value")

    def __init__(self, payload):
        self._payload = payload

    def items(self):
        if isinstance(self._payload, list):
            return self._payload
        if isinstance(self._payload, dict):
            for key in self.LIST_KEYS:
                if isinstance(self._payload.get(key), list):
                    return self._payload[key]
        return []


class BaseService:
    def __init__(self, client):
        self.client = client
