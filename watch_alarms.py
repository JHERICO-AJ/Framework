"""
watch_alarms.py — monitor de ALARMAS en vivo. Cierra el ciclo:

     causa en el CRUDO  (oráculo, alarms_oracle.py)
   vs alarma en la API  (alarms_api.py)
   -> veredicto de 4 casos (verdict.py)

Dos modos, según tengas o no el catálogo:

  BASELINE (corre HOY, sin catálogo ni hook de inyección):
    Con el simulador SANO no debería haber NINGUNA alarma abierta. Entonces
    cualquier alarma Open que aparezca es una posible FALSA. No necesita saber
    qué dispara cada alarma; solo mira la API.

  COMPLETO (cuando exista alarms_catalog.py):
    Por cada alarma del catálogo cruza causa (oráculo) vs API y da el veredicto
    PASA / PASA_SANO / FALLA_FALSA / FALLA_NO_DETECTADA (o NO_VERIFICABLE).

SOLO LEE: la API y el simulador; no cierra ni reconoce alarmas.

Correr baseline (o cuando no hay catálogo):   python watch_alarms.py
Forzar baseline aunque haya catálogo:         python watch_alarms.py --baseline
Probar la correlación sin red:                python watch_alarms.py --self-check
"""

from __future__ import annotations

import datetime
import os
import sys
import time

from auth import make_auth
from config import BASE_URL
from alarms_api import leer_alarmas, abiertas_por_codigo
from alarms_oracle import causa_activa, LectorModbus, LectorFalso
from verdict import (verdict, DESCRIPCION, es_ok, es_confiable,
                     FALLA_FALSA, FALLA_NO_DETECTADA, NO_VERIFICABLE)

EVERY_S = 6            # cada cuánto consultamos la API (suave para el 429)


# --- carga del catálogo (opcional) ------------------------------------------
def cargar_catalogo():
    """Devuelve (CATALOGO, disponible). Si no existe alarms_catalog.py -> ([], False)."""
    try:
        import alarms_catalog          # el real, que crea la usuaria
        return list(alarms_catalog.CATALOGO), True
    except Exception:
        return [], False


# --- correlación (lógica pura y testeable) ----------------------------------
def correlacionar(catalogo, codigos_abiertos, lector):
    """Por cada entrada del catálogo produce (entry, causa, abierta, veredicto).
    `codigos_abiertos` es un set/dict de codes Open de la API.
    `lector` es el lector del crudo (real o falso) para el oráculo."""
    filas = []
    abiertos = set(codigos_abiertos)
    for entry in catalogo:
        code = (entry.get("api_match") or {}).get("code")
        abierta = code in abiertos
        try:
            causa = causa_activa(entry, lector)
        except Exception:
            causa = None               # si no pude leer el crudo, no arriesgo
        v = verdict(causa, abierta,
                    oracle_independent=entry.get("oracle_independent", True))
        filas.append((entry, causa, abierta, v))
    return filas


# --- reporte ----------------------------------------------------------------
def guardar_reporte(stats, modo):
    os.makedirs("reportes", exist_ok=True)
    stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    path = f"reportes/reporte_alarmas_{stamp}.txt"
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(f"Validación de alarmas — modo {modo}\n")
        fh.write(f"Corrida: {datetime.datetime.now():%Y-%m-%d %H:%M:%S}\n")
        fh.write("=" * 56 + "\n\n")
        fh.write(f"Ciclos: {stats['ciclos']}\n\n")
        if modo == "baseline":
            fh.write("BASELINE (simulador sano -> no debería haber alarmas):\n")
            fh.write(f"  ciclos limpios (0 abiertas) : {stats['limpios']}\n")
            fh.write(f"  ciclos con alarmas abiertas : {stats['sucios']}\n")
            if stats["falsas_vistas"]:
                fh.write("\nAlarmas abiertas observadas (posibles FALSAS):\n")
                for c in sorted(stats["falsas_vistas"]):
                    fh.write(f"  - {c}\n")
        else:
            fh.write("COMPLETO (por catálogo):\n")
            for k in ("PASA", "PASA_SANO", "FALLA_FALSA",
                      "FALLA_NO_DETECTADA", "NO_VERIFICABLE"):
                fh.write(f"  {k:20}: {stats['conteo'].get(k, 0)}\n")
            if stats["hallazgos"]:
                fh.write("\nHallazgos (revisar):\n")
                for h in stats["hallazgos"][:30]:
                    fh.write(f"  {h}\n")
    print(f"\nReporte guardado: {path}")


