"""Test EN VIVO de la API de alarmas (necesita OmniOps). Devuelve models Alarm."""
import pytest

from framework_api.models.alarm import Alarm

pytestmark = pytest.mark.api


def test_get_open_alarms_devuelve_models(require_stack, alarms_service):
    alarmas = alarms_service.get_open_alarms()
    assert all(isinstance(a, Alarm) for a in alarmas)
    assert all(a.is_open for a in alarmas)
