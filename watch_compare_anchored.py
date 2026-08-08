"""
watch_compare_anchored.py — TIEMPO REAL + COMPARACIÓN ANCLADA POR TIEMPO.

Elimina los FALLA por desfase. Cómo:
  - Lee el simulador seguido (cada ~1s) y guarda un historial (hora, valor).
  - Cada ~6s lee OmniOps, que trae el 'timestamp' del dato que muestra.
  - Busca en el historial el valor del simulador DE ESE MISMO instante y compara
    contra ese, no contra el simulador de ahora.

Así, cuando OmniOps va un pasito atrás, igual comparamos el mismo momento y la
razón da ~1.00 de forma consistente. Los FALLA que queden serán bugs de verdad.

SOLO LEE. Necesita el simulador y OmniOps corriendo en la misma máquina
(para que los relojes coincidan).

Correr:            python watch_compare_anchored.py
Probar la lógica:  python watch_compare_anchored.py --self-check
"""

import sys
import time

from auth import make_auth, _parse_dt
from check_pcs_power import BASE_URL, SUMMARY_PATH
from compare_pcs_power import read_sim_total_kw, compare
from reporter import Reporter

OMNIOPS_EVERY_S = 6     # cada cuánto le preguntamos a OmniOps (suave para el 429)
SIM_EVERY_S = 1         # cada cuánto guardamos el simulador en el historial
BUFFER_S = 90           # cuánto historial del simulador guardamos
MATCH_MAX_GAP_S = 1.5   # si el mejor match está más lejos que esto, no confío


def parse_epoch(ts):
    dt = _parse_dt(ts)
    return dt.timestamp() if dt else None


def match_buffer(buffer, target_epoch):
    """Del historial, el valor cuya hora esté más cerca del instante de OmniOps."""
    best, best_gap = None, None
    for ep, kw in buffer:
        gap = abs(ep - target_epoch)
        if best_gap is None or gap < best_gap:
            best, best_gap = (ep, kw), gap
    return best, best_gap


def run_live():
    auth = make_auth(BASE_URL)
    buffer = []
    state = {"n": 0, "ok": 0, "fallas": []}
    last_omni = 0.0
    reporte = Reporter(gap_confiable_s=1.0)
    print("Comparación ANCLADA por tiempo, en vivo...  (Ctrl+C para parar)")
    print("(los primeros segundos llena el historial; esperá una lectura o dos)\n")
    try:
        while True:
            now = time.time()
            # 1) siempre: guardar el simulador en el historial
            try:
                kw, _ = read_sim_total_kw()
                buffer.append((now, kw))
                buffer[:] = [(e, v) for e, v in buffer if now - e <= BUFFER_S]
            except Exception as e:
                print("  (error leyendo simulador):", e)

            # 2) cada OMNIOPS_EVERY_S: leer OmniOps y comparar anclado
            if now - last_omni >= OMNIOPS_EVERY_S:
                last_omni = now
                try:
                    summary = auth.authorized_get(BASE_URL + SUMMARY_PATH)
                    disp = summary.get("dispatchDiagnostics") or {}
                    actual = disp.get("actualPcsPower")
                    tep = parse_epoch(disp.get("timestamp"))
                    hora = (disp.get("timestamp") or "")[11:19]

                    if actual is None or tep is None:
                        print(f"[{hora}]  OmniOps sin dato utilizable")
                    else:
                        (mep, mkw), gap = match_buffer(buffer, tep)
                        if gap is None or gap > MATCH_MAX_GAP_S:
                            print(f"[{hora}]  aún no puedo anclar (gap {gap}s, "
                                  "historial corto todavía)")
                        else:
                            ok, diff, ratio, tol = compare(mkw, float(actual))
                            print(f"[{hora}]  esperado={mkw:8.0f} (anclado, "
                                  f"±{gap:.1f}s)  actual={float(actual):8.0f}  "
                                  f"razón={ratio:5.2f}   "
                                  f"{'PASA ' if ok else 'FALLA <<<'}")
                            state["n"] += 1
                            if ok:
                                state["ok"] += 1
                            else:
                                state["fallas"].append((hora, mkw, float(actual), ratio))
                            reporte.registrar(hora, mkw, float(actual), ratio, ok, gap)
                except Exception as e:
                    msg = str(e)
                    if "429" in msg:
                        print("  (OmniOps pidió esperar)")
                    else:
                        print("  (error leyendo OmniOps):", msg)

            time.sleep(SIM_EVERY_S)
    except KeyboardInterrupt:
        print("\n=== RESUMEN ===")
        print(f"Comparaciones ancladas: {state['n']}   PASA: {state['ok']}   "
              f"FALLA: {len(state['fallas'])}")
        for hora, exp, act, r in state["fallas"][:10]:
            print(f"   {hora}: esperado={exp:.0f} actual={act:.0f} razón={r:.2f}")
        reporte.save()


def self_check():
    print("(modo prueba: historial simulado + un dato de OmniOps 'atrasado')\n")
    # historial del simulador: la potencia subió con el tiempo
    buffer = [(1000.0, 100), (1001.0, 200), (1002.0, 300),
              (1003.0, 400), (1004.0, 500)]
    # OmniOps muestra un dato cuyo timestamp corresponde al instante 1002
    omni_actual, omni_epoch = 300, 1002.0
    (mep, mkw), gap = match_buffer(buffer, omni_epoch)
    ok, diff, ratio, tol = compare(mkw, omni_actual)
    print(f"OmniOps dato del instante {omni_epoch} (actual={omni_actual})")
    print(f"  -> del historial, el simulador en ese instante valía {mkw} (gap {gap}s)")
    print(f"  -> razón={ratio:.2f}   {'PASA ' if ok else 'FALLA'}")
    print("\nSin anclar habríamos comparado contra el simulador de ahora (500) -> "
          "razón 0.60 -> FALLA falso. Anclando da 1.00.")


if __name__ == "__main__":
    if "--self-check" in sys.argv:
        self_check()
    else:
        run_live()
