"""
test_3capas.py — las 3 capas de la potencia PCS, como prueba pytest.

Mismo fondo que watch_3capas.py (mismo oráculo, mismo anclaje por tiempo, misma
lectura de pantalla con Playwright), pero con envoltorio pytest: corre UNA vez,
da verde/rojo y termina. Ideal para reportes automáticos ("las capas pasan").

Diferencia con watch_3capas.py: el watch se queda en vivo mostrando línea por
línea; esto arranca, muestrea el sistema real unos segundos hasta anclar bien,
asegura, y termina.

Requiere el stack corriendo (simulador + OmniOps) y playwright. Si el simulador
no responde, los tests se SALTAN (no fallan), así pytest no rompe cuando está todo apagado.

Correr:   pytest test_3capas.py -v
"""

import time

import pytest

from core.auth import make_auth
from config import (BASE_URL, SUMMARY_PATH, UI_TOL_KW, GAP_CONFIABLE_S, BUFFER_S)
from core.source_modbus import read_sim_total_kw
from core.omniops_time import parse_epoch
from core.timeanchor import match_buffer, podar
from calc.compare_pcs_power import compare
from ui.ui_reader import UiSession

TIMEOUT_S = 30          # cuánto insistir hasta conseguir una lectura confiable


def _sistema_arriba():
    """¿Responde el simulador? Si no, salteamos (no fallamos) los tests."""
    try:
        read_sim_total_kw()
        return True
    except Exception:
        return False


# si el stack no está corriendo, todos los tests de este archivo se saltan
pytestmark = pytest.mark.skipif(
    not _sistema_arriba(),
    reason="el simulador/OmniOps no están corriendo (levantalos y reintentá)")


@pytest.fixture(scope="module")
def auth():
    return make_auth(BASE_URL)


@pytest.fixture(scope="module")
def ui():
    """Abre el navegador UNA sola vez para todo el módulo y lo cierra al final."""
    sesion = UiSession()
    yield sesion
    sesion.close()


def _leer_api(auth):
    summary = auth.authorized_get(BASE_URL + SUMMARY_PATH)
    dd = summary.get("dispatchDiagnostics") or {}
    return dd.get("actualPcsPower"), dd.get("timestamp")


def _muestra_confiable(auth, timeout=TIMEOUT_S):
    """Junta historial del simulador y lo ancla al timestamp de OmniOps.
    Devuelve (esperado_kw, actual_kw, gap) cuando el anclaje es confiable,
    o None si en todo el timeout nunca bajó del umbral de gap."""
    buffer = []
    t0 = time.time()
    while time.time() - t0 < timeout:
        now = time.time()
        kw, _ = read_sim_total_kw()
        buffer.append((now, kw))
        podar(buffer, now, BUFFER_S)

        actual, ts = _leer_api(auth)
        tep = parse_epoch(ts) if ts else None
        if actual is not None and tep is not None:
            (_, mkw), gap = match_buffer(buffer, tep)
            if gap is not None and gap <= GAP_CONFIABLE_S:
                return mkw, float(actual), gap
        time.sleep(1)
    return None


def test_calculo_pcs_power(auth):
    """Capa CÁLCULO: lo que calcula OmniOps (API) coincide con el oráculo (sim)."""
    muestra = _muestra_confiable(auth)
    assert muestra is not None, (
        "no conseguí una comparación confiable en el tiempo dado "
        "(el gap de anclaje nunca bajó del umbral)")
    esperado, actual, gap = muestra
    ok, diff, ratio, tol = compare(esperado, actual)
    assert ok, (f"OmniOps NO coincide: esperado {esperado:.0f} kW, "
                f"actual {actual:.0f} kW (razón {ratio:.2f}, tol ±{tol:.0f})")


def test_pantalla_pcs_power(auth, ui):
    """Capa PANTALLA: lo que muestra la UI coincide con la API (a 1 decimal).

    Leemos UI y API INTERCALADAS en una ventana corta, para no comparar momentos
    distintos (la potencia se mueve). Pasa apenas la UI coincide con alguna
    lectura reciente de la API; si en toda la ventana nunca coinciden, falla."""
    vistas_api = []
    ultimo_ui = None
    t0 = time.time()
    while time.time() - t0 < 15:
        actual, _ = _leer_api(auth)
        if actual is not None:
            vistas_api.append(round(float(actual), 1))
            vistas_api = vistas_api[-8:]          # ventana de las últimas lecturas

        val, txt = ui.read()
        if val is not None:
            ultimo_ui = round(val, 1)
            if any(abs(ultimo_ui - a) <= UI_TOL_KW for a in vistas_api):
                return                             # coincidió -> PASA
        time.sleep(1)

    assert vistas_api, "la API no devolvió actualPcsPower en la ventana"
    assert ultimo_ui is not None, "la pantalla no mostró un valor usable en la ventana"
    pytest.fail(f"la UI ({ultimo_ui} kW) no coincidió con ninguna lectura reciente "
                f"de la API {vistas_api} en 15s")
