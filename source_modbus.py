"""
source_modbus.py — la ÚNICA fuente de lectura del simulador (Modbus).

Antes la lectura Modbus estaba en compare_pcs_power.py y REIMPLEMENTADA en
alarms_oracle.py. Ahora vive acá y todos la usan. Esto es también el "lector de
fuente" que el traspaso quería separar para poder enchufar otro simulador
(p. ej. Fractal) cambiando solo este archivo.

Contiene:
  signed16 / w_to_kw       -> conversión de crudos
  read_sim_total_kw()      -> suma de la potencia de los 3 PCS (capa cálculo)
  LectorModbus             -> lee registros sueltos (para el oráculo de alarmas)
  LectorFalso              -> lector de mentira para las pruebas offline

SOLO LEE. pymodbus se importa recién cuando se conecta (para poder testear
la lógica sin tenerlo instalado).

Correr la prueba:  python source_modbus.py --self-check
"""

from __future__ import annotations

import sys

from config import SIM_HOST, SIM_PORT, SIM_UNIT, PCS_W_REGS


def signed16(raw):
    return raw - 65536 if raw > 32767 else raw


def w_to_kw(raw, sf):
    """potencia de un PCS en kW = raw_con_signo * 10^sf / 1000 (W -> kW)."""
    return signed16(raw) * (10 ** signed16(sf)) / 1000.0


def _read(client, addr, count):
    # pymodbus nuevo usa device_id=; el viejo usa slave=
    try:
        return client.read_holding_registers(addr, count=count, device_id=SIM_UNIT)
    except TypeError:
        return client.read_holding_registers(addr, count=count, slave=SIM_UNIT)


def read_sim_total_kw():
    """Suma la potencia de los 3 PCS leyendo el simulador por Modbus.
    Devuelve (total_kw, [(registro, kw), ...])."""
    from pymodbus.client import ModbusTcpClient

    client = ModbusTcpClient(SIM_HOST, port=SIM_PORT)
    if not client.connect():
        raise ConnectionError(f"no pude conectar al simulador {SIM_HOST}:{SIM_PORT} "
                              "(¿está corriendo el simulador?)")
    try:
        total = 0.0
        detalle = []
        for w_addr, sf_addr in PCS_W_REGS:
            rr = _read(client, w_addr, 2)
            if rr.isError():
                raise IOError(f"error leyendo registro {w_addr}")
            raw = rr.registers[0]
            sf = _read(client, sf_addr, 1).registers[0]
            kw = w_to_kw(raw, sf)
            total += kw
            detalle.append((w_addr, kw))
        return total, detalle
    finally:
        client.close()


# --- lectores de registros sueltos (para el oráculo de alarmas) ------------
class LectorModbus:
    """Lee el simulador real por Modbus, registro por registro."""

    def __init__(self, host=SIM_HOST, port=SIM_PORT, unit=SIM_UNIT):
        from pymodbus.client import ModbusTcpClient
        self._client = ModbusTcpClient(host, port=port)
        self._unit = unit
        if not self._client.connect():
            raise ConnectionError(
                f"no pude conectar al simulador {host}:{port} "
                "(¿está corriendo el simulador?)")

    def leer_registro(self, addr):
        try:
            rr = self._client.read_holding_registers(addr, count=1, device_id=self._unit)
        except TypeError:
            rr = self._client.read_holding_registers(addr, count=1, slave=self._unit)
        if rr.isError():
            raise IOError(f"error leyendo registro {addr}")
        return rr.registers[0]

    def close(self):
        try:
            self._client.close()
        except Exception:
            pass


class LectorFalso:
    """Para pruebas: un dict {direccion: valor_crudo_16bits}."""

    def __init__(self, registros):
        self._r = dict(registros)

    def leer_registro(self, addr):
        if addr not in self._r:
            raise IOError(f"registro {addr} no está en el lector falso")
        return self._r[addr]

    def close(self):
        pass


# ---------------------------------------------------------------------------
SAMPLE_SIM = [(17014, 14218, 2), (17114, 14176, 2), (17214, 7100, 2)]


def _self_check():
    print("(prueba de source_modbus — conversión + lector falso, sin red)\n")
    detalle = [(a, w_to_kw(raw, sf)) for a, raw, sf in SAMPLE_SIM]
    total = sum(kw for _, kw in detalle)
    for a, kw in detalle:
        print(f"  reg {a}: {kw:9.1f} kW")
    print(f"  TOTAL: {total:.1f} kW")
    ok1 = signed16(65535) == -1 and signed16(1) == 1
    lf = LectorFalso({100: 0b1000, 101: 5})
    ok2 = lf.leer_registro(100) == 8 and lf.leer_registro(101) == 5
    print(f"\n  signed16 -> {'OK' if ok1 else 'MAL'}")
    print(f"  LectorFalso -> {'OK' if ok2 else 'MAL'}")
    print("=> " + ("OK ✓" if ok1 and ok2 else "MAL ✗"))
    return ok1 and ok2


if __name__ == "__main__":
    sys.exit(0 if _self_check() else 1)
