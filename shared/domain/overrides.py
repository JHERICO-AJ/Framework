"""Overrides -- the register overrides (set/clear/replace) to inject."""

from __future__ import annotations


class Overrides:
    """What to do to each register: OR (turn on), CLEAR (turn off), REPLACE (set value)."""

    def __init__(self):
        self.set = {}      # {reg16: mask to turn on}
        self.clear = {}    # {reg16: mask to turn off}
        self.replace = {}  # {reg16: value to set} (telemetry)
        self.unsupported = []  # [(rule_id, reason)]

    def _or(self, reg, mask):
        self.set[reg] = self.set.get(reg, 0) | mask

    def _and_clear(self, reg, mask):
        self.clear[reg] = self.clear.get(reg, 0) | mask

    def _replace(self, reg, value):
        self.replace[reg] = value & 0xFFFF

    def apply_to(self, reg, value):
        """What the value of `reg` would become after the overrides (used by the proxy)."""
        if reg in self.replace:
            return self.replace[reg] & 0xFFFF        # REPLACE wins
        value = (value | self.set.get(reg, 0)) & ~self.clear.get(reg, 0)
        return value & 0xFFFF

    def touched_registers(self):
        return sorted(set(self.set) | set(self.clear) | set(self.replace))
