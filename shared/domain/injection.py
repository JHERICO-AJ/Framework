"""
injection.py — the BRAIN of injection: "I want alarm X" -> "which register/bit to force".

Doesn't apply anything by itself: it computes the set of overrides (at the
Modbus register level) that represent the cause of one or more alarms, and a
SCHEDULE over time ("alarm 1 at 10s, alarm 3 at 50s"). That override map is
then applied by the Modbus proxy (or the simulator hook) on the wire that
OmniOps reads, and the oracle confirms it was actually set.

Translation by cause type (`inject` field of the catalog):
  evt1_802_bits  -> TURN ON bit in Evt1_802  (HR 10095, u32)
  evt1_e001_bits -> TURN ON bit in Evt1_E001 (HR 9815,  u32)
  fire_containers-> TURN ON bit (container-1) in FireAlarm (HR 9818)
  pcs_offline    -> TURN OFF bit (pcs-1)      in PcsOnline (HR 9822)
  strings_or_pcs -> Model 803 telemetry: register map MISSING -> not supported yet
  ems / trend    -> the cause isn't in Modbus -> not supported (would be on OmniOps' side)

The u32 values are big-endian (high word first), same as the oracle:
  bit < 16 -> register base+1 (low word), bit
  bit >=16 -> register base   (high word), bit-16

Run the self-check:  python injection.py --self-check
"""

from __future__ import annotations

import json
import os
import sys
import time

from shared.domain import alarm_catalog as cat

# u32 bases by type
_BASE = {
    "evt1_802_bits": cat.ADDR["evt1_802"],   # 10095
    "evt1_e001_bits": cat.ADDR["evt1_e001"],  # 9815
    "fire_containers": cat.ADDR["fire_alarm"],  # 9818
    "pcs_offline": cat.ADDR["pcs_online"],    # 9822
}


def _bit_to_register(base_hr, bit):
    """(16-bit register, mask) for a bit within the big-endian u32."""
    if bit < 16:
        return base_hr + 1, (1 << bit)        # low word
    return base_hr, (1 << (bit - 16))         # high word


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


def overrides_for(rule_ids):
    """Combines the overrides of several alarms into a single register map."""
    ov = Overrides()
    for rid in rule_ids:
        alarm = cat.BY_RULE_ID.get(rid)
        if alarm is None:
            ov.unsupported.append((rid, "not in the catalog"))
            continue
        inj = alarm.get("inject") or {}
        if "evt1_802_bits" in inj:
            for b in inj["evt1_802_bits"]:
                reg, mask = _bit_to_register(_BASE["evt1_802_bits"], b)
                ov._or(reg, mask)
        elif "evt1_e001_bits" in inj:
            for b in inj["evt1_e001_bits"]:
                reg, mask = _bit_to_register(_BASE["evt1_e001_bits"], b)
                ov._or(reg, mask)
        elif "fire_containers" in inj:
            for c in inj["fire_containers"]:
                reg, mask = _bit_to_register(_BASE["fire_containers"], c - 1)
                ov._or(reg, mask)
        elif "pcs_offline" in inj:
            for p in inj["pcs_offline"]:
                reg, mask = _bit_to_register(_BASE["pcs_offline"], p - 1)
                ov._and_clear(reg, mask)      # turn off = PCS down
        elif "strings_or_pcs" in inj:
            from shared.domain.telemetry_map import TELEMETRY
            from shared.utils.parsing import extreme_raw_value
            t = TELEMETRY.get(rid)
            if t is None:
                ov.unsupported.append((rid, "unmapped telemetry (missing 803/103 address)"))
            else:
                ov._replace(t["field"], extreme_raw_value(t["dir"], t["type"]))
        else:
            ov.unsupported.append((rid, "ems/trend: the cause isn't in Modbus"))
    return ov


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


