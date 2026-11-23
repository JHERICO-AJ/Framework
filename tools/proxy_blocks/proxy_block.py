"""ProxyBlock -- holding registers block that serves the real data with the injection applied."""

from __future__ import annotations

from pymodbus.datastore.store import BaseModbusDataBlock
from shared.domain.injection import read_state


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
