"""Overrides -- the Fractal register overrides (set/clear/replace) to inject."""

from __future__ import annotations


class Overrides:
    """What to do to each register: OR (turn bits on), REPLACE (analog
    value). No CLEAR today -- no Fractal alarm in the catalog needs turning
    a bit off (unlike EPC's pcs_offline)."""

    def __init__(self):
        self.set = {}       # {reg16: mask to OR in}
        self.clear = {}     # {reg16: mask to AND-NOT} (unused today, kept for parity)
        self.replace = {}   # {reg16: value to REPLACE} (analog telemetry)
        self.unsupported = []   # [(rule_id, reason)]

    def _or(self, reg, mask):
        self.set[reg] = self.set.get(reg, 0) | mask

    def _replace(self, reg, value):
        self.replace[reg] = value & 0xFFFF

    def apply_to(self, reg, value):
        """What the value of `reg` would become after the overrides (used by
        the proxy)."""
        if reg in self.replace:
            return self.replace[reg] & 0xFFFF
        value = (value | self.set.get(reg, 0)) & ~self.clear.get(reg, 0)
        return value & 0xFFFF

    def touched_registers(self):
        return sorted(set(self.set) | set(self.clear) | set(self.replace))
