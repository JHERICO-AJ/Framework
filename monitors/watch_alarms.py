"""
watch_alarms.py — monitor de ALARMAS EN VIVO (inyectás y mirás reaccionar).

Corré esto, y desde OTRA terminal inyectá (python -m alarms.inject 1). El monitor
te muestra, en tiempo real, para cada alarma que te interesa:

    hora | id | nombre | causa(crudo) | API | veredicto

Cruza el ORÁCULO (¿la causa está en el crudo del simulador, vía el proxy?) contra
la API de OmniOps (¿la alarma está abierta?), usando verdict() (4 casos).

Clave para TU entorno: OmniOps arrastra alarmas viejas que no se cierran. El
monitor marca una alarma como "nueva" solo si su firstOccurred es POSTERIOR al
arranque del monitor. Así, las viejas pegadas no se cuentan como falsas: lo que
validamos es lo que aparece por TU inyección.

Requisitos: proxy en 5020 (python -m tools.sim_proxy), sim real en 5021, edge y
OmniOps prendidos. Si algo no está, el preflight te avisa claro.

Correr:            python -m monitors.watch_alarms
Probar la lógica:  python -m monitors.watch_alarms --self-check
"""

from __future__ import annotations

import datetime
import sys
import time

from core.auth import make_auth
from config import BASE_URL, OMNIOPS_EVERY_S, SIM_HOST, SIM_PORT
import alarms.catalog as cat
from alarms.api import leer_alarmas, rule_ids_abiertos, por_rule_id, primera_ultima
from alarms.oracle import evaluar
from alarms.verdict import (verdict, PASA, PASA_SANO,
                            FALLA_FALSA, FALLA_NO_DETECTADA, NO_VERIFICABLE)
from core.source_modbus import LectorModbus

TOL_TIEMPO_S = 20      # margen para "firstOccurred ≈ arranque" (tick + redondeo)


def clasificar(causa_estado, abierta, fresca):
    """Devuelve una etiqueta de verdict. `causa_estado`: True/False/None.
    `fresca`: la alarma en la API apareció DESPUÉS de arrancar el monitor.
    Una alarma abierta pero NO fresca (vieja pegada) se trata como no-abierta,
    así no la marcamos falsa."""
    if causa_estado is None:
        return NO_VERIFICABLE
    abierta_efectiva = bool(abierta and fresca)
    return verdict(causa_estado, abierta_efectiva, oracle_independent=True)


def preflight():
    """Chequea que se pueda leer el 5020 (proxy/sim) y la API. Mensajes claros."""
    problemas = []
    reader = None
    try:
        reader = LectorModbus()
        reader.leer_registro(cat.ADDR["evt1_802"])
    except Exception as e:
        problemas.append(
            f"No puedo leer el simulador en {SIM_HOST}:{SIM_PORT}. ¿Levantaste el "
            f"proxy? (python -m tools.sim_proxy)\n     En modo inyección el sim real "
            f"va en 5021 y el proxy en 5020.\n     Detalle: {e}")
    auth = None
    try:
        auth = make_auth(BASE_URL)
        leer_alarmas(auth=auth)
    except Exception as e:
        problemas.append(f"No puedo leer la API de alarmas de OmniOps. ¿Está "
                         f"corriendo?\n     Detalle: {e}")
    return reader, auth, problemas


def run():
    print("Preparando monitor de alarmas…")
    reader, auth, problemas = preflight()
    if problemas:
        print("\n No puedo arrancar todavía:\n")
        for p in problemas:
            print("  •", p)
        print("\nLevantá lo que falte y volvé a intentar.")
        if reader:
            reader.close()
        return

    arranque = datetime.datetime.now()
    base_abiertas, _ = leer_alarmas(auth=auth)
    baseline = rule_ids_abiertos(base_abiertas)
    print(f"OK. Arranque {arranque:%H:%M:%S}. Alarmas viejas ya abiertas: "
          f"{sorted(baseline)} (no las cuento como nuevas).")
    print("Inyectá desde otra terminal:  python -m alarms.inject <id>   "
          "(apagar: --clear)\nCtrl+C para terminar.\n")

    vistas_pasa = set()
    try:
        while True:
            hora = datetime.datetime.now().strftime("%H:%M:%S")
            estados, presentes = evaluar(reader)              # oráculo (crudo)
            alarmas, _ = leer_alarmas(auth=auth)              # API
            abiertos = rule_ids_abiertos(alarmas)

            # alarmas "de interés": las que tienen causa inyectada ahora, o que
            # aparecieron nuevas (firstOccurred posterior al arranque)
            interes = set(presentes)
            for rid in abiertos:
                pf, _ = primera_ultima(alarmas, rid)
                if pf and pf >= arranque - datetime.timedelta(seconds=TOL_TIEMPO_S):
                    interes.add(rid)

            if not interes:
                print(f"[{hora}]  sin causas inyectadas ni alarmas nuevas "
                      f"(viejas pegadas: {len(baseline)})")
            else:
                for rid in sorted(interes):
                    a = cat.BY_RULE_ID.get(rid)
                    nombre = a["name"] if a else f"regla {rid}"
                    causa = estados.get(rid, (None, ""))[0]
                    abierta = rid in abiertos
                    pf, ul = primera_ultima(alarmas, rid)
                    fresca = bool(pf and pf >= arranque - datetime.timedelta(seconds=TOL_TIEMPO_S))
                    v = clasificar(causa, abierta, fresca)
                    if v == PASA:
                        vistas_pasa.add(rid)
                    et = {True: "SÍ ", False: "no ", None: "n/v"}[causa]
                    marca = "  <<<" if v in (FALLA_FALSA, FALLA_NO_DETECTADA) else ""
                    ts = f" first={pf:%H:%M:%S}" if pf else ""
                    print(f"[{hora}]  ID {rid:2} {nombre:26} causa:{et} "
                          f"api:{'SÍ' if abierta else 'no'}{ts}  -> {v}{marca}")
            time.sleep(OMNIOPS_EVERY_S)
    except KeyboardInterrupt:
        print("\n=== RESUMEN ===")
        print(f"Alarmas que llegaron a PASA (inyectadas y detectadas): "
              f"{sorted(vistas_pasa) or '(ninguna)'}")
        reader.close()


# ---------------------------------------------------------------------------
def _self_check():
    print("(prueba de clasificación del monitor de alarmas — sin red)\n")
    casos = [
        # (causa, abierta, fresca, esperado)
        ("inyectada y aparece nueva",       True,  True,  True,  PASA),
        ("inyectada y no aparece",          True,  False, False, FALLA_NO_DETECTADA),
        ("sin causa, aparece nueva (falsa)", False, True,  True,  FALLA_FALSA),
        ("vieja pegada (abierta no fresca)", False, True,  False, PASA_SANO),
        ("sin causa, sin alarma",           False, False, False, PASA_SANO),
        ("no verificable (ems)",            None,  True,  True,  NO_VERIFICABLE),
    ]
    ok = True
    for nombre, causa, abierta, fresca, esperado in casos:
        got = clasificar(causa, abierta, fresca)
        bien = got == esperado
        ok = ok and bien
        print(f"  {nombre:36} -> {got:18} {'OK' if bien else f'MAL (esp {esperado})'}")
    print("\n=> " + ("TODOS OK ✓" if ok else "HAY DIFERENCIAS ✗"))
    return ok


if __name__ == "__main__":
    if "--self-check" in sys.argv:
        sys.exit(0 if _self_check() else 1)
    run()
