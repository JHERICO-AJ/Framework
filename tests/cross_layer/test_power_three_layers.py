"""cross_layer — el DIFERENCIAL de potencia: simulador vs API vs UI.

Se lee como una frase:
  esperado (oráculo del simulador)  ==  API (lo que OmniOps calcula)  ==  UI (lo que muestra)

Necesita el stack arriba (simulador + OmniOps). Si no, se saltea (require_stack).
El assert vive ACÁ, en el test (no en otra capa).
"""
import time

import pytest

from shared.datasource.modbus_source import read_sim_total_kw
from shared.domain import power
from shared.config.settings import SITE_ID, UI_TOL_KW

pytestmark = pytest.mark.cross_layer

TIMEOUT_S = 30


def _muestra_estable(monitoring_service, intentos=8):
    """Junta lecturas recientes de simulador y API para comparar el mismo momento."""
    for _ in range(intentos):
        sim_kw, _ = read_sim_total_kw()
        summary = monitoring_service.get_summary(SITE_ID)
        api_kw = summary.actual_pcs_power_kw
        if api_kw is not None and power.matches(sim_kw, float(api_kw)):
            return sim_kw, float(api_kw)
        time.sleep(2)
    # última lectura aunque no haya coincidido (para el mensaje de error)
    return sim_kw, (float(api_kw) if api_kw is not None else None)


def test_backend_calcula_bien(require_stack, monitoring_service):
    """Capa CÁLCULO: la API de OmniOps coincide con el oráculo del simulador."""
    expected_kw, api_kw = _muestra_estable(monitoring_service)
    assert api_kw is not None, "la API no devolvió actualPcsPower"
    assert power.matches(expected_kw, api_kw), (
        f"el BACKEND calcula mal: esperado {expected_kw:.0f} kW, "
        f"API {api_kw:.0f} kW")


def test_front_muestra_bien(require_stack, monitoring_service, monitoring_page):
    """Capa PANTALLA: la UI muestra lo mismo que la API (a 1 decimal)."""
    recientes = []
    for _ in range(3):
        s = monitoring_service.get_summary(SITE_ID)
        if s.actual_pcs_power_kw is not None:
            recientes.append(float(s.actual_pcs_power_kw))
        time.sleep(1)
    assert recientes, "la API no devolvió actualPcsPower"

    ui_kw = monitoring_page.read_pcs_power_kw()
    assert ui_kw is not None, "la pantalla no muestra un valor usable"
    assert any(abs(round(ui_kw, 1) - round(a, 1)) <= UI_TOL_KW for a in recientes), (
        f"el FRONT muestra mal: UI {ui_kw} kW vs API reciente {recientes}")
