"""AlarmRow — one parsed row of the alarms table (UI-side)."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AlarmRow:
    name: str
    device: str
    severity: str
    status: str
    first: str
    last: str
    subsystem: str
    signal: str

    @property
    def key(self):
        return (self.name, self.device)
