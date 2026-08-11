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

from auth import make_auth
from config import (BASE_URL, SUMMARY_PATH, OMNIOPS_EVERY_S, SIM_EVERY_S,
                    BUFFER_S, GAP_CONFIABLE_S, GAP_MAX_ANCLAJE_S)
from omniops_time import parse_epoch
from timeanchor import match_buffer, podar
from source_modbus import read_sim_total_kw
from compare_pcs_power import compare
from reporter import Reporter

MATCH_MAX_GAP_S = GAP_MAX_ANCLAJE_S   # hasta este gap intenta anclar (1.5)

# Modo presentación (para mostrar a un alto cargo). Se prende con --limpio.
# En limpio: líneas en idioma humano, y las mediciones descartadas por desfase
# se muestran como "· midiendo…" en vez de con la palabra técnica.
# El resumen ejecutivo se genera SIEMPRE (lo arma reporter.py), prendido o no.
LIMPIO = False


def run_live():
    auth = make_auth(BASE_URL)
    buffer = []
    state = {"n": 0, "ok": 0, "fallas": []}
    last_omni = 0.0
    reporte = Reporter(gap_confiable_s=GAP_CONFIABLE_S)
    if LIMPIO:
        print("Validación de OmniOps en vivo…  (Ctrl+C para terminar)\n")
    else:
        print("Comparación ANCLADA por tiempo, en vivo...  (Ctrl+C para parar)")
        print("(los primeros segundos llena el historial; esperá una lectura o dos)\n")
    try:
        while True:
            now = time.time()
            # 1) siempre: guardar el simulador en el historial
            try:
                kw, _ = read_sim_total_kw()
                buffer.append((now, kw))
                podar(buffer, now)
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
                        # sin dato utilizable: en limpio no asustamos, mostramos vida
                        print(f"[{hora}]  · midiendo…" if LIMPIO
                              else f"[{hora}]  OmniOps sin dato utilizable")
                    else:
                        (mep, mkw), gap = match_buffer(buffer, tep)
                        if gap is None or gap > MATCH_MAX_GAP_S:
                            # descartada por desfase: útil para nosotros, ruido para
                            # un directivo -> en limpio se ve como "midiendo…"
                            print(f"[{hora}]  · midiendo…" if LIMPIO
                                  else f"[{hora}]  aún no puedo anclar (gap {gap}s, "
                                       "historial corto todavía)")
                        else:
                            ok, diff, ratio, tol = compare(mkw, float(actual))
                            if LIMPIO:
                                if ok:
                                    print(f"[{hora}]  OmniOps calcula correcto ✓   "
                                          f"({float(actual):.0f} kW)")
                                else:
                                    print(f"[{hora}]  OmniOps NO coincide ✗   "
                                          f"(esperado {mkw:.0f}, mostró "
                                          f"{float(actual):.0f} kW)")
                            else:
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
        if LIMPIO:
            tasa = (state["ok"] / state["n"] * 100) if state["n"] else 0.0
            print(f"Mediciones verificadas: {state['n']}   "
                  f"Correctas: {state['ok']}   "
                  f"Con diferencia: {len(state['fallas'])}   "
                  f"Acierto: {tasa:.1f}%")
            for hora, exp, act, r in state["fallas"][:10]:
                print(f"   {hora}: se esperaba {exp:.0f} kW, mostró {act:.0f} kW")
        else:
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
    if "--limpio" in sys.argv:
        LIMPIO = True                    # modo presentación (terminal en limpio)
    if "--self-check" in sys.argv:
        self_check()
    else:
        run_live()
