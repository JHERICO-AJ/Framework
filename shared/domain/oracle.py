"""
oracle.py — CAUSE ORACLE for the alarms (prompt 1, the heart of it).

Reads the RAW Modbus of the simulator and, for each alarm in the catalog,
decides whether its CAUSE is actually present — without trusting OmniOps. Uses
the `oracle` and `layer` fields from alarm_catalog.py and the addresses from
the BIT MAP.

What it can confirm per layer:
  bit_802      -> Evt1_802  (HR 10095, u32) bit N
  bit_e001     -> Evt1_E001 (HR 9815,  u32) bit N
  bit_fire     -> FireAlarm (HR 9818) != 0  (smoke in some container)
  bit_pcsonline-> PcsOnline (HR 9822): some PCS with its bit off
  telemetry    -> Model 803: the register map is MISSING -> 'not verifiable (803)'
  ems / trend  -> cause outside Modbus -> 'not verifiable'

The u32 values are assembled big-endian (high word first: hi<<16 | lo), like
SunSpec. Map verification: injecting bit 9 and reading HR 10095 must give
0x200 (512).

READ ONLY. pymodbus is only used when connecting (the self-check runs without it).

Run against the simulator:  python oracle.py
Test the logic without Modbus: python oracle.py --self-check
"""

from __future__ import annotations

import sys

from shared.domain import alarm_catalog as cat
from shared.datasource.modbus_source import signed16, ModbusReader, FakeModbusReader

_OPERATORS = {
    ">":  lambda v, l: v > l,
    ">=": lambda v, l: v >= l,
    "<":  lambda v, l: v < l,
    "<=": lambda v, l: v <= l,
    "==": lambda v, l: v == l,
    "!=": lambda v, l: v != l,
}

# how many PCS we expect "online" (for PcsOnline). Same as the calc layer.
PCS_COUNT = 3

# possible states of the cause
PRESENT = True
ABSENT = False
UNVERIFIABLE = None


def read_u32(reader, hr):
    """Builds the 32-bit integer from 2 consecutive HRs (big-endian)."""
    hi = reader.read_register(hr)
    lo = reader.read_register(hr + 1)
    return (hi << 16) | lo


def cause_of(alarm, reader):
    """Returns (state, reason). state: True/False (verified) or None (not verifiable)."""
    layer = alarm["layer"]
    o = alarm["oracle"]

    if not alarm.get("oracle_independent", True):
        return UNVERIFIABLE, "not verifiable (ems/trend: cause outside Modbus)"

    try:
        if layer in ("bit_802", "bit_e001"):
            # reuse the catalog's own function so we don't diverge
            present = cat.read_bit(lambda hr: read_u32(reader, hr), o["hr"], o["bit"])
            return bool(present), o["sig"]

        if layer == "bit_fire":
            val = read_u32(reader, cat.ADDR["fire_alarm"])
            return bool(val != 0), "FireAlarm (HR 9818) != 0"

        if layer == "bit_pcsonline":
            val = read_u32(reader, cat.ADDR["pcs_online"])
            all_online = (1 << PCS_COUNT) - 1          # e.g. 0b111 with 3 PCS
            any_down = (val & all_online) != all_online
            return bool(any_down), f"PcsOnline (HR 9822): some PCS down (mask={val & all_online:#b})"

        if layer == "telemetry":
            from shared.domain.telemetry_map import TELEMETRY
            t = TELEMETRY.get(alarm["alarm_rule_id"])
            if not t:
                return UNVERIFIABLE, "unmapped telemetry (missing Model 803 address)"
            raw = reader.read_register(t["field"])
            if t["type"] == "int16":
                raw = signed16(raw)
            sf = signed16(reader.read_register(t["sf"]))
            value = raw * (10 ** sf)
            op = _OPERATORS[t["op"]]
            approx = " (approx)" if t.get("approx") else ""
            return bool(op(value, t["limit"])), (
                f"{value:.2f} {t['op']} {t['limit']}{approx}")

        return UNVERIFIABLE, f"unknown layer: {layer}"
    except Exception as e:
        return UNVERIFIABLE, f"couldn't read the raw data: {e}"


