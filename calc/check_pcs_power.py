"""
check_pcs_power.py — TU PRIMER TEST contra OmniOps LOCAL (con login automático).

Lee actualPcsPower del endpoint de resumen y verifica tres cosas:
  1) el valor está presente y es un número,
  2) está dentro de un rango físico razonable,
  3) la frescura del dato es coherente con lo que OmniOps reporta.

El login lo maneja auth.py: se loguea solo y renueva el token al vencer.
SOLO LEE: no escribe ni modifica nada en OmniOps. No instala nada nuevo.

Antes de correr, creá el archivo 'omniops_login.txt' en esta carpeta:
    email=admin@omniops.com
    password=1

Correr contra OmniOps local:   python check_pcs_power.py
Probar la lógica sin OmniOps:  python check_pcs_power.py --self-check
"""

import sys

from core.auth import make_auth
from config import BASE_URL, SUMMARY_PATH, POWER_MIN_KW, POWER_MAX_KW


def normal_freshness(reported: str) -> bool:
    return (reported or "").strip().lower() in ("ok", "normal", "good", "fresh")


def evaluate(summary):
    disp = summary.get("dispatchDiagnostics") or {}
    gw = summary.get("gatewayDiagnostics") or {}
    checks = []

    power = disp.get("actualPcsPower")
    ts = disp.get("timestamp")

    is_num = isinstance(power, (int, float)) and not isinstance(power, bool)
    checks.append(("valor presente y numerico", is_num,
                   f"actualPcsPower = {power}"))

    in_range = is_num and POWER_MIN_KW <= power <= POWER_MAX_KW
    checks.append(("dentro de rango plausible", in_range,
                   f"{power} kW en [{POWER_MIN_KW}, {POWER_MAX_KW}]"))

    fresh_s = gw.get("freshnessSeconds")
    interval = gw.get("samplingInterval")
    reported = gw.get("dataFreshness")
    if isinstance(fresh_s, (int, float)) and isinstance(interval, (int, float)):
        oracle_normal = fresh_s <= 2 * interval
        match = oracle_normal == normal_freshness(reported)
        detalle = (f"freshness={fresh_s:.2f}s, intervalo={interval}s -> "
                   f"mi veredicto: {'normal' if oracle_normal else 'no normal'}; "
                   f"OmniOps dice: '{reported}'")
    else:
        match = False
        detalle = "faltan freshnessSeconds o samplingInterval"
    checks.append(("frescura coherente con OmniOps", match, detalle))

    return checks, ts


def report(summary):
    checks, ts = evaluate(summary)
    print(f"\nTimestamp del dato: {ts}\n")
    all_ok = True
    for name, passed, detalle in checks:
        print(f"  [{'PASA ' if passed else 'FALLA'}] {name}")
        print(f"          {detalle}")
        all_ok = all_ok and passed
    print("\n" + ("=> TODOS PASARON ✓" if all_ok else "=> HAY FALLAS ✗"))
    return all_ok


SAMPLE = {
    "dispatchDiagnostics": {"actualPcsPower": 2229.4,
                            "timestamp": "2026-08-04T13:36:35.438Z"},
    "gatewayDiagnostics": {"samplingInterval": 1, "dataFreshness": "Watch",
                           "freshnessSeconds": 3.5684898},
}

if __name__ == "__main__":
    if "--self-check" in sys.argv:
        print("(modo prueba: usando una muestra, sin conectar a OmniOps)")
        report(SAMPLE)
        sys.exit(0)

    auth = make_auth(BASE_URL)
    try:
        summary = auth.authorized_get(BASE_URL + SUMMARY_PATH)
    except FileNotFoundError as e:
        print(e)
        sys.exit(1)
    except Exception as e:
        print("No pude leer el endpoint:", e)
        print("Revisá que OmniOps esté corriendo en local y que las credenciales sean correctas.")
        sys.exit(1)
    report(summary)
