"""cross_layer — INYECCIÓN de alarmas: inyecta una condición y verifica que
OmniOps la cree. Reusa verify_alarms (la misma lógica que el comando tools.probar).

Necesita la cadena arriba: sim(5021) + proxy(5020) + edge + OmniOps. Si no, se saltea.
El assert vive ACÁ, en el test.
"""
import pytest

from tools.probar import verify_alarms
from shared.domain.verdict import PASA
from shared.datasource.modbus_source import LectorModbus

pytestmark = pytest.mark.cross_layer


def test_inject_rack_high_temp(require_stack, alarms_service):
    """Inyecta Rack High Temp (telemetría) y verifica que OmniOps la cree -> PASA."""
    reader = LectorModbus()
    try:
        results = verify_alarms([16], alarms_service, reader=reader, timeout=60)
    finally:
        reader.close()
    r = results[0]
    assert r.verdict == PASA, (
        f"ID 16 no llegó a PASA: causa={r.cause} api={r.in_api} veredicto={r.verdict}")
