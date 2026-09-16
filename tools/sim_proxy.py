"""
sim_proxy.py — Modbus PROXY that sits between the edge and the real simulator,
so alarms can be INJECTED without touching any other repo.

     edge  ──►  proxy (5020)  ──►  REAL simulator (5021)  ──►  OmniOps

On every read, the proxy fetches the FRESH data from the real simulator and, if
something is injected (left by `alarms/inject.py` in INJECT_STATE_FILE),
overwrites those registers before returning them. The edge (and therefore
OmniOps) receives the condition as if it came from the simulator. When there's
no injection, it's invisible.

HOW TO USE IT (locally, from the project ROOT):
  1) REAL simulator on 5021 (move the port in your usual command):
       python <path>\\simulator\\bess_modbus_simulator.py 127.0.0.1 5021 5
  2) Proxy on 5020:
       python -m tools.sim_proxy
  3) The edge and OmniOps start as usual (they keep reading 5020 = the proxy).
  4) Trigger an alarm whenever you want, from another terminal:
       python -m alarms.inject 24          # turns on "Rack Smoke Detected"
       python -m alarms.inject 1 --at 10   # turns on Cell Overvoltage at 10s
       python -m alarms.inject --clear     # clears the injection

Test the proxy without the real simulator (loopback):  python -m tools.sim_proxy --self-check
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
from shared.domain.injection import read_state


class _UpstreamReader:
    """Client toward the real simulator, with reconnection. Reads fresh registers."""

    def __init__(self, host, port, unit):
        self.host, self.port, self.unit = host, port, unit
        self._c = None

    def _client(self):
        if self._c is None:
            self._c = ModbusTcpClient(self.host, port=self.port)
        if not getattr(self._c, "connected", False):
            self._c.connect()
        return self._c

    def read(self, address, count):
        c = self._client()
        try:
            rr = c.read_holding_registers(address, count=count, device_id=self.unit)
        except TypeError:
            rr = c.read_holding_registers(address, count=count, slave=self.unit)
        if rr.isError():
            raise IOError(f"upstream error reading {address}..{address+count-1}")
        return list(rr.registers)


class ProxyBlock(BaseModbusDataBlock):
    """Holding registers block that, instead of storing data, fetches it from
    the real simulator on every request and applies the injection."""

    def __init__(self, upstream):
        self.upstream = upstream
        self.address = 0
        self.values = {}
        self.default_value = 0

    def validate(self, address, count=1):
        return True                     # accept any address; the real one validates

    def getValues(self, address, count=1):
        regs = self.upstream.read(address, count)
        set_, clear, replace = read_state()   # FRESH injection state on every read
        if set_ or clear or replace:
            out = []
            for i, v in enumerate(regs):
                reg = address + i
                if reg in replace:
                    v = replace[reg]                       # REPLACE (telemetry) wins
                else:
                    v = (v | set_.get(reg, 0)) & ~clear.get(reg, 0)
                out.append(v & 0xFFFF)
            return out
        return regs

    def setValues(self, address, values):
        pass                            # read-only proxy

    def reset(self):
        pass


def _make_context():
    upstream = _UpstreamReader(SIM_REAL_HOST, SIM_REAL_PORT, SIM_UNIT)
    block = ProxyBlock(upstream)
    # zero_mode=True -> addresses pass through AS-IS (the proxy asks the real
    # sim for the same address the edge asked for).
    slave = ModbusSlaveContext(hr=block, ir=block, zero_mode=True)
    return ModbusServerContext(slaves=slave, single=True)


def run():
    print(f"Modbus proxy listening on {SIM_HOST}:{SIM_PORT}  ->  "
          f"real simulator at {SIM_REAL_HOST}:{SIM_REAL_PORT}")
    print("Inject with:  python -m alarms.inject <id>   (clear: --clear)\n")
    StartTcpServer(context=_make_context(), address=(SIM_HOST, SIM_PORT))


# ---------------------------------------------------------------------------
def _self_check():
    """Real loopback: starts a fake 'sim', the proxy in front of it, and reads
    through the proxy — with and without injection."""
    from pymodbus.datastore import ModbusSequentialDataBlock
    from shared.domain.injection import save_state, clear_state

    print("(loopback: fake sim 5599 -> proxy 5598 -> client)\n")
    HR_BASE, PROXY_P, REAL_P = 10095, 5598, 5599

    # fake sim: registers 10095.. with zeros (large block)
    real_block = ModbusSequentialDataBlock(0, [0] * 20000)
    ctx_real = ModbusServerContext(
        slaves=ModbusSlaveContext(hr=real_block, ir=real_block, zero_mode=True),
        single=True)
    threading.Thread(target=StartTcpServer,
                     kwargs={"context": ctx_real, "address": ("127.0.0.1", REAL_P)},
                     daemon=True).start()

    # proxy pointing at the fake sim
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

    def read(addr, count):
        try:
            rr = cli.read_holding_registers(addr, count=count, device_id=1)
        except TypeError:
            rr = cli.read_holding_registers(addr, count=count, slave=1)
        return list(rr.registers)

    clear_state()
    without = read(HR_BASE, 2)
    ok1 = without == [0, 0]
    print(f"  no injection, HR {HR_BASE}..+1 -> {without}  {'OK' if ok1 else 'FAIL'}")

    # inject Cell Overvoltage (ID 1 = bit 9 -> HR 10096 = 0x200)
    save_state([1])
    with_ = read(HR_BASE, 2)
    ok2 = with_[1] == 0x200
    print(f"  with injection ID 1, HR {HR_BASE}..+1 -> {with_}  "
          f"(expected low word 0x200)  {'OK' if ok2 else 'FAIL'}")

    clear_state()
    reverted = read(HR_BASE, 2)
    ok3 = reverted == [0, 0]
    print(f"  after --clear, HR {HR_BASE}..+1 -> {reverted}  {'OK' if ok3 else 'FAIL'}")

    # inject telemetry (ID 16 Rack High Temp -> REPLACE HR 10173 = 30000)
    save_state([16])
    tele = read(10173, 1)
    ok4 = tele == [30000]
    print(f"  with injection ID 16 (telemetry), HR 10173 -> {tele}  "
          f"(expected [30000])  {'OK' if ok4 else 'FAIL'}")
    clear_state()

    cli.close()
    all_ok = ok1 and ok2 and ok3 and ok4
    print("\n=> " + ("PROXY OK ✓ (passes the data and applies/removes the injection)"
                     if all_ok else "FAIL ✗"))
    return all_ok


if __name__ == "__main__":
    if "--self-check" in sys.argv:
        ok = _self_check()
        sys.exit(0 if ok else 1)
    run()
