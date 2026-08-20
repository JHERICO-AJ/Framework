"""
sim_proxy.py — PROXY Modbus que se mete entre el edge y el simulador real,
para poder INYECTAR alarmas sin tocar ningún otro repo.

     edge  ──►  proxy (5020)  ──►  simulador REAL (5021)  ──►  OmniOps

En cada lectura, el proxy trae el dato FRESCO del simulador real y, si hay algo
inyectado (lo que dejó `alarms/inject.py` en INJECT_STATE_FILE), pisa esos
registros antes de devolverlos. El edge (y por lo tanto OmniOps) recibe la
condición como si viniera del simulador. Cuando no hay inyección, es invisible.

CÓMO USARLO (en local, desde la RAÍZ del proyecto):
  1) Simulador REAL en 5021 (mové el puerto en tu comando de siempre):
       python <ruta>\\simulator\\bess_modbus_simulator.py 127.0.0.1 5021 5
  2) Proxy en 5020:
       python -m tools.sim_proxy
  3) El edge y OmniOps arrancan como siempre (siguen leyendo 5020 = el proxy).
  4) Disparás una alarma cuando quieras, desde otra terminal:
       python -m alarms.inject 24          # enciende "Rack Smoke Detected"
       python -m alarms.inject 1 --at 10   # enciende Cell Overvoltage a los 10s
       python -m alarms.inject --clear     # apaga la inyección

Probar el proxy sin el simulador real (loopback):  python -m tools.sim_proxy --self-check
"""

from __future__ import annotations

import sys
import threading
import time

from pymodbus.client import ModbusTcpClient
from pymodbus.datastore import ModbusServerContext, ModbusSlaveContext
from pymodbus.datastore.store import BaseModbusDataBlock
from pymodbus.server import StartTcpServer

from shared.config.settings import SIM_HOST, SIM_PORT, SIM_REAL_HOST, SIM_REAL_PORT, SIM_UNIT
from shared.domain.injection import leer_estado


class _UpstreamReader:
    """Cliente hacia el simulador real, con reconexión. Lee registros frescos."""

    def __init__(self, host, port, unit):
        self.host, self.port, self.unit = host, port, unit
        self._c = None

    def _cliente(self):
        if self._c is None:
            self._c = ModbusTcpClient(self.host, port=self.port)
        if not getattr(self._c, "connected", False):
            self._c.connect()
        return self._c

    def leer(self, address, count):
        c = self._cliente()
        try:
            rr = c.read_holding_registers(address, count=count, device_id=self.unit)
        except TypeError:
            rr = c.read_holding_registers(address, count=count, slave=self.unit)
        if rr.isError():
            raise IOError(f"upstream error leyendo {address}..{address+count-1}")
        return list(rr.registers)


class ProxyBlock(BaseModbusDataBlock):
    """Bloque de holding registers que, en vez de guardar datos, los trae del
    simulador real en cada pedido y aplica la inyección."""

    def __init__(self, upstream):
        self.upstream = upstream
        self.address = 0
        self.values = {}
        self.default_value = 0

    def validate(self, address, count=1):
        return True                     # aceptamos cualquier dirección; valida el real

    def getValues(self, address, count=1):
        regs = self.upstream.leer(address, count)
        pon, qui, rep = leer_estado()   # estado de inyección FRESCO en cada lectura
        if pon or qui or rep:
            out = []
            for i, v in enumerate(regs):
                reg = address + i
                if reg in rep:
                    v = rep[reg]                       # REPLACE (telemetría) gana
                else:
                    v = (v | pon.get(reg, 0)) & ~qui.get(reg, 0)
                out.append(v & 0xFFFF)
            return out
        return regs

    def setValues(self, address, values):
        pass                            # proxy de solo lectura

    def reset(self):
        pass


def _hacer_contexto():
    upstream = _UpstreamReader(SIM_REAL_HOST, SIM_REAL_PORT, SIM_UNIT)
    bloque = ProxyBlock(upstream)
    # zero_mode=True -> las direcciones pasan TAL CUAL (el proxy pide al real la
    # misma dirección que pidió el edge).
    slave = ModbusSlaveContext(hr=bloque, ir=bloque, zero_mode=True)
    return ModbusServerContext(slaves=slave, single=True)


