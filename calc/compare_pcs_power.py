"""
compare_pcs_power.py — TEST DIFERENCIAL: simulador vs OmniOps.

Oráculo (fuente confiable, según el documento del equipo): la potencia total de
los PCS se calcula sumando la potencia POR PCS del Model 103 (que llega correcta).
Actual: el actualPcsPower que muestra OmniOps.

Compara los dos y muestra la razón entre ellos. Si OmniOps usara el agregado con
el bug de escala documentado (§10), la razón daría ~1000 (o ~0.001). Si usa el
camino bueno, la razón da ~1.

La lectura del simulador vive ahora en source_modbus.py (fuente única).
SOLO LEE. Necesita: pymodbus y el simulador corriendo.

Correr:            python compare_pcs_power.py
Probar la lógica:  python compare_pcs_power.py --self-check
"""

import sys

from core.auth import make_auth
from config import BASE_URL, SUMMARY_PATH, TOL_ABS_KW, TOL_REL
from core.source_modbus import signed16, w_to_kw, read_sim_total_kw


def compare(expected_kw, actual_kw):
    diff = actual_kw - expected_kw
    ratio = (actual_kw / expected_kw) if expected_kw else float("inf")
    tol = max(TOL_ABS_KW, abs(expected_kw) * TOL_REL)
    ok = abs(diff) <= tol
    return ok, diff, ratio, tol


def report(expected_kw, actual_kw, detalle):
    print("\n--- ORÁCULO (simulador, suma por PCS) ---")
    for addr, kw in detalle:
        print(f"    PCS reg {addr}: {kw:9.1f} kW")
    print(f"    TOTAL esperado: {expected_kw:9.1f} kW")
    print(f"\n--- ACTUAL (OmniOps API) ---")
    print(f"    actualPcsPower: {actual_kw:9.1f} kW")
    ok, diff, ratio, tol = compare(expected_kw, actual_kw)
    print(f"\n    diferencia: {diff:+.1f} kW   (tolerancia ±{tol:.0f} kW)")
    print(f"    razón actual/esperado: {ratio:.3f}")
    if ok:
        print("\n=> PASA ✓  OmniOps coincide con el oráculo (usa el camino correcto)")
    elif ratio and (ratio < 0.01 or ratio > 100):
        print("\n=> BUG DE ESCALA <<<  la razón es enorme: OmniOps parece usar el "
              "agregado roto (~1000x, ver §10 del documento)")
    else:
        print("\n=> NO COINCIDE <<<  revisar (puede ser desfase de tiempo o un bug)")
    return ok


SAMPLE_SIM = [(17014, 14218, 2), (17114, 14176, 2), (17214, 7100, 2)]  # raws de ejemplo
SAMPLE_API = 3540.0

if __name__ == "__main__":
    if "--self-check" in sys.argv:
        print("(modo prueba: raws del snapshot real + un actualPcsPower de ejemplo)")
        detalle = [(a, w_to_kw(raw, sf)) for a, raw, sf in SAMPLE_SIM]
        expected = sum(kw for _, kw in detalle)
        report(expected, SAMPLE_API, detalle)
        sys.exit(0)

    try:
        expected, detalle = read_sim_total_kw()
    except Exception as e:
        print("No pude leer el simulador:", e)
        sys.exit(1)
    try:
        auth = make_auth(BASE_URL)
        summary = auth.authorized_get(BASE_URL + SUMMARY_PATH)
        actual = (summary.get("dispatchDiagnostics") or {}).get("actualPcsPower")
    except Exception as e:
        print("No pude leer OmniOps:", e)
        sys.exit(1)
    if actual is None:
        print("OmniOps devolvió actualPcsPower = null (sin dato ahora).")
        sys.exit(1)
    report(expected, float(actual), detalle)
