"""BaseService — every service receives the ApiClient and shares helpers."""
from __future__ import annotations


class BaseService:
    def __init__(self, client):
        self.client = client
