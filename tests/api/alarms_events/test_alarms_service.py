"""Unit test OFFLINE de framework_api (modelo + service), con un client falso.
Corre sin el stack — sirve de smoke en CI. Marcado @pytest.mark.api."""
import json
import os

import pytest

from framework_api.services.alarms_service import AlarmsService
from framework_api.models.alarm import Alarm

FIXTURE = os.path.join(os.path.dirname(__file__), "..", "..", "fixtures",
                       "alarms_sample.json")


def _payload():
    with open(FIXTURE, encoding="utf-8") as f:
        return json.load(f)


class FakeClient:
    """Simula el ApiClient: devuelve el fixture sin tocar la red."""
    def __init__(self, payload):
        self._payload = payload

    def get(self, path, **params):
        return self._payload


@pytest.mark.api
def test_alarm_model_parsea_campos_reales():
    d = _payload()[0]
    a = Alarm.from_json(d)
    assert a.rule_id == d["alarmRuleId"]
    assert a.device_name == d["deviceName"]
    assert a.is_open is (d["status"].lower() == "open")
    # fecha en UTC aware
    assert a.first_occurred is not None
    assert a.first_occurred.tzinfo is not None


@pytest.mark.api
def test_service_devuelve_models_no_dicts():
    svc = AlarmsService(FakeClient(_payload()))
    alarmas = svc.get_alarms()
    assert all(isinstance(a, Alarm) for a in alarmas)


@pytest.mark.api
def test_service_open_rule_ids_y_agrupado():
    svc = AlarmsService(FakeClient(_payload()))
    assert svc.open_rule_ids() == {49, 50, 44}      # del fixture real
    assert len(svc.by_rule_id(50)) == 2             # PCS Comm Lost en 2 devices