def evaluate(reader, catalog=None):
    """Runs the oracle over the whole catalog.
    Returns (dict rule_id -> (state, reason), set of rule_ids with cause present)."""
    catalog = catalog or cat.ALARMS
    causes = {}
    present = set()
    for alarm in catalog:
        state, reason = cause_of(alarm, reader)
        causes[alarm["alarm_rule_id"]] = (state, reason)
        if state is PRESENT:
            present.add(alarm["alarm_rule_id"])
    return causes, present


# ---------------------------------------------------------------------------
def _self_check():
    print("(oracle test — FAKE reader, no Modbus)\n")
    # Evt1_802 (10095/10096): bit 9 (0x200, in the low word) and bit 17 (in the high one)
    #   u32 = 0x00020200 -> hi=0x0002=2, lo=0x0200=512
    # Evt1_E001 (9815/9816): bit 0 (0x1) -> hi=0, lo=1
    # FireAlarm (9818/9819): != 0 -> hi=0, lo=1
    # PcsOnline (9822/9823): 0b111=7 -> all online (no cause)
    reader = FakeModbusReader({
        10095: 0x0002, 10096: 0x0200,
        9815: 0x0000, 9816: 0x0001,
        9818: 0x0000, 9819: 0x0001,
        9822: 0x0000, 9823: 0b111,
        # telemetry: ID 16 Rack High Temp (StrModTmpMax 10173, SF 10156)
        10173: 30000, 10156: 0,          # 30000 * 10^0 = 30000 °C  > 58 -> YES
    })

    expected = {
        1:  PRESENT,       # bit 9  -> present
        2:  ABSENT,        # bit 11 -> absent
        6:  PRESENT,       # bit 17 -> present (high word)
        46: PRESENT,       # e001 bit 0 -> present
        38: ABSENT,        # e001 bit 1 -> absent
        24: PRESENT,       # fire != 0 -> present
        50: ABSENT,        # pcsonline: all online -> absent
        16: PRESENT,       # telemetry: 30000°C > 58 -> present
        44: UNVERIFIABLE,  # ems -> not verifiable
    }

    causes, present = evaluate(reader)
    all_ok = True
    for rid, exp in expected.items():
        got, reason = causes[rid]
        ok = got is exp if exp is None else got == exp
        all_ok = all_ok and ok
        name = cat.BY_RULE_ID[rid]["name"]
        et = {True: "YES", False: "no", None: "n/v"}[got]
        print(f"  ID {rid:2} {name:26} cause={et:3} {'OK' if ok else f'FAIL (exp {exp})'}")

    # PcsOnline with one PCS down: bit 0 off -> 0b110
    reader2 = FakeModbusReader({9822: 0, 9823: 0b110})
    got50, _ = cause_of(cat.BY_RULE_ID[50], reader2)
    ok50 = got50 is PRESENT
    all_ok = all_ok and ok50
    print(f"  ID 50 PcsOnline with 1 PCS down       cause={'YES' if got50 else 'no'} "
          f"{'OK' if ok50 else 'FAIL'}")

    print(f"\n  causes present: {sorted(present)}")
    print("=> " + ("ALL OK ✓" if all_ok else "DIFFERENCES FOUND ✗"))
    return all_ok


if __name__ == "__main__":
    if "--self-check" in sys.argv:
        sys.exit(0 if _self_check() else 1)

    # against the real simulator
    try:
        reader = ModbusReader()
    except Exception as e:
        print("Couldn't connect to the simulator:", e)
        sys.exit(1)
    try:
        causes, present = evaluate(reader)
    finally:
        reader.close()

    print("Cause per alarm (read from raw data):\n")
    for alarm in cat.ALARMS:
        state, reason = causes[alarm["alarm_rule_id"]]
        et = {True: "YES", False: "no ", None: "n/v"}[state]
        print(f"  ID {alarm['alarm_rule_id']:2} {alarm['name']:34} cause:{et}  ({reason})")
    print(f"\nCauses present now: {sorted(present) or '(none — simulator healthy)'}")
