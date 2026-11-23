"""OFFLINE unit test of framework_api (model + service), with a fake client.
Runs without the stack — serves as a smoke test in CI. Marked @pytest.mark.api."""
import json
import os

import pytest

from framework_api.services.alarms_service import AlarmsService
from framework_api.models.alarm import Alarm
from tests.api.alarms_events.fakes import FakeClient

FIXTURE = os.path.join(os.path.dirname(__file__), "..", "..", "fixtures",
                       "alarms_sample.json")


def _payload():
    with open(FIXTURE, encoding="utf-8") as f:
        return json.load(f)


@pytest.mark.api
def test_alarm_model_parses_real_fields():
    d = _payload()[0]
    a = Alarm.from_json(d)
    assert a.rule_id == d["alarmRuleId"]
    assert a.device_name == d["deviceName"]
    assert a.is_open is (d["status"].lower() == "open")
    # UTC-aware date
    assert a.first_occurred is not None
    assert a.first_occurred.tzinfo is not None


@pytest.mark.api
def test_service_returns_models_not_dicts():
    svc = AlarmsService(FakeClient(_payload()))
    alarms = svc.get_alarms()
    assert all(isinstance(a, Alarm) for a in alarms)


@pytest.mark.api
def test_service_open_rule_ids_and_grouped():
    svc = AlarmsService(FakeClient(_payload()))
    assert svc.open_rule_ids() == {49, 50, 44}      # from the real fixture
    assert len(svc.by_rule_id(50)) == 2             # PCS Comm Lost on 2 devices