# ---------------------------------------------------------------------------
# Persistence: the CLI writes the state; the proxy (tools/sim_proxy.py) reads it.
# ---------------------------------------------------------------------------
def save_state(rule_ids):
    """Computes the overrides for those alarms and stores them in INJECT_STATE_FILE."""
    ov = overrides_for(rule_ids)
    data = {
        "alarms": sorted(rule_ids),
        "set": {str(r): m for r, m in ov.set.items()},
        "clear": {str(r): m for r, m in ov.clear.items()},
        "replace": {str(r): m for r, m in ov.replace.items()},
        "unsupported": ov.unsupported,
    }
    with open(state_file(), "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2, ensure_ascii=False)
    return ov


def read_state():
    """What the proxy applies: (set {reg:mask}, clear {reg:mask}, replace {reg:value}).
    If there's no file, there's no injection (everything empty)."""
    path = state_file()
    if not os.path.exists(path):
        return {}, {}, {}
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
        set_ = {int(r): int(m) for r, m in data.get("set", {}).items()}
        clear = {int(r): int(m) for r, m in data.get("clear", {}).items()}
        replace = {int(r): int(m) for r, m in data.get("replace", {}).items()}
        return set_, clear, replace
    except Exception:
        return {}, {}, {}


def clear_state():
    """Turns off all injection (deletes the state file)."""
    path = state_file()
    if os.path.exists(path):
        os.remove(path)


def state_file():
    # path of the state file (to the project root, not the cwd)
    try:
        from shared.config.settings import INJECT_STATE_FILE
        return INJECT_STATE_FILE
    except Exception:
        return "inject_state.json"


# ---------------------------------------------------------------------------
def _self_check():
    print("(injection brain test — pure logic, no network)\n")
    ok = True

    def check(desc, got, exp):
        nonlocal ok
        good = got == exp
        ok = ok and good
        print(f"  {desc:46} {'OK' if good else f'FAIL got={got} exp={exp}'}")

    # bit 9 (Cell Overvoltage) -> low word of 10095 = reg 10096, 0x200
    o1 = overrides_for([1])
    check("ID 1 bit 9  -> set{10096:0x200}", o1.set, {10096: 0x200})
    # bit 17 (Cell Voltage diff) -> high word = reg 10095, 0x2
    o6 = overrides_for([6])
    check("ID 6 bit 17 -> set{10095:0x2}", o6.set, {10095: 0x2})
    # e001 bit 0 (PCS Ground Fault) -> reg 9816, 0x1
    o46 = overrides_for([46])
    check("ID 46 e001 bit 0 -> set{9816:0x1}", o46.set, {9816: 0x1})
    # fire container 1 -> bit 0 -> reg 9819, 0x1
    o24 = overrides_for([24])
    check("ID 24 fire cont 1 -> set{9819:0x1}", o24.set, {9819: 0x1})
    # pcs_offline [1] -> turn off bit 0 -> clear{9823:0x1}
    o50 = overrides_for([50])
    check("ID 50 pcs_offline 1 -> clear{9823:0x1}", o50.clear, {9823: 0x1})
    # telemetry now supported: produces a REPLACE (extreme value)
    check("ID 16 telemetry -> replace{10173:30000}", overrides_for([16]).replace, {10173: 30000})
    check("ID 44 ems -> unsupported", len(overrides_for([44]).unsupported), 1)
    # combine 1 and 2 (bits 9 and 11) in the same register
    o12 = overrides_for([1, 2])
    check("ID 1+2 -> set{10096:0xA00}", o12.set, {10096: 0x200 | 0x800})
    # apply on a clean register
    check("apply_to(10096, 0) with bit9", o1.apply_to(10096, 0x0000), 0x200)
    # real clear: PcsOnline 0b111 -> turn off bit0 -> 0b110
    check("apply_to(9823, 0b111) turns off PCS1", o50.apply_to(9823, 0b111), 0b110)

    # schedule over time
    schedule = Schedule().turn_on(10, 1).turn_on(50, 3).turn_off(60, 1)
    check("t=5  -> {}", schedule.active_at(5), set())
    check("t=10 -> {1}", schedule.active_at(10), {1})
    check("t=55 -> {1,3}", schedule.active_at(55), {1, 3})
    check("t=65 -> {3}", schedule.active_at(65), {3})

    print("\n=> " + ("ALL OK ✓" if ok else "DIFFERENCES FOUND ✗"))
    return ok


if __name__ == "__main__":
    if "--self-check" in sys.argv:
        sys.exit(0 if _self_check() else 1)

    args = sys.argv[1:]

    if "--status" in args:
        set_, clear = read_state()
        if not set_ and not clear:
            print("No active injection (the proxy returns the simulator as-is).")
        else:
            print("Injection ACTIVE:")
            for r, m in sorted(set_.items()):
                print(f"  TURN ON  HR {r}: {m:#06x}")
            for r, m in sorted(clear.items()):
                print(f"  TURN OFF HR {r}: {m:#06x}")
        sys.exit(0)

    if "--clear" in args or "--off" in args:
        clear_state()
        print("Injection cleared. The proxy goes back to returning the simulator as-is.")
        sys.exit(0)

    # alarm ids to turn on (e.g.: python -m alarms.inject 1 3)
    ids = [int(x) for x in args if x.isdigit()]
    if not ids:
        print("Usage:\n"
              "  python -m alarms.inject 1 3        # turn on alarms 1 and 3 NOW\n"
              "  python -m alarms.inject 1 --at 10  # turn on alarm 1 at 10s\n"
              "  python -m alarms.inject --status   # see what's injected\n"
              "  python -m alarms.inject --clear    # clear all injection")
        sys.exit(1)

    # --at N : wait N seconds before turning on ("fire at this second")
    wait_s = 0
    if "--at" in args:
        try:
            wait_s = int(args[args.index("--at") + 1])
        except (IndexError, ValueError):
            print("--at needs a number of seconds (e.g.: --at 10)")
            sys.exit(1)

    if wait_s:
        print(f"Turning on {ids} in {wait_s}s… (Ctrl+C to cancel)")
        time.sleep(wait_s)

    ov = save_state(ids)
    names = ", ".join(f"{i}:{cat.BY_RULE_ID[i]['name']}" for i in ids
                       if i in cat.BY_RULE_ID)
    print(f"Injection ACTIVE for [{names}].")
    for reg, mask in sorted(ov.set.items()):
        print(f"  TURN ON  HR {reg}: {mask:#06x}")
    for reg, mask in sorted(ov.clear.items()):
        print(f"  TURN OFF HR {reg}: {mask:#06x}")
    for rid, reason in ov.unsupported:
        print(f"  (unsupported) ID {rid}: {reason}")
    print("\nThe proxy is already applying it. To turn off: python -m alarms.inject --clear")
