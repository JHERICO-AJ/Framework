"""
alarms_api.py — LEE las alarmas de OmniOps (la "verdad" del lado plataforma).

Es el equivalente, para alarmas, de lo que check_pcs_power.py es para la potencia:
pide el endpoint y normaliza la respuesta a una lista simple de alarmas abiertas.

  GET /api/events/alarms/filtered?Status=Open

Usa el mismo portero (auth.py), así que se loguea y renueva el token solo.
SOLO LEE: no cierra ni reconoce alarmas, no escribe nada.

OJO — nombres de campos: todavía no vimos la forma REAL de la respuesta. El
parser de abajo prueba las formas más comunes y expone el dict crudo de cada
alarma en `.raw`. Cuando la corras contra OmniOps real, usá:

    python alarms_api.py --dump

para volcar la respuesta cruda; con eso ajustamos las 2-3 líneas marcadas
"AJUSTAR" y queda clavado.

Correr (contra OmniOps):     python alarms_api.py
Volcar respuesta cruda:      python alarms_api.py --dump
Probar el parser sin red:    python alarms_api.py --self-check
"""

from __future__ import annotations

import json
import sys
import urllib.parse

from auth import make_auth
from config import BASE_URL, ALARMS_PATH


class Alarma:
    """Una alarma normalizada. `raw` guarda el dict original por si falta algo."""

    def __init__(self, codigo, nombre, estado, timestamp, raw):
        self.codigo = codigo        # identificador estable para matchear con el catálogo
        self.nombre = nombre        # texto legible
        self.estado = estado        # "Open" / "Closed" / ...
        self.timestamp = timestamp
        self.raw = raw

    def __repr__(self):
        return (f"Alarma(codigo={self.codigo!r}, nombre={self.nombre!r}, "
                f"estado={self.estado!r})")


# --- extracción de campos (AJUSTAR con la respuesta real, ver --dump) --------
def _primero(d, *claves):
    """Devuelve el primer valor no-None entre varias claves candidatas."""
    for k in claves:
        if isinstance(d, dict) and d.get(k) is not None:
            return d.get(k)
    return None


def _normalizar_una(d):
    # AJUSTAR: agregá/quitá candidatos cuando veas los nombres reales.
    codigo = _primero(d, "code", "alarmCode", "type", "alarmType",
                       "eventCode", "id")
    nombre = _primero(d, "name", "alarmName", "description", "message",
                      "title")
    estado = _primero(d, "status", "state", "alarmStatus")
    ts = _primero(d, "timestamp", "raisedAt", "openedAt", "createdAt",
                  "startTime")
    return Alarma(codigo, nombre, estado, ts, d)


def _extraer_lista(payload):
    """La respuesta puede venir como lista, o envuelta en items/data/results/..."""
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        for k in ("items", "data", "results", "alarms", "value", "records"):
            v = payload.get(k)
            if isinstance(v, list):
                return v
        # a veces viene {data: {items: [...]}}
        for k in ("data", "result"):
            v = payload.get(k)
            if isinstance(v, dict):
                inner = _extraer_lista(v)
                if inner:
                    return inner
    return []


def normalizar(payload):
    """De la respuesta cruda -> lista de Alarma."""
    return [_normalizar_una(d) for d in _extraer_lista(payload) if isinstance(d, dict)]


# --- acceso a la API --------------------------------------------------------
def _url(status="Open", extra=None):
    params = {}
    if status:
        params["Status"] = status
    if extra:
        params.update(extra)
    q = ("?" + urllib.parse.urlencode(params)) if params else ""
    return f"{BASE_URL}{ALARMS_PATH}{q}"


def leer_alarmas(auth=None, status="Open"):
    """Devuelve (lista_de_Alarma, payload_crudo). status=None trae todas."""
    auth = auth or make_auth(BASE_URL)
    payload = auth.authorized_get(_url(status=status))
    return normalizar(payload), payload


def abiertas_por_codigo(alarmas):
    """dict {codigo: Alarma} de las que están Open. Útil para el cruce con el catálogo."""
    out = {}
    for a in alarmas:
        if (a.estado or "").strip().lower() in ("open", "active", "raised", "1", "true"):
            if a.codigo is not None:
                out[a.codigo] = a
    return out


# ---------------------------------------------------------------------------
_SAMPLE = {
    "items": [
        {"code": "OV_PCS", "name": "Sobretensión PCS", "status": "Open",
         "timestamp": "2026-08-11T14:00:03.100Z"},
        {"alarmType": "TEMP_HI", "description": "Temperatura alta",
         "state": "Open", "raisedAt": "2026-08-11T14:00:05.000Z"},
        {"code": "COMMS", "name": "Pérdida de comunicación", "status": "Closed",
         "timestamp": "2026-08-11T13:50:00.000Z"},
    ]
}


def _self_check():
    print("(prueba del parser de alarmas — usa una muestra, sin red)\n")
    alarmas = normalizar(_SAMPLE)
    for a in alarmas:
        print("  ", a)
    abiertas = abiertas_por_codigo(alarmas)
    print(f"\n  abiertas: {sorted(abiertas)}")
    ok = set(abiertas) == {"OV_PCS", "TEMP_HI"}
    print("=> " + ("OK ✓ (2 abiertas, la Closed queda afuera)"
                   if ok else "MAL ✗"))
    return ok


if __name__ == "__main__":
    if "--self-check" in sys.argv:
        sys.exit(0 if _self_check() else 1)

    if "--dump" in sys.argv:
        # volcar la respuesta cruda para fijar los nombres de campos
        auth = make_auth(BASE_URL)
        try:
            payload = auth.authorized_get(_url(status="Open"))
        except Exception as e:
            print("No pude leer la API de alarmas:", e)
            sys.exit(1)
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        print("\n--- normalizado ---")
        for a in normalizar(payload):
            print("  ", a)
        sys.exit(0)

    try:
        alarmas, _ = leer_alarmas(status="Open")
    except FileNotFoundError as e:
        print(e)
        sys.exit(1)
    except Exception as e:
        print("No pude leer la API de alarmas:", e)
        print("Revisá que OmniOps esté corriendo y las credenciales en omniops_login.txt.")
        sys.exit(1)

    if not alarmas:
        print("Sin alarmas abiertas ahora (o la respuesta vino en un formato "
              "que el parser no reconoció -> probá  python alarms_api.py --dump).")
    else:
        print(f"Alarmas abiertas ({len(alarmas)}):")
        for a in alarmas:
            print(f"  [{a.estado}] {a.codigo}  {a.nombre}   ({a.timestamp})")
