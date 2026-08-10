"""
alarm_oracle.py — ORÁCULO DE CAUSA para Alarms & Events.

Lee el Modbus CRUDO (misma conexión que compare_pcs_power.py) y, para cada
alarma del catálogo, determina si su CAUSA está REALMENTE presente:

  bit_802 / bit_e001 : bit exacto del Evt1 correspondiente (vía
                        alarms_catalog.read_bit), usando el campo `oracle`.
  bit_fire           : FireAlarm (HR 9818) != 0 -> algún contenedor con humo.
                        (el catálogo no da un bit puntual para esto: mira el
                        registro completo)
  bit_pcsonline       : PcsOnline (HR 9822) con algún PCS caído (bit apagado),
                        sobre los PCS conocidos (PCS_COUNT, de compare_pcs_power).
  telemetry           : PENDIENTE. El catálogo no trae direcciones Model 803
                        por métrica (t_max, cv_max, current_a, ...) -> se
                        marca 'no verificable' hasta tener ese mapa.
  oracle_independent=False (ems/trend): la causa no está en el Modbus (se
                        calcula en OmniOps) -> 'no verificable', no se toca.

Orden de palabras del Evt1 (32 bits en 2 HR): HR base = palabra BAJA,
HR base+1 = palabra ALTA (u32 = hi<<16 | lo). Confirmado por el self-check de
MAPA_DE_BITS.md: inyectando bit 9 y leyendo solo HR 10095 debe dar 0x200; eso
solo es posible si la palabra baja vive en la dirección base. Si el simulador
real resulta usar el orden inverso, corregir en read_u32().

SOLO LEE. Necesita pymodbus y el simulador corriendo.

Correr:            python alarm_oracle.py
Probar la lógica:  python alarm_oracle.py --self-check
"""

from __future__ import annotations

import os
import sys

# compare_pcs_power.py vive en la raíz del framework, un nivel arriba de esta carpeta.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from alarms_catalog import ADDR, ALARMS, read_bit
from compare_pcs_power import PCS_W_REGS, SIM_HOST, SIM_PORT, UNIT

PCS_COUNT = len(PCS_W_REGS)          # 3 PCS, confirmado en compare_pcs_power.py
PCS_ONLINE_MASK = (1 << PCS_COUNT) - 1


def _read_regs(client, addr, count):
    # pymodbus nuevo usa device_id=; el viejo usa slave= (igual que compare_pcs_power.py)
    try:
        return client.read_holding_registers(addr, count=count, device_id=UNIT)
    except TypeError:
        return client.read_holding_registers(addr, count=count, slave=UNIT)


def read_u16(client, hr):
    rr = _read_regs(client, hr, 1)
    if rr.isError():
        raise IOError(f"error leyendo registro {hr}")
    return rr.registers[0]


def read_u32(client, hr):
    """Lee 2 HR consecutivos (hr, hr+1) y devuelve el entero de 32 bits.
    hr = palabra baja, hr+1 = palabra alta (ver nota de orden en el docstring)."""
    rr = _read_regs(client, hr, 2)
    if rr.isError():
        raise IOError(f"error leyendo registro {hr}")
    lo, hi = rr.registers
    return (hi << 16) | lo


def connect():
    from pymodbus.client import ModbusTcpClient

    client = ModbusTcpClient(SIM_HOST, port=SIM_PORT)
    if not client.connect():
        raise ConnectionError(f"no pude conectar al simulador {SIM_HOST}:{SIM_PORT} "
                              "(¿está corriendo bess_modbus_simulator.py?)")
    return client


def _causa_alarma(a, evt1_802, evt1_e001, fire, pcs_online):
    """(presente|None, detalle). presente=None = 'no verificable'."""
    oracle = a["oracle"]
    layer = a["layer"]

    if not a["oracle_independent"]:
        return None, "no verificable (causa fuera del Modbus)"

    if layer == "bit_802":
        presente = read_bit(lambda _hr: evt1_802, oracle["hr"], oracle["bit"])
        return presente, f"{oracle['sig']} = {'ON' if presente else 'off'}"

    if layer == "bit_e001":
        presente = read_bit(lambda _hr: evt1_e001, oracle["hr"], oracle["bit"])
        return presente, f"{oracle['sig']} = {'ON' if presente else 'off'}"

    if layer == "bit_fire":
        presente = fire != 0
        return presente, f"FireAlarm (HR {ADDR['fire_alarm']}) = 0x{fire:04X}"

    if layer == "bit_pcsonline":
        presente = (pcs_online & PCS_ONLINE_MASK) != PCS_ONLINE_MASK
        return presente, (f"PcsOnline (HR {ADDR['pcs_online']}) = 0x{pcs_online:04X} "
                          f"(mask esperada 0x{PCS_ONLINE_MASK:X} para {PCS_COUNT} PCS)")

    if layer == "telemetry":
        return None, "no verificable (falta mapa de registros Model 803 por métrica)"

    return None, f"no verificable (layer desconocida: {layer!r})"


