"""probar.py — comando OPERATIVO para disparar y verificar alarmas (cross-layer).

Orquesta 3 capas: inyecta (domain+proxy), lee el crudo (oráculo) y lee la API
(AlarmsService), y da un veredicto por alarma. NO es "solo API": por eso vive en
tools/ (herramienta), no en framework_api/.

  python -m tools.probar 16                       # simple
  python -m tools.probar 16 29 --vivo             # varias, en vivo
  python -m tools.probar 16 --at 10 --hasta 30 --vivo   # escena temporal

La función verify_alarms() la reusa tests/cross_layer/test_alarms.py (misma lógica).
Necesita la cadena arriba (sim + proxy + edge + OmniOps).
"""
from __future__ import annotations

import datetime
import sys
import time

from shared.config.settings import BASE_URL, OMNIOPS_EVERY_S
from shared.datasource.modbus_source import LectorModbus
from shared.domain import alarm_catalog as cat
from shared.domain.injection import guardar_estado, limpiar_estado
from shared.domain.oracle import evaluar
from shared.domain.verdict import clasificar, PASA, PASA_SANO, NO_VERIFICABLE
from framework_api.client.api_client import ApiClient
from framework_api.services.alarms_service import AlarmsService

TIMEOUT_S = 45
TOL_S = 25


def _near(ts, ref, tol_s):
    return bool(ts and abs((ts - ref).total_seconds()) <= tol_s)


def _api_snapshot(alarms_service):
    """(set de rule_ids abiertos, dict rule_id -> lastOccurred máximo)."""
    alarms = alarms_service.get_alarms()
    open_ids = {a.rule_id for a in alarms if a.is_open and a.rule_id is not None}
    last_by_rule = {}
    for a in alarms:
        if a.last_occurred:
            prev = last_by_rule.get(a.rule_id)
            if prev is None or a.last_occurred > prev:
                last_by_rule[a.rule_id] = a.last_occurred
    return open_ids, last_by_rule


class Result:
    def __init__(self, rule_id, name):
        self.rule_id = rule_id
        self.name = name
        self.cause = None
        self.in_api = False
        self.verdict = NO_VERIFICABLE
        self.last = None
        self.appeared_in_s = None
        self.time_ok = None

    @property
    def ok(self):
        return self.verdict in (PASA, PASA_SANO, NO_VERIFICABLE)


def verify_alarms(ids, alarms_service, reader=None, timeout=TIMEOUT_S, tol_s=TOL_S,
                  at=0, live=False):
    """Inyecta ids, verifica causa(crudo)+API+hora, limpia. Devuelve [Result]."""
    own_reader = reader is None
    if own_reader:
        reader = LectorModbus()
        reader.leer_registro(cat.ADDR["evt1_802"])   # falla claro si no hay proxy/sim

    res = {r: Result(r, cat.BY_RULE_ID.get(r, {}).get("name", f"rule {r}")) for r in ids}
    if at:
        if live:
            print(f"Disparo en {at}s…")
        time.sleep(at)

    moment = datetime.datetime.now(datetime.timezone.utc)
    try:
        guardar_estado(ids)
        if live:
            print(f"[{moment.astimezone():%H:%M:%S}] inyectadas {ids}. Esperando a OmniOps…")
        t0 = time.time()
        while time.time() - t0 < timeout:
            states, _ = evaluar(reader)
            open_ids, last_by_rule = _api_snapshot(alarms_service)
            done = True
            for r in ids:
                res[r].cause = states.get(r, (None, ""))[0]
                res[r].in_api = r in open_ids
                ul = last_by_rule.get(r)
                res[r].last = ul
                fresh = _near(ul, moment, tol_s) or (ul and ul >= moment)
                if fresh and res[r].appeared_in_s is None:
                    res[r].appeared_in_s = round(time.time() - t0, 1)
                    res[r].time_ok = _near(ul, moment, tol_s)
                res[r].verdict = clasificar(res[r].cause, res[r].in_api, bool(fresh))
                if res[r].verdict not in (PASA, NO_VERIFICABLE):
                    done = False
            if live:
                _live_line(res, ids)
            if done:
                break
            time.sleep(OMNIOPS_EVERY_S)
    finally:
        limpiar_estado()
        if own_reader:
            reader.close()
    return [res[r] for r in ids]


def _et(cause):
    return {True: "SÍ", False: "no", None: "n/v"}[cause]


def _live_line(res, ids):
    hora = datetime.datetime.now().strftime("%H:%M:%S")
    parts = [f"ID{r} causa:{_et(res[r].cause)} api:{'SÍ' if res[r].in_api else 'no'} "
             f"{res[r].verdict}" for r in ids]
    print("  [" + hora + "] " + "  |  ".join(parts))


def _print(results):
    print("\n=== RESULTADO ===")
    for r in results:
        ts = f" last={r.last.astimezone():%H:%M:%S}" if r.last else ""
        extra = ""
        if r.appeared_in_s is not None:
            extra = f"  (apareció en {r.appeared_in_s}s, {'hora✓' if r.time_ok else 'hora✗'})"
        print(f"  ID {r.rule_id:2} {r.name:26} causa:{_et(r.cause)} "
              f"api:{'SÍ' if r.in_api else 'no'}{ts}  -> {r.verdict}{extra}")
    fail = [r.rule_id for r in results if not r.ok]
    print(f"\n  {'FALLAN: ' + str(fail) if fail else 'Todas OK ✓'}")


def _parse_args(args):
    ids, at, hasta, live, skip = [], 0, 0, "--vivo" in args, set()
    for j, a in enumerate(args):
        if a == "--at" and j + 1 < len(args):
            at = int(args[j + 1]); skip.add(j + 1)
        elif a == "--hasta" and j + 1 < len(args):
            hasta = int(args[j + 1]); skip.add(j + 1)
    for j, a in enumerate(args):
        if j not in skip and not a.startswith("--") and a.isdigit():
            ids.append(int(a))
    return ids, at, hasta, live


if __name__ == "__main__":
    ids, at, hasta, live = _parse_args(sys.argv[1:])
    if not ids:
        print("Uso: python -m tools.probar <id> [<id> ...] [--at N] [--vivo]")
        sys.exit(1)
    service = AlarmsService(ApiClient(BASE_URL))
    print(f"Probando alarmas {ids}…")
    try:
        results = verify_alarms(ids, service, at=at, live=live)
    except Exception as e:
        print(f"\nNo pude probar: {e}\n¿Está la cadena arriba? (sim+proxy+edge) y OmniOps.")
        sys.exit(1)
    _print(results)
    sys.exit(0 if all(r.ok for r in results) else 1)
