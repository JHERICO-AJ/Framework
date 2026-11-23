"""FractalProxyBlock -- holding registers block that serves the real data with the injection applied."""

from __future__ import annotations

from pymodbus.datastore.store import BaseModbusDataBlock
from shared.domain.fractal_register_injection import read_state


class FractalProxyBlock(BaseModbusDataBlock):
    """Holding registers block that fetches data from the real Fractal
    simulator on every request and applies that SITE's injection."""

    def __init__(self, upstream, site_name):
        self.upstream = upstream
        self.site_name = site_name
        self.address = 0
        self.values = {}
        self.default_value = 0

    def validate(self, address, count=1):
        return True

    def getValues(self, address, count=1):
        regs = self.upstream.read(address, count)
        set_, clear, replace = read_state(self.site_name)   # FRESH on every read
        if set_ or clear or replace:
            out = []
            for i, v in enumerate(regs):
                reg = address + i
                if reg in replace:
                    v = replace[reg]
                else:
                    v = (v | set_.get(reg, 0)) & ~clear.get(reg, 0)
                out.append(v & 0xFFFF)
            return out
        return regs

    def setValues(self, address, values):
        pass

    def reset(self):
        pass
