"""RecentAlarmRow -- one parsed row of the "Recent Alarms (Last 24h)" card
on Site View. Split into its own file per PR review Correction 2 (one class
per file) -- same pattern already applied to alarms_events/components/
alarm_row.py."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RecentAlarmRow:
    time: str
    device: str
    severity: str
    description: str
