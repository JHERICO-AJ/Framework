"""
alarms_oracle.py — el ORÁCULO DE CAUSA de las alarmas.

Responde una sola pregunta por alarma, mirando SOLO el crudo del simulador
(nunca a OmniOps): ¿está presente la condición que DEBERÍA disparar esta alarma?

Dos tipos de causa (los que describe el traspaso, §7):

  - "bit"    : un bit de una palabra de estado/falla (p. ej. Evt1). La causa está
               activa si ese bit vale 1.
                 {"tipo": "bit", "registro": 1234, "bit": 5}

  - "umbral" : una medida de telemetría que cruza un límite. La causa está activa
               si la medida (con su scale factor opcional) cumple el operador.
                 {"tipo": "umbral", "registro": 5678, "sf_registro": 5679,
                  "operador": ">", "limite": 55.0}
               (sf_registro es opcional; si no está, se usa el valor crudo con signo)

El "engine" ya está completo. Lo único que falta para usarlo de verdad son los
NÚMEROS (qué registro / qué bit / qué límite por alarma), que viven en el
catálogo (alarms_catalog.py, traducido del SPEC90 / MAPA_DE_BITS.md).

SOLO LEE por Modbus. Se puede probar entero sin simulador con un lector falso.

Correr la prueba:  python alarms_oracle.py --self-check
"""

from __future__ import annotations

import sys

# los lectores del crudo viven ahora en source_modbus (fuente única)
from source_modbus import signed16, LectorModbus, LectorFalso


# ---------------------------------------------------------------------------
# El oráculo
# ---------------------------------------------------------------------------
_OPERADORES = {
    ">":  lambda v, l: v > l,
    ">=": lambda v, l: v >= l,
    "<":  lambda v, l: v < l,
    "<=": lambda v, l: v <= l,
    "==": lambda v, l: v == l,
    "!=": lambda v, l: v != l,
}


def _valor_escalado(lector, registro, sf_registro):
    raw = signed16(lector.leer_registro(registro))
    if sf_registro is None:
        return float(raw)
    sf = signed16(lector.leer_registro(sf_registro))
    return raw * (10 ** sf)


def causa_activa(entry, lector):
    """True/False si la causa de `entry` está presente en el crudo.
    Devuelve None si la alarma no es verificable por oráculo (ems/trend) o si
    la definición de causa está incompleta/rota."""
    if not entry.get("oracle_independent", True):
        return None                      # ems/trend: no verificable a propósito
    causa = entry.get("causa")
    if not isinstance(causa, dict):
        return None                      # catálogo sin causa definida todavía

    tipo = causa.get("tipo")
    if tipo == "bit":
        reg = causa.get("registro")
        bit = causa.get("bit")
        if reg is None or bit is None:
            return None
        palabra = lector.leer_registro(reg)
        return bool((palabra >> bit) & 1)

    if tipo == "umbral":
        reg = causa.get("registro")
        op = _OPERADORES.get(causa.get("operador"))
        lim = causa.get("limite")
        if reg is None or op is None or lim is None:
            return None
        valor = _valor_escalado(lector, reg, causa.get("sf_registro"))
        return bool(op(valor, float(lim)))

    return None                          # tipo desconocido


def abrir_lector_real():
    """Atajo para el monitor: devuelve un LectorModbus conectado."""
    return LectorModbus()


# ---------------------------------------------------------------------------
def _self_check():
    print("(prueba del oráculo de causa — lector FALSO, sin Modbus)\n")

    # registro 1000 = palabra de falla con el bit 5 en 1  (0b100000 = 32)
    # registro 2000 = temperatura cruda 60, sf en 2001 = 0  -> 60.0
    # registro 3000 = potencia cruda 20, sf en 3001 = 2     -> 2000.0
    lector = LectorFalso({
        1000: 0b0000_0000_0010_0000,   # bit 5 = 1
        1001: 0b0000_0000_0000_0000,   # ningún bit
        2000: 60, 2001: 0,
        3000: 20, 3001: 2,
    })

    casos = [
        ("bit activo",
         {"oracle_independent": True,
          "causa": {"tipo": "bit", "registro": 1000, "bit": 5}}, True),
        ("bit inactivo",
         {"oracle_independent": True,
          "causa": {"tipo": "bit", "registro": 1001, "bit": 5}}, False),
        ("umbral temp > 55 (vale 60)",
         {"oracle_independent": True,
          "causa": {"tipo": "umbral", "registro": 2000, "sf_registro": 2001,
                    "operador": ">", "limite": 55.0}}, True),
        ("umbral temp > 55 pero vale 60... no, < 55 (vale 60) -> False",
         {"oracle_independent": True,
          "causa": {"tipo": "umbral", "registro": 2000, "sf_registro": 2001,
                    "operador": "<", "limite": 55.0}}, False),
        ("umbral escalado pot > 1500 (vale 2000)",
         {"oracle_independent": True,
          "causa": {"tipo": "umbral", "registro": 3000, "sf_registro": 3001,
                    "operador": ">", "limite": 1500.0}}, True),
        ("no verificable (ems/trend)",
         {"oracle_independent": False,
          "causa": {"tipo": "bit", "registro": 1000, "bit": 5}}, None),
        ("catálogo sin causa aún",
         {"oracle_independent": True}, None),
    ]

    todos_ok = True
    for nombre, entry, esperado in casos:
        got = causa_activa(entry, lector)
        ok = got is esperado if esperado is None else got == esperado
        todos_ok = todos_ok and ok
        print(f"  {nombre:48} -> {str(got):5} "
              f"{'OK' if ok else f'MAL (esperaba {esperado})'}")
    print("\n=> " + ("TODOS OK ✓" if todos_ok else "HAY DIFERENCIAS ✗"))
    return todos_ok


if __name__ == "__main__":
    if "--self-check" in sys.argv or len(sys.argv) == 1:
        sys.exit(0 if _self_check() else 1)