def leer_causas(client=None):
    """Lee el crudo UNA vez y evalúa la causa de cada alarma del catálogo.
    Devuelve {alarm_rule_id: (presente|None, detalle)}."""
    cerrar = client is None
    client = client or connect()
    try:
        evt1_802 = read_u32(client, ADDR["evt1_802"])
        evt1_e001 = read_u32(client, ADDR["evt1_e001"])
        fire = read_u16(client, ADDR["fire_alarm"])
        pcs_online = read_u16(client, ADDR["pcs_online"])
    finally:
        if cerrar:
            client.close()

    return {a["alarm_rule_id"]: _causa_alarma(a, evt1_802, evt1_e001, fire, pcs_online)
            for a in ALARMS}


def causas_presentes(client=None):
    """El conjunto de alarmRuleId cuya causa está REALMENTE presente en el
    crudo ahora mismo (excluye los 'no verificable')."""
    return {rid for rid, (presente, _) in leer_causas(client).items() if presente}


def report(causas):
    verificables = {rid: v for rid, v in causas.items() if v[0] is not None}
    presentes = [rid for rid, (p, _) in verificables.items() if p]
    no_verificables = [rid for rid, (p, _) in causas.items() if p is None]

    print(f"\nCausas presentes en el crudo ahora: {sorted(presentes) or '(ninguna)'}")
    print(f"No verificables (EMS/trend o telemetry pendiente): {len(no_verificables)} alarmas")
    print()
    for rid, (presente, detalle) in sorted(causas.items()):
        nombre = next(a["name"] for a in ALARMS if a["alarm_rule_id"] == rid)
        estado = "PRESENTE" if presente else ("no verificable" if presente is None else "ausente")
        print(f"  [{rid:>3}] {nombre:35s} {estado:15s} {detalle}")
    return presentes


# --- prueba de la lógica de decodificación (sin simulador) -----------------
def self_check():
    print("(prueba de _causa_alarma con registros fabricados, sin conectar al simulador)")

    # bit 9 de Evt1_802 (Cell Overvoltage) prendido -> 0x200 en la palabra baja
    evt1_802 = 0x200
    evt1_e001 = 0
    fire = 0
    pcs_online = PCS_ONLINE_MASK   # todos los PCS en línea

    cell_ov = next(a for a in ALARMS if a["alarm_rule_id"] == 1)
    presente, detalle = _causa_alarma(cell_ov, evt1_802, evt1_e001, fire, pcs_online)
    print(f"Cell Overvoltage con evt1_802=0x{evt1_802:X} -> {presente} ({detalle}) "
          "(esperado True)")

    rack_door = next(a for a in ALARMS if a["alarm_rule_id"] == 23)   # bit 23
    presente, detalle = _causa_alarma(rack_door, evt1_802, evt1_e001, fire, pcs_online)
    print(f"Rack Door Open (bit 23) con evt1_802=0x{evt1_802:X} -> {presente} "
          "(esperado False, bit 23 no está prendido)")

    smoke = next(a for a in ALARMS if a["alarm_rule_id"] == 24)
    presente, _ = _causa_alarma(smoke, evt1_802, evt1_e001, fire=1, pcs_online=pcs_online)
    print(f"Rack Smoke Detected con FireAlarm=1 -> {presente} (esperado True)")

    pcs_comm = next(a for a in ALARMS if a["alarm_rule_id"] == 50)
    presente, _ = _causa_alarma(pcs_comm, evt1_802, evt1_e001, fire=0,
                                pcs_online=PCS_ONLINE_MASK & ~1)   # PCS 1 caído
    print(f"PCS Communication Lost con un PCS caído -> {presente} (esperado True)")

    ems = next(a for a in ALARMS if a["alarm_rule_id"] == 51)   # EMS-BMS Comm Lost
    presente, detalle = _causa_alarma(ems, evt1_802, evt1_e001, fire, pcs_online)
    print(f"EMS-BMS Comm Lost -> {presente} ({detalle}) (esperado None)")

    telem = next(a for a in ALARMS if a["alarm_rule_id"] == 16)   # Rack High Temp
    presente, detalle = _causa_alarma(telem, evt1_802, evt1_e001, fire, pcs_online)
    print(f"Rack High Temp (telemetry) -> {presente} ({detalle}) (esperado None)")


if __name__ == "__main__":
    if "--self-check" in sys.argv:
        self_check()
        sys.exit(0)

    try:
        causas = leer_causas()
    except Exception as e:
        print("No pude leer el simulador:", e)
        sys.exit(1)
    report(causas)
