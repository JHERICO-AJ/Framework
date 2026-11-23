"""FractalUpstreamReader -- client toward the real simulator, with reconnection."""

from __future__ import annotations

from pymodbus.client import ModbusTcpClient


class FractalUpstreamReader:
    """Client toward the real Fractal simulator, with reconnection."""

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
