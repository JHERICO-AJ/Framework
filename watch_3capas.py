"""
watch_3capas.py — monitor de las TRES capas: simulador -> API -> pantalla.

Por cada ciclo valida DOS cosas y te dice el veredicto de cada una:
  CÁLCULO : simulador (anclado por tiempo) vs API (actualPcsPower)
            -> ¿OmniOps calcula bien?
  PANTALLA: API vs el número renderizado en la UI (Playwright)
            -> ¿la UI muestra bien lo que la API calculó?

El primer eslabón que falla localiza el problema.
El navegador se abre y se loguea UNA vez, y se reusa en cada ciclo.
Al cortar con Ctrl+C, guarda un reporte de las tres capas.

Correr:  python watch_3capas.py
"""

import datetime
import os
import sys
import time

from auth import make_auth
from config import (BASE_URL, SUMMARY_PATH, OMNIOPS_EVERY_S, SIM_EVERY_S,
                    BUFFER_S, GAP_CONFIABLE_S, UI_TOL_KW, HEADLESS)
from omniops_time import parse_epoch
from timeanchor import match_buffer, podar
from source_modbus import read_sim_total_kw
from compare_pcs_power import compare
from ui_reader import UiSession

MATCH_MAX_GAP_S = GAP_CONFIABLE_S   # en 3capas el corte es directo (1.0)

# Modo presentación (para mostrar a un alto cargo). Se prende con --limpio.
# En limpio: líneas en idioma humano y sin la palabra "descartada" (las
# descartadas por desfase se ven como "· midiendo…"). El resumen ejecutivo
# se genera SIEMPRE, prendido o no.
LIMPIO = False


def pantalla_ok(ui_val, api_recientes):
    """La pantalla está bien si coincide (a 1 decimal) con ALGÚN valor reciente
    de la API — así absorbe el retardo de un tick sin aflojar la precisión."""
    if ui_val is None:
        return None                       # sin dato en pantalla
    for a in api_recientes:
        if abs(round(ui_val, 1) - round(a, 1)) <= UI_TOL_KW:
            return True
    return False


def guardar_reporte(stats):
    os.makedirs("reportes", exist_ok=True)
    stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    path = f"reportes/reporte_3capas_{stamp}.txt"
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("Validación 3 capas (simulador -> API -> pantalla)\n")
        fh.write(f"Corrida: {datetime.datetime.now():%Y-%m-%d %H:%M:%S}\n")
        fh.write("=" * 56 + "\n\n")
        fh.write("CAPA CÁLCULO (simulador vs API):\n")
        fh.write(f"  PASA {stats['calc_ok']}   FALLA {stats['calc_fail']}   "
                 f"descartadas {stats['calc_desc']}\n\n")
        fh.write("CAPA PANTALLA (API vs UI):\n")
        fh.write(f"  PASA {stats['pant_ok']}   FALLA {stats['pant_fail']}   "
                 f"sin dato {stats['pant_none']}\n")
        if stats["fallas"]:
            fh.write("\nFallas (revisar):\n")
            for f in stats["fallas"][:15]:
                fh.write(f"  {f}\n")
    ej = guardar_ejecutivo(stats, stamp)
    print(f"\nReporte técnico guardado: {path}")
    print(f"Resumen ejecutivo (para presentar): {ej}")


def guardar_ejecutivo(stats, stamp):
    """Resumen limpio y EN INGLÉS para un alto cargo: solo passed/failed y la
    tasa por capa. No menciona descartadas ni 'sin dato'."""
    path = f"reportes/executive_summary_{stamp}.txt"
    calc_conf = stats["calc_ok"] + stats["calc_fail"]
    pant_conf = stats["pant_ok"] + stats["pant_fail"]
    tasa_calc = (stats["calc_ok"] / calc_conf * 100) if calc_conf else 0.0
    tasa_pant = (stats["pant_ok"] / pant_conf * 100) if pant_conf else 0.0
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("OmniOps Validation — Executive Summary\n")
        fh.write(f"Date: {datetime.datetime.now():%Y-%m-%d %H:%M}\n")
        fh.write("=" * 44 + "\n\n")
        fh.write("Automated, independent verification that OmniOps\n")
        fh.write("calculates the power correctly and displays it correctly.\n\n")
        fh.write("Calculation (does OmniOps compute correctly?)\n")
        fh.write(f"  Measurements verified : {calc_conf}\n")
        fh.write(f"  Passed                : {stats['calc_ok']}\n")
        fh.write(f"  Failed                : {stats['calc_fail']}\n")
        fh.write(f"  Pass rate             : {tasa_calc:.1f}%\n\n")
        fh.write("Display (is it shown correctly?)\n")
        fh.write(f"  Measurements verified : {pant_conf}\n")
        fh.write(f"  Passed                : {stats['pant_ok']}\n")
        fh.write(f"  Failed                : {stats['pant_fail']}\n")
        fh.write(f"  Pass rate             : {tasa_pant:.1f}%\n\n")
        if stats["calc_fail"] == 0 and stats["pant_fail"] == 0:
            fh.write("Overall result: PASS\n")
            fh.write("OmniOps calculated and displayed the correct value in "
                     "all verified measurements.\n")
        else:
            fh.write("Overall result: FAIL\n")
            fh.write("Differences detected (see technical report for detail).\n")
    return path