def run():
    print(f"Proxy Modbus escuchando en {SIM_HOST}:{SIM_PORT}  ->  "
          f"simulador real en {SIM_REAL_HOST}:{SIM_REAL_PORT}")
    print("Inyectá con:  python -m alarms.inject <id>   (apagar: --clear)\n")
    StartTcpServer(context=_hacer_contexto(), address=(SIM_HOST, SIM_PORT))


# ---------------------------------------------------------------------------
def _self_check():
    """Loopback real: levanta un 'sim' de mentira, el proxy delante, y lee a
    través del proxy — con y sin inyección."""
    from pymodbus.datastore import ModbusSequentialDataBlock
    from shared.domain.injection import guardar_estado, limpiar_estado

    print("(loopback: sim falso 5599 -> proxy 5598 -> cliente)\n")
    HR_BASE, PROXY_P, REAL_P = 10095, 5598, 5599

    # sim de mentira: registros 10095.. con ceros (bloque grande)
    bloque_real = ModbusSequentialDataBlock(0, [0] * 20000)
    ctx_real = ModbusServerContext(
        slaves=ModbusSlaveContext(hr=bloque_real, ir=bloque_real, zero_mode=True),
        single=True)
    threading.Thread(target=StartTcpServer,
                     kwargs={"context": ctx_real, "address": ("127.0.0.1", REAL_P)},
                     daemon=True).start()

    # proxy apuntando al sim de mentira
    up = _UpstreamReader("127.0.0.1", REAL_P, 1)
    blk = ProxyBlock(up)
    ctx_proxy = ModbusServerContext(
        slaves=ModbusSlaveContext(hr=blk, ir=blk, zero_mode=True), single=True)
    threading.Thread(target=StartTcpServer,
                     kwargs={"context": ctx_proxy, "address": ("127.0.0.1", PROXY_P)},
                     daemon=True).start()
    time.sleep(1.5)

    cli = ModbusTcpClient("127.0.0.1", port=PROXY_P)
    cli.connect()

    def leer(addr, n):
        try:
            rr = cli.read_holding_registers(addr, count=n, device_id=1)
        except TypeError:
            rr = cli.read_holding_registers(addr, count=n, slave=1)
        return list(rr.registers)

    limpiar_estado()
    sin = leer(HR_BASE, 2)
    ok1 = sin == [0, 0]
    print(f"  sin inyección, HR {HR_BASE}..+1 -> {sin}  {'OK' if ok1 else 'MAL'}")

    # inyectar Cell Overvoltage (ID 1 = bit 9 -> HR 10096 = 0x200)
    guardar_estado([1])
    con = leer(HR_BASE, 2)
    ok2 = con[1] == 0x200
    print(f"  con inyección ID 1, HR {HR_BASE}..+1 -> {con}  "
          f"(esperado palabra baja 0x200)  {'OK' if ok2 else 'MAL'}")

    limpiar_estado()
    vuelto = leer(HR_BASE, 2)
    ok3 = vuelto == [0, 0]
    print(f"  tras --clear, HR {HR_BASE}..+1 -> {vuelto}  {'OK' if ok3 else 'MAL'}")

    # inyectar telemetría (ID 16 Rack High Temp -> REPLACE HR 10173 = 30000)
    guardar_estado([16])
    tele = leer(10173, 1)
    ok4 = tele == [30000]
    print(f"  con inyección ID 16 (telemetría), HR 10173 -> {tele}  "
          f"(esperado [30000])  {'OK' if ok4 else 'MAL'}")
    limpiar_estado()

    cli.close()
    todos = ok1 and ok2 and ok3 and ok4
    print("\n=> " + ("PROXY OK ✓ (pasa el dato y aplica/quita la inyección)"
                     if todos else "MAL ✗"))
    return todos


if __name__ == "__main__":
    if "--self-check" in sys.argv:
        ok = _self_check()
        sys.exit(0 if ok else 1)
    run()
