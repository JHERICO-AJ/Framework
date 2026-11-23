"""FakeModbusReader -- fake Modbus reader for offline tests."""

from __future__ import annotations


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