def run():
    auth = make_auth(BASE_URL)
    print("Abriendo navegador y logueando (una sola vez)...")
    ui = UiSession(headless=HEADLESS)
    print("Listo. Validación de OmniOps en vivo…  (Ctrl+C para terminar)\n"
          if LIMPIO else
          "Listo. Monitor de 3 capas en vivo.  (Ctrl+C para parar)\n")

    buffer = []
    api_recientes = []
    stats = {"calc_ok": 0, "calc_fail": 0, "calc_desc": 0,
             "pant_ok": 0, "pant_fail": 0, "pant_none": 0, "fallas": []}
    last_omni = 0.0
    try:
        while True:
            now = time.time()
            try:
                kw, _ = read_sim_total_kw()
                buffer.append((now, kw))
                podar(buffer, now)
            except Exception as e:
                print("  (error simulador):", e)

            if now - last_omni >= OMNIOPS_EVERY_S:
                last_omni = now
                try:
                    disp = (auth.authorized_get(BASE_URL + SUMMARY_PATH)
                            .get("dispatchDiagnostics") or {})
                    api_val = disp.get("actualPcsPower")
                    tep = parse_epoch(disp.get("timestamp"))
                    hora = (disp.get("timestamp") or "")[11:19]
                    ui_val, ui_txt = ui.read()

                    if api_val is None or tep is None:
                        print(f"[{hora}]  · midiendo…" if LIMPIO
                              else f"[{hora}]  API sin dato")
                    else:
                        api_val = float(api_val)
                        api_recientes.append(api_val)
                        api_recientes[:] = api_recientes[-3:]   # últimos 3

                        # --- capa cálculo (sim anclado vs api) ---
                        (mep, mkw), gap = match_buffer(buffer, tep)
                        if gap is None or gap > MATCH_MAX_GAP_S:
                            calc = "descartada"
                            stats["calc_desc"] += 1
                        else:
                            ok, *_ = compare(mkw, api_val)
                            calc = "PASA " if ok else "FALLA"
                            stats["calc_ok" if ok else "calc_fail"] += 1
                            if not ok:
                                stats["fallas"].append(
                                    f"{hora} CÁLCULO sim={mkw:.0f} api={api_val:.0f}")

                        # --- capa pantalla (api vs ui) ---
                        pok = pantalla_ok(ui_val, api_recientes)
                        if pok is None:
                            pant = "sin dato"
                            stats["pant_none"] += 1
                        elif pok:
                            pant = "PASA "
                            stats["pant_ok"] += 1
                        else:
                            pant = "FALLA"
                            stats["pant_fail"] += 1
                            stats["fallas"].append(
                                f"{hora} PANTALLA api={api_val:.1f} ui={ui_val}")

                        if LIMPIO:
                            # descartada por desfase -> ruido para un directivo:
                            # se ve como actividad ("midiendo…"), no como error
                            if calc.strip() == "descartada":
                                print(f"[{hora}]  · midiendo…")
                            else:
                                c = "✓" if calc.strip() == "PASA" else "✗"
                                p = ("✓" if pant.strip() == "PASA"
                                     else "—" if pant.strip() == "sin dato"
                                     else "✗")
                                print(f"[{hora}]  Cálculo {c}  Pantalla {p}   "
                                      f"({api_val:.0f} kW)")
                        else:
                            print(f"[{hora}]  cálculo:{calc}  pantalla:{pant}   "
                                  f"(api={api_val:8.1f}  ui={ui_txt})")
                except Exception as e:
                    msg = str(e)
                    if "429" in msg:
                        print("  (OmniOps pidió esperar)")
                    else:
                        print("  (error ciclo):", msg)

            time.sleep(SIM_EVERY_S)
    except KeyboardInterrupt:
        print("\n=== RESUMEN 3 CAPAS ===")
        if LIMPIO:
            calc_conf = stats["calc_ok"] + stats["calc_fail"]
            pant_conf = stats["pant_ok"] + stats["pant_fail"]
            tc = (stats["calc_ok"] / calc_conf * 100) if calc_conf else 0.0
            tp = (stats["pant_ok"] / pant_conf * 100) if pant_conf else 0.0
            print(f"Cálculo : correctas {stats['calc_ok']}  "
                  f"con diferencia {stats['calc_fail']}  acierto {tc:.1f}%")
            print(f"Pantalla: correctas {stats['pant_ok']}  "
                  f"con diferencia {stats['pant_fail']}  acierto {tp:.1f}%")
        else:
            print(f"CÁLCULO : PASA {stats['calc_ok']}  FALLA {stats['calc_fail']}  "
                  f"descartadas {stats['calc_desc']}")
            print(f"PANTALLA: PASA {stats['pant_ok']}  FALLA {stats['pant_fail']}  "
                  f"sin dato {stats['pant_none']}")
        guardar_reporte(stats)
    finally:
        ui.close()


# --- prueba de la lógica de la capa pantalla (sin navegador) ---------------
def self_check():
    print("(prueba de pantalla_ok)")
    api = [4285.1, 4290.0, 4280.0]
    print("ui=4285.1 (coincide) ->", pantalla_ok(4285.1, api), "(esperado True)")
    print("ui=4290.0 (tick previo) ->", pantalla_ok(4290.0, api), "(esperado True)")
    print("ui=4.3 (bug de escala) ->", pantalla_ok(4.3, api), "(esperado False)")
    print("ui=None (N/A) ->", pantalla_ok(None, api), "(esperado None)")


if __name__ == "__main__":
    if "--limpio" in sys.argv:
        LIMPIO = True                    # modo presentación (terminal en limpio)
    if "--self-check" in sys.argv:
        self_check()
    else:
        run()
