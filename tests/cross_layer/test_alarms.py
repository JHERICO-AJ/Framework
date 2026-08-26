"""cross_layer — alarm INJECTION: injects a condition and verifies that
OmniOps creates it. Reuses verify_alarms (the same logic as the tools.run_check command).

Needs the stack up: sim(5021) + proxy(5020) + edge + OmniOps. If not, it's skipped.
The assert lives HERE, in the test.
"""
import pytest

from tools.run_check import verify_alarms
from shared.domain.verdict import PASS
from shared.datasource.modbus_source import ModbusReader

pytestmark = pytest.mark.cross_layer


def test_inject_rack_high_temp(require_stack, alarms_service):
    """Injects Rack High Temp (telemetry) and verifies OmniOps creates it -> PASS."""
    reader = ModbusReader()
    try:
        results = verify_alarms([16], alarms_service, reader=reader, timeout=60)
    finally:
        reader.close()
    r = results[0]
    assert r.verdict == PASS, (
        f"ID 16 didn't reach PASS: cause={r.cause} api={r.in_api} verdict={r.verdict}")
