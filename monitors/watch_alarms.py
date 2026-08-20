"""watch_alarms — monitor EN VIVO de alarmas: inyectás (desde otra terminal) y
ves causa (crudo) vs API en tiempo real. Observa en bucle, no valida.

    python -m monitors.watch_alarms
    # en otra terminal:  python -m tools.probar 16   (o inyección manual)
"""
from __future__ import annotations

import datetime
import time

from shared.config.settings import BASE_URL, OMNIOPS_EVERY_S, SIM_HOST, SIM_PORT
from shared.datasource.modbus_source import LectorModbus
from shared.domain import alarm_catalog as cat
from shared.domain.oracle import evaluar
from shared.domain.verdict import clasificar, PASA, FALLA_FALSA, FALLA_NO_DETECTADA
from framework_api.client.api_client import ApiClient
from framework_api.services.alarms_service import AlarmsService

TOL_S = 20


def _api_snapshot(service):
    alarms = service.get_alarms()
    open_ids = {a.rule_id for a in alarms if a.is_open and a.rule_id is not None}
    last_by_rule = {}
    for a in alarms:
        if a.last_occurred:
            prev = last_by_rule.get(a.rule_id)
            if prev is None or a.last_occurred > prev:
                last_by_rule[a.rule_id] = a.last_occurred
    return open_ids, last_by_rule


def run():
    service = AlarmsService(ApiClient(BASE_URL))
    try:
        reader = LectorModbus()
        reader.leer_registro(cat.ADDR["evt1_802"])
    except Exception as e:
        print(f"No puedo leer el simulador en {SIM_HOST}:{SIM_PORT}. "
              f"¿Levantaste el proxy?\n  {e}")
        return

    start = datetime.datetime.now(datetime.timezone.utc)
    baseline, _ = _api_snapshot(service)
    print(f"watch_alarms — arranque {start.astimezone():%H:%M:%S}. "
          f"Viejas ya abiertas: {sorted(baseline)}")
    print("Inyectá desde otra terminal (python -m tools.probar <id>). Ctrl+C para salir.\n")
    try:
        while True:
            hora = datetime.datetime.now().strftime("%H:%M:%S")
            states, present = evaluar(reader)
            open_ids, last_by_rule = _api_snapshot(service)

            interest = set(present)
            for rid, ul in last_by_rule.items():
                if ul >= start - datetime.timedelta(seconds=TOL_S):
                    interest.add(rid)

            if not interest:
                print(f"[{hora}] sin causas inyectadas ni alarmas nuevas "
                      f"(viejas: {len(baseline)})")
            else:
                for rid in sorted(interest):
                    name = cat.BY_RULE_ID.get(rid, {}).get("name", f"rule {rid}")
                    cause = states.get(rid, (None, ""))[0]
                    ul = last_by_rule.get(rid)
                    fresh = bool(ul and ul >= start - datetime.timedelta(seconds=TOL_S))
                    v = clasificar(cause, rid in open_ids, fresh)
                    mark = "  <<<" if v in (FALLA_FALSA, FALLA_NO_DETECTADA) else ""
                    et = {True: "SÍ ", False: "no ", None: "n/v"}[cause]
                    print(f"[{hora}] ID {rid:2} {name:24} causa:{et} "
                          f"api:{'SÍ' if rid in open_ids else 'no'}  -> {v}{mark}")
            time.sleep(OMNIOPS_EVERY_S)
    except KeyboardInterrupt:
        print("\nfin.")
    finally:
        reader.close()


if __name__ == "__main__":
    run()
