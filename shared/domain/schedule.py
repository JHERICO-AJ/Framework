"""Schedule -- a timed sequence of alarm turn-on/turn-off steps."""

from __future__ import annotations

from shared.domain.injection import overrides_for


class Schedule:
    """Timeline: at second t, turn certain alarms on/off.
    Alarms stay active until a later event turns them off (consistent with
    OmniOps not closing alarms)."""

    def __init__(self):
        self.events = []      # [(t, 'on'|'off', rule_id)]

    def turn_on(self, second, *rule_ids):
        for rule_id in rule_ids:
            self.events.append((second, "on", rule_id))
        return self

    def turn_off(self, second, *rule_ids):
        for rule_id in rule_ids:
            self.events.append((second, "off", rule_id))
        return self

    def active_at(self, second):
        """Set of alarms active at that instant, based on events up to then."""
        active = set()
        for event_second, action, rule_id in sorted(self.events, key=lambda e: e[0]):
            if event_second > second:
                break
            active.add(rule_id) if action == "on" else active.discard(rule_id)
        return active

    def overrides_at(self, second):
        return overrides_for(self.active_at(second))
