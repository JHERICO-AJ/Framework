"""Alarms UI layer: does the /alarms screen show an alarm end to end?

- test_compare_alarms_offline: pure comparison logic, runs without the stack.
- test_injected_alarm_shows_on_screen: live — inject alarm 16, verify OmniOps
  creates it (API) AND that it appears on the /alarms table (UI). Focused on an
  alarm WE control, not on the whole (virtualized) table of pre-existing alarms.
"""
import pytest

from tools.alarms_ui import compare_alarms


# --- offline: pure logic, no browser, no stack ---
class _FakeApiAlarm:
    def __init__(self, name, device, is_open=True):
        self.name = name
        self.device_name = device
        self.is_open = is_open


class _FakeUiRow:
    def __init__(self, name, device):
        self.name = name
        self.device = device


def test_compare_alarms_offline():
    api = [_FakeApiAlarm("Rack High Temp", "RACK-01"),
           _FakeApiAlarm("PCS Phase Loss", "HDS1-PCS03")]
    ui = [_FakeUiRow("Rack High Temp", "RACK-01"),
          _FakeUiRow("Other", "RACK-99")]
    result = compare_alarms(api, ui)
    assert result["in_both"] == {("rack high temp", "rack-01")}
    assert result["api_only"] == {("pcs phase loss", "hds1-pcs03")}   # UI missing it
    assert result["ui_only"] == {("other", "rack-99")}                # phantom row


# --- live: an alarm WE inject must reach API and show on screen ---
ALARM_ID = 16          # Rack High Temp — telemetry, reaches OmniOps end to end


@pytest.mark.cross_layer
def test_injected_alarm_shows_on_screen(require_stack, alarms_service):
    """Inject alarm 16, verify it in the API and on the /alarms screen (ui:YES)."""
    from tools.probar import verify_alarms
    from shared.datasource.modbus_source import LectorModbus

    reader = LectorModbus()
    try:
        results = verify_alarms([ALARM_ID], alarms_service, reader=reader,
                                timeout=60, with_ui=True)
    finally:
        reader.close()

    r = results[0]
    assert r.in_api, f"OmniOps did not create alarm {ALARM_ID} (API): cause={r.cause}"
    assert r.ui_shown, f"alarm {ALARM_ID} is not shown on the /alarms screen"


@pytest.mark.cross_layer
def test_alarm_scene_end_to_end(require_stack, alarms_service):
    """Full end-to-end scene: inject alarm 16, verify it is registered at the
    right time, shown on screen with a matching timestamp, and that after
    clearing the cause is gone and lastOccurred freezes.

    Slow (~90s, opens a browser). Reuses run_scene (same logic as the demo
    command `python -m tools.probar 16 --at 5 --hasta 40`).
    """
    from tools.probar import run_scene

    out = run_scene(ALARM_ID, alarms_service, at=5, until=40)

    assert out.get("time_ok"), "OmniOps did not register the alarm at inject time"
    assert out.get("ui_shown"), "the alarm is not shown on the /alarms screen"
    assert out.get("ui_time_match"), "UI timestamp does not match the API timestamp"
    assert out.get("cause_gone"), "the cause did not disappear from the raw data"
    assert out.get("frozen"), "lastOccurred did not freeze after clearing"