# --- loop en vivo -----------------------------------------------------------
def run(forzar_baseline=False):
    auth = make_auth(BASE_URL)
    catalogo, hay_catalogo = cargar_catalogo()
    modo = "baseline" if (forzar_baseline or not hay_catalogo) else "completo"

    if modo == "baseline":
        if not hay_catalogo:
            print("No hay alarms_catalog.py todavía -> corro en modo BASELINE.")
        print("BASELINE: con el simulador sano NO debería haber alarmas abiertas.\n"
              "Cualquier alarma Open = posible FALSA.  (Ctrl+C para parar)\n")
    else:
        print(f"COMPLETO: {len(catalogo)} alarmas en el catálogo. Cruzo causa "
              "(oráculo) vs API.  (Ctrl+C para parar)\n")

    stats = {"ciclos": 0, "limpios": 0, "sucios": 0, "falsas_vistas": set(),
             "conteo": {}, "hallazgos": []}

    try:
        while True:
            stats["ciclos"] += 1
            hora = datetime.datetime.now().strftime("%H:%M:%S")
            try:
                alarmas, _ = leer_alarmas(auth=auth, status="Open")
            except Exception as e:
                msg = str(e)
                print("  (OmniOps pidió esperar)" if "429" in msg
                      else f"  (error API alarmas): {msg}")
                time.sleep(EVERY_S)
                continue

            abiertas = abiertas_por_codigo(alarmas)

            if modo == "baseline":
                n = len(abiertas)
                if n == 0:
                    stats["limpios"] += 1
                    print(f"[{hora}]  0 alarmas abiertas  -> baseline limpio ✓")
                else:
                    stats["sucios"] += 1
                    stats["falsas_vistas"].update(abiertas.keys())
                    print(f"[{hora}]  {n} alarma(s) abierta(s) con simulador sano "
                          f"-> POSIBLE FALSA <<<  {sorted(abiertas)}")
            else:
                # modo completo: necesito leer el crudo para el oráculo
                lector = None
                try:
                    lector = LectorModbus()
                except Exception as e:
                    print(f"[{hora}]  (no pude abrir el simulador para el oráculo): {e}")
                    time.sleep(EVERY_S)
                    continue
                try:
                    filas = correlacionar(catalogo, set(abiertas), lector)
                finally:
                    lector.close()

                resumen = {}
                for entry, causa, abierta, v in filas:
                    stats["conteo"][v] = stats["conteo"].get(v, 0) + 1
                    resumen[v] = resumen.get(v, 0) + 1
                    if v in (FALLA_FALSA, FALLA_NO_DETECTADA):
                        stats["hallazgos"].append(
                            f"{hora} {entry['id']}: {DESCRIPCION[v]} "
                            f"(causa={causa}, abierta={abierta})")
                marca = ""
                if resumen.get(FALLA_FALSA) or resumen.get(FALLA_NO_DETECTADA):
                    marca = "  <<< HALLAZGO"
                print(f"[{hora}]  " + "  ".join(
                    f"{k}:{resumen[k]}" for k in sorted(resumen)) + marca)

            time.sleep(EVERY_S)
    except KeyboardInterrupt:
        print("\n=== RESUMEN ALARMAS ===")
        if modo == "baseline":
            print(f"Ciclos: {stats['ciclos']}   limpios: {stats['limpios']}   "
                  f"con alarmas: {stats['sucios']}")
            if stats["falsas_vistas"]:
                print("Posibles falsas vistas:", sorted(stats["falsas_vistas"]))
        else:
            for k, n in sorted(stats["conteo"].items()):
                print(f"  {k:20}: {n}")
        guardar_reporte(stats, modo)


# --- prueba de la correlación sin red ---------------------------------------
def _self_check():
    print("(prueba de correlación — catálogo y lector FALSOS, sin red)\n")
    catalogo = [
        {"id": "OV_PCS", "oracle_independent": True,
         "causa": {"tipo": "bit", "registro": 1000, "bit": 5},
         "api_match": {"code": "OV_PCS"}},          # causa sí, abierta sí -> PASA
        {"id": "TEMP_HI", "oracle_independent": True,
         "causa": {"tipo": "bit", "registro": 1000, "bit": 3},
         "api_match": {"code": "TEMP_HI"}},         # causa no, abierta sí -> FALLA_FALSA
        {"id": "UNDERV", "oracle_independent": True,
         "causa": {"tipo": "bit", "registro": 1000, "bit": 5},
         "api_match": {"code": "UNDERV"}},          # causa sí, abierta no -> NO_DETECTADA
        {"id": "SANA", "oracle_independent": True,
         "causa": {"tipo": "bit", "registro": 1000, "bit": 3},
         "api_match": {"code": "SANA"}},            # causa no, abierta no -> PASA_SANO
        {"id": "EMS", "oracle_independent": False,
         "api_match": {"code": "EMS"}},             # no verificable
    ]
    lector = LectorFalso({1000: 0b100000})          # bit 5 = 1, bit 3 = 0
    codigos_abiertos = {"OV_PCS", "TEMP_HI", "EMS"}

    filas = correlacionar(catalogo, codigos_abiertos, lector)
    esperado = {
        "OV_PCS": "PASA", "TEMP_HI": FALLA_FALSA,
        "UNDERV": FALLA_NO_DETECTADA, "SANA": "PASA_SANO", "EMS": NO_VERIFICABLE,
    }
    todos_ok = True
    for entry, causa, abierta, v in filas:
        ok = v == esperado[entry["id"]]
        todos_ok = todos_ok and ok
        print(f"  {entry['id']:8} causa={str(causa):5} abierta={str(abierta):5} "
              f"-> {v:18} {'OK' if ok else 'MAL'}")
    print("\n=> " + ("TODOS OK ✓" if todos_ok else "HAY DIFERENCIAS ✗"))
    return todos_ok


if __name__ == "__main__":
    if "--self-check" in sys.argv:
        sys.exit(0 if _self_check() else 1)
    run(forzar_baseline="--baseline" in sys.argv)
