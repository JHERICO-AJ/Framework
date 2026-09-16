"""
modbus_source.py — the ONLY read source for the simulator (Modbus).

Before, the Modbus read lived in compare_pcs_power.py and was REIMPLEMENTED in
oracle.py. Now it lives here and everyone uses it. This is also the "source
reader" that the migration wanted to separate out, so another simulator can be
plugged in (e.g. Fractal) by changing only this file.

Contains:
  signed16 / w_to_kw       -> conversions of raw values
  read_sim_total_kw()      -> sum of the power of the 3 PCS (calc layer)
  ModbusReader             -> reads individual registers (for the alarm oracle)
  FakeModbusReader         -> fake reader for offline tests

READ ONLY. pymodbus is only imported when connecting (so the logic can be
tested without having it installed).

Run the self-check:  python modbus_source.py --self-check
"""

from __future__ import annotations

import sys

from shared.config.settings import SIM_HOST, SIM_PORT, SIM_UNIT, PCS_W_REGS


def signed16(raw):
    return raw - 65536 if raw > 32767 else raw


def w_to_kw(raw, sf):
    """power of a PCS in kW = signed_raw * 10^sf / 1000 (W -> kW)."""
    return signed16(raw) * (10 ** signed16(sf)) / 1000.0


def _read(client, addr, count):
    # newer pymodbus uses device_id=; the old one uses slave=
    try:
        return client.read_holding_registers(addr, count=count, device_id=SIM_UNIT)
    except TypeError:
        return client.read_holding_registers(addr, count=count, slave=SIM_UNIT)


# --- persistent connection (optimization) -----------------------------------
# Before, the WHOLE Modbus connection was opened and closed on every read (once
# per second). Now it's opened ONCE and reused; if the socket drops, it
# reconnects on its own and retries. This lowers the latency of each cycle and
# holds up over long runs.
_client = None


def _get_client():
    global _client
    from pymodbus.client import ModbusTcpClient
    if _client is None:
        _client = ModbusTcpClient(SIM_HOST, port=SIM_PORT)
    if not getattr(_client, "connected", False):
        if not _client.connect():
            raise ConnectionError(
                f"couldn't connect to the simulator at {SIM_HOST}:{SIM_PORT} "
                "(is the simulator running?)")
    return _client


def _reconnect():
    global _client
    try:
        if _client is not None:
            _client.close()
    except Exception:
        pass
    _client = None
    return _get_client()


def _read_with_retry(addr, count):
    """Reads registers with the persistent connection; if it fails, reconnects and retries once."""
    try:
        rr = _read(_get_client(), addr, count)
        if rr.isError():
            raise IOError(f"error reading register {addr}")
        return rr.registers
    except Exception:
        rr = _read(_reconnect(), addr, count)
        if rr.isError():
            raise IOError(f"error reading register {addr}")
        return rr.registers


def close_sim():
    """Closes the persistent connection (optional, when the monitor ends)."""
    global _client
    try:
        if _client is not None:
            _client.close()
    finally:
        _client = None


def read_sim_total_kw():
    """Sums the power of the 3 PCS by reading the simulator over Modbus.
    Reuses the persistent connection. Returns (total_kw, [(register, kw), ...])."""
    total = 0.0
    details = []
    for w_addr, sf_addr in PCS_W_REGS:
        raw = _read_with_retry(w_addr, 2)[0]
        sf = _read_with_retry(sf_addr, 1)[0]
        kw = w_to_kw(raw, sf)
        total += kw
        details.append((w_addr, kw))
    return total, details


# --- individual register readers (for the alarm oracle) --------------------
class ModbusReader:
    """Reads the real simulator over Modbus, register by register."""

    def __init__(self, host=SIM_HOST, port=SIM_PORT, unit=SIM_UNIT):
        from pymodbus.client import ModbusTcpClient
        self._client = ModbusTcpClient(host, port=port)
        self._unit = unit
        if not self._client.connect():
            raise ConnectionError(
                f"couldn't connect to the simulator at {host}:{port} "
                "(is the simulator running?)")

    def read_register(self, addr):
        try:
            rr = self._client.read_holding_registers(addr, count=1, device_id=self._unit)
        except TypeError:
            rr = self._client.read_holding_registers(addr, count=1, slave=self._unit)
        if rr.isError():
            raise IOError(f"error reading register {addr}")
        return rr.registers[0]

    def close(self):
        try:
            self._client.close()
        except Exception:
            pass


class FakeModbusReader:
    """For tests: a dict {address: raw_16bit_value}."""

    def __init__(self, registers):
        self._r = dict(registers)

    def read_register(self, addr):
        if addr not in self._r:
            raise IOError(f"register {addr} is not in the fake reader")
        return self._r[addr]

    def close(self):
        pass


# ---------------------------------------------------------------------------
SAMPLE_SIM = [(17014, 14218, 2), (17114, 14176, 2), (17214, 7100, 2)]


def _self_check():
    print("(modbus_source test — conversion + fake reader, no network)\n")
    details = [(a, w_to_kw(raw, sf)) for a, raw, sf in SAMPLE_SIM]
    total = sum(kw for _, kw in details)
    for a, kw in details:
        print(f"  reg {a}: {kw:9.1f} kW")
    print(f"  TOTAL: {total:.1f} kW")
    ok1 = signed16(65535) == -1 and signed16(1) == 1
    fr = FakeModbusReader({100: 0b1000, 101: 5})
    ok2 = fr.read_register(100) == 8 and fr.read_register(101) == 5
    print(f"\n  signed16 -> {'OK' if ok1 else 'FAIL'}")
    print(f"  FakeModbusReader -> {'OK' if ok2 else 'FAIL'}")
    print("=> " + ("OK ✓" if ok1 and ok2 else "FAIL ✗"))
    return ok1 and ok2


if __name__ == "__main__":
    sys.exit(0 if _self_check() else 1)
