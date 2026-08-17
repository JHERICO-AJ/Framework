"""
alarm_oracle.py — ORÁCULO DE CAUSA de las alarmas (prompt 1, el corazón).

Lee el Modbus CRUDO del simulador y, por cada alarma del catálogo, decide si su
CAUSA está realmente presente — sin creerle a OmniOps. Usa el campo `oracle` y
`layer` de alarms_catalog.py y las direcciones del MAPA_DE_BITS.

Qué puede confirmar por capa:
  bit_802      -> Evt1_802  (HR 10095, u32) bit N
  bit_e001     -> Evt1_E001 (HR 9815,  u32) bit N
  bit_fire     -> FireAlarm (HR 9818) != 0  (humo en algún contenedor)
  bit_pcsonline-> PcsOnline (HR 9822): algún PCS con su bit apagado
  telemetry    -> Model 803: FALTA el mapa de registros -> 'no verificable (803)'
  ems / trend  -> causa fuera del Modbus -> 'no verificable'

Los u32 se arman big-endian (palabra alta primero: hi<<16 | lo), como SunSpec.
Verificación del MAPA: inyectar bit 9 y leer HR 10095 debe dar 0x200 (512).

SOLO LEE. pymodbus se usa solo al conectar (self-check corre sin él).

Correr contra el simulador:  python alarm_oracle.py
Probar la lógica sin Modbus: python alarm_oracle.py --self-check
"""

from __future__ import annotations

import sys

from alarms import catalog as cat
from core.source_modbus import LectorModbus, LectorFalso

# cuántos PCS esperamos "en línea" (para PcsOnline). Igual que la capa cálculo.
PCS_COUNT = 3

# estados posibles de la causa
SI = True
NO = False
NV = None            # no verificable


def leer_u32(reader, hr):
    """Arma el entero de 32 bits desde 2 HR consecutivos (big-endian)."""
    hi = reader.leer_registro(hr)
    lo = reader.leer_registro(hr + 1)
    return (hi << 16) | lo


def causa_de(alarma, reader):
    """Devuelve (estado, motivo). estado: True/False (verificado) o None (no verificable)."""
    layer = alarma["layer"]
    o = alarma["oracle"]

    if not alarma.get("oracle_independent", True):
        return NV, "no verificable (ems/trend: causa fuera del Modbus)"

    try:
        if layer in ("bit_802", "bit_e001"):
            # reusamos la propia función del catálogo para no divergir
            presente = cat.read_bit(lambda hr: leer_u32(reader, hr), o["hr"], o["bit"])
            return bool(presente), o["sig"]

        if layer == "bit_fire":
            val = leer_u32(reader, cat.ADDR["fire_alarm"])
            return bool(val != 0), "FireAlarm (HR 9818) != 0"

        if layer == "bit_pcsonline":
            val = leer_u32(reader, cat.ADDR["pcs_online"])
            todos = (1 << PCS_COUNT) - 1          # p. ej. 0b111 con 3 PCS
            hay_caido = (val & todos) != todos
            return bool(hay_caido), f"PcsOnline (HR 9822): algún PCS caído (mask={val & todos:#b})"

        if layer == "telemetry":
            return NV, "no verificable todavía (falta el mapa de registros del Model 803)"

        return NV, f"capa desconocida: {layer}"
    except Exception as e:
        return NV, f"no pude leer el crudo: {e}"


def evaluar(reader, catalogo=None):
    """Corre el oráculo sobre todo el catálogo.
    Devuelve (dict rule_id -> (estado, motivo), set de rule_id con causa presente)."""
    catalogo = catalogo or cat.ALARMS
    estados = {}
    presentes = set()
    for a in catalogo:
        estado, motivo = causa_de(a, reader)
        estados[a["alarm_rule_id"]] = (estado, motivo)
        if estado is SI:
            presentes.add(a["alarm_rule_id"])
    return estados, presentes


# ---------------------------------------------------------------------------
def _self_check():
    print("(prueba del oráculo — lector FALSO, sin Modbus)\n")
    # Evt1_802 (10095/10096): bit 9 (0x200, en la palabra baja) y bit 17 (en la alta)
    #   u32 = 0x00020200 -> hi=0x0002=2, lo=0x0200=512
    # Evt1_E001 (9815/9816): bit 0 (0x1) -> hi=0, lo=1
    # FireAlarm (9818/9819): != 0 -> hi=0, lo=1
    # PcsOnline (9822/9823): 0b111=7 -> todos en línea (sin causa)
    reader = LectorFalso({
        10095: 0x0002, 10096: 0x0200,
        9815: 0x0000, 9816: 0x0001,
        9818: 0x0000, 9819: 0x0001,
        9822: 0x0000, 9823: 0b111,
    })

    esperado = {
        1:  SI,   # bit 9  -> presente
        2:  NO,   # bit 11 -> ausente
        6:  SI,   # bit 17 -> presente (palabra alta)
        46: SI,   # e001 bit 0 -> presente
        38: NO,   # e001 bit 1 -> ausente
        24: SI,   # fire != 0 -> presente
        50: NO,   # pcsonline: todos en línea -> ausente
        16: NV,   # telemetry -> no verificable
        44: NV,   # ems -> no verificable
    }

    estados, presentes = evaluar(reader)
    todos_ok = True
    for rid, exp in esperado.items():
        got, motivo = estados[rid]
        ok = got is exp if exp is None else got == exp
        todos_ok = todos_ok and ok
        nombre = cat.BY_RULE_ID[rid]["name"]
        et = {True: "SÍ", False: "no", None: "n/v"}[got]
        print(f"  ID {rid:2} {nombre:26} causa={et:3} {'OK' if ok else f'MAL (esp {exp})'}")

    # PcsOnline con un PCS caído: bit 0 apagado -> 0b110
    reader2 = LectorFalso({9822: 0, 9823: 0b110})
    got50, _ = causa_de(cat.BY_RULE_ID[50], reader2)
    ok50 = got50 is SI
    todos_ok = todos_ok and ok50
    print(f"  ID 50 PcsOnline con 1 PCS caído       causa={'SÍ' if got50 else 'no'} "
          f"{'OK' if ok50 else 'MAL'}")

    print(f"\n  causas presentes: {sorted(presentes)}")
    print("=> " + ("TODOS OK ✓" if todos_ok else "HAY DIFERENCIAS ✗"))
    return todos_ok


if __name__ == "__main__":
    if "--self-check" in sys.argv:
        sys.exit(0 if _self_check() else 1)

    # contra el simulador real
    try:
        reader = LectorModbus()
    except Exception as e:
        print("No pude conectar al simulador:", e)
        sys.exit(1)
    try:
        estados, presentes = evaluar(reader)
    finally:
        reader.close()

    print("Causa por alarma (leída del crudo):\n")
    for a in cat.ALARMS:
        estado, motivo = estados[a["alarm_rule_id"]]
        et = {True: "SÍ ", False: "no ", None: "n/v"}[estado]
        print(f"  ID {a['alarm_rule_id']:2} {a['name']:34} causa:{et}  ({motivo})")
    print(f"\nCausas presentes ahora: {sorted(presentes) or '(ninguna — simulador sano)'}")
