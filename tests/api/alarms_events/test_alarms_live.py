"""LIVE test of the alarms API (needs OmniOps). Returns Alarm models."""
import pytest

from framework_api.models.alarm import Alarm

pytestmark = pytest.mark.api


def test_get_open_alarms_returns_models(require_stack, alarms_service):
    alarms = alarms_service.get_open_alarms()
    assert all(isinstance(a, Alarm) for a in alarms)
    assert all(a.is_open for a in alarms)
