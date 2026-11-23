"""Test doubles for the alarms_events API tests."""


class FakeClient:
    """Simulates the ApiClient: returns the fixture without touching the network."""
    def __init__(self, payload):
        self._payload = payload

    def get(self, path, **params):
        return self._payload
