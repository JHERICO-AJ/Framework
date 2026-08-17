"""
alarms/api.py — LEE las alarmas de OmniOps (la "verdad" del lado plataforma).

Clavado a la respuesta REAL de OmniOps: GET /api/events/alarms/filtered devuelve
un ARRAY plano de alarmas, una fila por device, con estos campos (los que usamos):

  alarmRuleId, alarm, subsystem, signal, severity, status,
  firstOccurred, lastOccurred, siteId, deviceId, deviceName, count

La API es la ventana a la BD/caché: si una alarma está acá con status "Open",
está en la base. Reusa auth.py para el token. SOLO LEE.

Nota: varias filas pueden compartir alarmRuleId (una por device). Para validar
agrupamos por alarmRuleId.

Correr:            python -m alarms.api            (contra OmniOps)
Volcar crudo:      python -m alarms.api --dump
Probar el parser:  python -m alarms.api --self-check
"""

from __future__ import annotations

import datetime
import json
import os
import sys

from core.auth import make_auth
from config import BASE_URL, ALARMS_PATH


def _fecha(texto):
    """'2026-08-13 18:39:53' -> datetime (o None)."""
    if not texto:
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S.%f"):
        try:
            return datetime.datetime.strptime(texto, fmt)
        except ValueError:
            continue
    return None


class Alarma:
    def __init__(self, d):
        self.raw = d
        self.rule_id = d.get("alarmRuleId")
        self.nombre = d.get("alarm")
        self.subsystem = d.get("subsystem")
        self.signal = d.get("signal")
        self.severity = d.get("severity")
        self.status = d.get("status")
        self.first_occurred = _fecha(d.get("firstOccurred"))
        self.last_occurred = _fecha(d.get("lastOccurred"))
        self.site_id = d.get("siteId")
        self.device_id = d.get("deviceId")
        self.device_name = d.get("deviceName")
        self.count = d.get("count")

    @property
    def abierta(self):
        return (self.status or "").strip().lower() == "open"

    def __repr__(self):
        return (f"Alarma(rule_id={self.rule_id}, {self.nombre!r}, "
                f"{self.severity}, {self.status}, dev={self.device_name})")


def normalizar(payload):
    """De la respuesta (array plano, o envuelta) -> lista de Alarma."""
    filas = payload
    if isinstance(payload, dict):
        for k in ("items", "data", "results", "alarms", "value"):
            if isinstance(payload.get(k), list):
                filas = payload[k]
                break
    if not isinstance(filas, list):
        return []
    return [Alarma(d) for d in filas if isinstance(d, dict)]


def leer_alarmas(auth=None, solo_abiertas=True):
    """Devuelve (lista_de_Alarma, payload_crudo)."""
    auth = auth or make_auth(BASE_URL)
    payload = auth.authorized_get(BASE_URL + ALARMS_PATH)
    alarmas = normalizar(payload)
    if solo_abiertas:
        alarmas = [a for a in alarmas if a.abierta]
    return alarmas, payload


def rule_ids_abiertos(alarmas):
    """Set de alarmRuleId que están Open."""
    return {a.rule_id for a in alarmas if a.abierta and a.rule_id is not None}


def por_rule_id(alarmas):
    """dict {alarmRuleId: [Alarma, ...]} (agrupa las filas por device)."""
    out = {}
    for a in alarmas:
        out.setdefault(a.rule_id, []).append(a)
    return out


def primera_ultima(alarmas, rule_id):
    """(firstOccurred mínimo, lastOccurred máximo) entre las filas de esa alarma.
    Sirve para comparar contra el timeline del oráculo. None si no está."""
    filas = [a for a in alarmas if a.rule_id == rule_id]
    firsts = [a.first_occurred for a in filas if a.first_occurred]
    lasts = [a.last_occurred for a in filas if a.last_occurred]
    return (min(firsts) if firsts else None, max(lasts) if lasts else None)


# ---------------------------------------------------------------------------
def _self_check():
    print("(prueba del parser de alarmas — contra el fixture real, sin red)\n")
    ruta = os.path.join(os.path.dirname(__file__), "..", "tests", "fixtures",
                        "alarms_sample.json")
    with open(ruta, encoding="utf-8") as fh:
        payload = json.load(fh)

    alarmas = normalizar(payload)
    for a in alarmas:
        print("  ", a)

    ids = rule_ids_abiertos(alarmas)
    grupos = por_rule_id(alarmas)
    pf, ul = primera_ultima(alarmas, 50)

    ok_ids = ids == {49, 50, 44}
    ok_grupo = len(grupos.get(50, [])) == 2          # PCS Comm Lost en 2 devices
    ok_fecha = alarmas[0].first_occurred == datetime.datetime(2026, 8, 4, 13, 32, 4)
    ok_pu = (pf == datetime.datetime(2026, 8, 4, 13, 35, 44) and
             ul == datetime.datetime(2026, 8, 13, 18, 39, 18))

    print(f"\n  rule_ids abiertos: {sorted(ids)}  {'OK' if ok_ids else 'MAL'}")
    print(f"  agrupado ID 50 -> {len(grupos.get(50, []))} filas  {'OK' if ok_grupo else 'MAL'}")
    print(f"  fecha parseada -> {alarmas[0].first_occurred}  {'OK' if ok_fecha else 'MAL'}")
    print(f"  first/last ID 50 -> {pf} / {ul}  {'OK' if ok_pu else 'MAL'}")
    todos = ok_ids and ok_grupo and ok_fecha and ok_pu
    print("\n=> " + ("TODOS OK ✓" if todos else "HAY DIFERENCIAS ✗"))
    return todos


if __name__ == "__main__":
    if "--self-check" in sys.argv:
        sys.exit(0 if _self_check() else 1)

    if "--dump" in sys.argv:
        auth = make_auth(BASE_URL)
        payload = auth.authorized_get(BASE_URL + ALARMS_PATH)
        print(json.dumps(payload, indent=2, ensure_ascii=False)[:4000])
        sys.exit(0)

    try:
        alarmas, _ = leer_alarmas()
    except Exception as e:
        print("No pude leer la API de alarmas:", e)
        sys.exit(1)

    grupos = por_rule_id(alarmas)
    print(f"Alarmas abiertas: {len(alarmas)} filas, {len(grupos)} tipos (alarmRuleId).\n")
    for rid in sorted(grupos):
        filas = grupos[rid]
        pf, ul = primera_ultima(alarmas, rid)
        print(f"  ID {rid:2} {filas[0].nombre:26} x{len(filas)} dev  "
              f"first={pf}  last={ul}")
