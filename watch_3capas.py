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

from auth import make_auth, _parse_dt
from check_pcs_power import BASE_URL, SUMMARY_PATH
from compare_pcs_power import read_sim_total_kw, compare
from ui_reader import UiSession

OMNIOPS_EVERY_S = 6
SIM_EVERY_S = 1
BUFFER_S = 90
MATCH_MAX_GAP_S = 1.0
UI_TOL_KW = 0.6          # margen para el redondeo a 1 decimal de la pantalla
HEADLESS = True          # True = navegador oculto; False = visible


def parse_epoch(ts):
    dt = _parse_dt(ts)
    return dt.timestamp() if dt else None


def match_buffer(buffer, target):
    best, bg = None, None
    for ep, kw in buffer:
        g = abs(ep - target)
        if bg is None or g < bg:
            best, bg = (ep, kw), g
    return best, bg


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
    print(f"\nReporte guardado: {path}")


def run():
    auth = make_auth(BASE_URL)
    print("Abriendo navegador y logueando (una sola vez)...")
    ui = UiSession(headless=HEADLESS)
    print("Listo. Monitor de 3 capas en vivo.  (Ctrl+C para parar)\n")

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
                buffer[:] = [(e, v) for e, v in buffer if now - e <= BUFFER_S]
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
                        print(f"[{hora}]  API sin dato")
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
    if "--self-check" in sys.argv:
        self_check()
    else:
        run()
