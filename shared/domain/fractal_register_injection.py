"""
fractal_register_injection.py — the BRAIN of Fractal alarm injection at the
Modbus register level: "I want alarm X active on site S" -> "which
register/bit on S's own PCS/EMU layout to force". Same role as
shared/domain/injection.py (EPC), but for Fractal's register map instead of
EPC's, and PER SITE (each of the 5 BOLIVIA sites is its own Modbus TCP
instance -- shared/config/settings.FRACTAL_SITE_MODBUS).

REPLACES the earlier plan (shared/domain/fractal_injection.py, generating a
`.faults.yaml` for the REAL simulator process to hot-reload): confirmed
2026-09-17 that mechanism needs code added inside omniops-bess-edge itself
(the internal QA note 'INYECCION_ALARMAS_FRACTAL' documents a teammate's own, never-pushed
local branch that adds it) -- not something this framework can drive purely
by writing a file. This module instead computes overrides at the Modbus
WIRE level, applied by tools/fractal_sim_proxy.py sitting between the real
simulator and OmniOps/edge -- exactly the already-proven EPC pattern
(tools/sim_proxy.py + shared/domain/injection.py), so it needs ZERO changes
to omniops-bess-edge, ever.

Field offsets/scales below are COPIED from omniops-bess-edge's
modbus_common/fractal_addressing_map.py (PCS_COMMON_FIELDS / EMU_FIELDS),
confirmed against that file directly 2026-09-17 -- same convention already
used by shared/datasource/fractal_modbus_source.py (its own docstring:
"confirmed against that file directly, not guessed"), kept self-contained
in this repo rather than cross-imported so this framework doesn't depend on
omniops-bess-edge's internal module layout staying stable.

PCS_BASES=(5000, 5300, 5600) is the same across all 5 BOLIVIA
sites/fractal-BOLIVIA*.local.yaml files today (confirmed by direct read) --
if a future site ever uses a different register_map.pcs list, this module
would need a per-site override, same limitation fractal_modbus_source.py
already has.

Run the self-check:  python -m shared.domain.fractal_register_injection --self-check
"""
from __future__ import annotations

import json
import os
import sys

from shared.config.settings import FRACTAL_INJECT_STATE_DIR
from shared.domain.fractal_overrides import Overrides
from shared.domain.fractal_alarm_catalog import BY_RULE_ID

# ---------------------------------------------------------------------------
# Register map (base + offset), copied from omniops-bess-edge's
# modbus_common/fractal_addressing_map.py -- PCS_COMMON_FIELDS / EMU_FIELDS.
# ---------------------------------------------------------------------------
PCS_BASES = (5000, 5300, 5600)   # 1-based pcs_index -> PCS_BASES[pcs_index - 1]

# name -> (offset within a PCS instance, bit width, scale)
PCS_ANALOG_FIELDS = {
    "vac_ab": (0, 16, 0.1), "vac_bc": (1, 16, 0.1), "vac_ca": (2, 16, 0.1),
    "iac_a": (5, 16, 0.1), "iac_b": (6, 16, 0.1), "iac_c": (7, 16, 0.1),
    "p_ac_kw": (8, 32, 0.1), "q_ac_kvar": (10, 32, 0.1),
    "vdc": (15, 16, 0.1),
    "temp_igbt_c": (19, 16, 0.1), "temp_cabinet_c": (20, 16, 0.1),
}
PCS_STATUS_WORD_1_OFFSET = 250    # status_word_N -> offset + (N-1)
PCS_ALARM_WORD_1_OFFSET = 260     # alarm_word_N  -> offset + (N-1)

EMU_BASE = 100
EMU_STATUS_WORD_1_OFFSET = 118
EMU_ALARM_WORD_1_OFFSET = 128


def _word_addr(word_name, base, status_word_offset, alarm_word_offset):
    """'status_word_3' / 'alarm_word_27' -> absolute register address."""
    prefix, _, n = word_name.rpartition("_")
    n = int(n)
    if prefix == "status_word":
        return base + status_word_offset + (n - 1)
    if prefix == "alarm_word":
        return base + alarm_word_offset + (n - 1)
    raise ValueError(f"unrecognized word field name: {word_name!r}")


def _encode16(value, scale):
    """Real engineering value -> raw uint16 (two's complement for negatives)."""
    return round(value / scale) & 0xFFFF


def _encode32(value, scale):
    """Real engineering value -> (hi, lo) uint16 pair, big-endian (matches
    fractal_modbus_source.py's _combine32/_as_signed32 decode convention)."""
    raw = round(value / scale) & 0xFFFFFFFF
    return (raw >> 16) & 0xFFFF, raw & 0xFFFF


BASELINE_VDC_V = 750.0   # inside the healthy 600-900V band (600<vdc<900 avoids both #38 and #39)


def _apply_baseline(ov):
    """Forces the simulator's own PERMANENTLY-broken default conditions back
    into a healthy range, so a test can assert '0 alarms at rest' the way
    the internal QA note 'Plan_Integral_Fractal''s acceptance criteria assume. Without
    this, a freshly-started Fractal simulator already sits with 4 alarms
    open by itself (confirmed live 2026-09-17 via Alarms & Events on
    BOLIVIA 4, matching the known gotchas in
    the internal QA note 'INYECCION_ALARMAS_FRACTAL'):
      - vdc is fixed at 1200V constant in the sim's physics (never
        recalculated) -> always > the 900V #38 threshold on all 3 PCS.
      - the EMU always reports every status_word/alarm_word as 0 (no
        connectivity model yet) -> the "connected" bit #52/#53 need is
        never set on its own, for any PCS or the meter.
    This does NOT touch anything the catalog's own `inject`/`inject_alt`
    entries would set for a REAL alarm under test -- overrides_for() applies
    baseline FIRST, then the requested alarm(s) on top, so e.g. injecting
    #39 (needs vdc<600V) still wins over this baseline's 750V."""
    for pcs_index in (1, 2, 3):
        base = PCS_BASES[pcs_index - 1]
        ov._replace(base + PCS_ANALOG_FIELDS["vdc"][0], _encode16(BASELINE_VDC_V, PCS_ANALOG_FIELDS["vdc"][2]))
    # EMU status_word_3 bit0/1/2 = PCS1/2/3 RS485 "Connected" -> suppresses #52
    ov._or(_word_addr("status_word_3", EMU_BASE, EMU_STATUS_WORD_1_OFFSET, EMU_ALARM_WORD_1_OFFSET), 0b111)
    # EMU status_word_7 bit0 = Meter RS485 "Connected" -> suppresses #53
    ov._or(_word_addr("status_word_7", EMU_BASE, EMU_STATUS_WORD_1_OFFSET, EMU_ALARM_WORD_1_OFFSET), 0b1)


def overrides_for(rule_ids, use_alt=None, baseline=False, pcs_override=None):
    """Combines the register-level overrides of several Fractal alarm IDs
    into a single map. Mirrors shared/domain/injection.py::overrides_for,
    but for Fractal's per-PCS/EMU word+analog layout instead of EPC's u32s.

    `use_alt`: set of rule_ids that should use their `inject_alt` variant
    (e.g. alarm #70's confirmed-broken EMU-side path).
    `baseline`: also force the simulator's own default-broken conditions
    (see _apply_baseline's docstring) back to healthy, so the site reads as
    "0 alarms at rest" plus exactly whatever's in rule_ids -- use this for
    E2E-F09/F10-style single-alarm scenarios; leave it off (default) for
    F11-style multi-site isolation checks, where a delta-based assertion
    (alarm count before/after, not an absolute 0) is the right comparison.
    `pcs_override`: {rule_id: pcs_index} to force a rule onto a DIFFERENT
    PCS instance than the catalog's own default (1-based). Needed in
    practice: confirmed live 2026-09-18 that once a (site, PCS, rule)
    combination has fired once, OmniOps caches it as "already open" and
    won't re-raise it even after a DB cleanup + fresh simulator/edge restart
    (a backend-side gotcha, not a bug in this module -- see
    the internal QA note 'FRACTAL_ALARM_INJECTION_SETUP''s "GOTCHA CRITICO" section). Using
    a PCS that has never fired that rule on that site sidesteps it."""
    use_alt = use_alt or set()
    pcs_override = pcs_override or {}
    ov = Overrides()
    if baseline:
        _apply_baseline(ov)

    for rid in rule_ids:
        alarm = BY_RULE_ID.get(rid)
        if alarm is None:
            ov.unsupported.append((rid, "not in the Fractal catalog"))
            continue

        variant_key = "inject_alt" if rid in use_alt else "inject"
        inject = alarm.get(variant_key)
        if not inject:
            ov.unsupported.append((rid, f"no {variant_key!r} variant defined"))
            continue

        pcs_index = pcs_override.get(rid, alarm["pcs_index"])

        if "analog" in inject:
            if pcs_index is None:
                ov.unsupported.append((rid, "'analog' override needs a pcs_index"))
            else:
                base = PCS_BASES[pcs_index - 1]
                for field, value in inject["analog"].items():
                    if field not in PCS_ANALOG_FIELDS:
                        ov.unsupported.append((rid, f"unmapped analog field {field!r}"))
                        continue
                    offset, width, scale = PCS_ANALOG_FIELDS[field]
                    addr = base + offset
                    if width == 16:
                        ov._replace(addr, _encode16(value, scale))
                    else:
                        hi, lo = _encode32(value, scale)
                        ov._replace(addr, hi)
                        ov._replace(addr + 1, lo)

        if "bits" in inject:
            if pcs_index is None:
                ov.unsupported.append((rid, "'bits' override needs a pcs_index"))
            else:
                base = PCS_BASES[pcs_index - 1]
                for word, bits in inject["bits"].items():
                    addr = _word_addr(word, base, PCS_STATUS_WORD_1_OFFSET, PCS_ALARM_WORD_1_OFFSET)
                    mask = 0
                    for b in bits:
                        mask |= (1 << b)
                    ov._or(addr, mask)

        if "emu_bits" in inject:
            for word, bits in inject["emu_bits"].items():
                addr = _word_addr(word, EMU_BASE, EMU_STATUS_WORD_1_OFFSET, EMU_ALARM_WORD_1_OFFSET)
                mask = 0
                for b in bits:
                    mask |= (1 << b)
                ov._or(addr, mask)

        if "meter_total_active_power_kw_factor" in inject:
            ov.unsupported.append(
                (rid, "meter mismatch: no register override needed -- the "
                      "simulator's own transformer loss already exceeds "
                      "tolerance; see the catalog note for the real (time) "
                      "blocker (MeterMismatchWindowDays)"))

    return ov


# ---------------------------------------------------------------------------
# Persistence: ONE state file PER SITE (the CLI/tests write it; the proxy
# instance running for that site reads it on every Modbus read).
# ---------------------------------------------------------------------------
def state_file_for(site_name):
    os.makedirs(FRACTAL_INJECT_STATE_DIR, exist_ok=True)
    safe_name = site_name.replace(" ", "_")
    return os.path.join(FRACTAL_INJECT_STATE_DIR, f"{safe_name}.json")


def save_state(site_name, rule_ids, use_alt=None, baseline=False, pcs_override=None):
    """Computes the overrides for those alarms and stores them for that
    site's proxy to pick up on its next read. `baseline`: see
    overrides_for's docstring -- forces the sim's own default-broken
    conditions (vdc, EMU connectivity) back to healthy first. `pcs_override`:
    see overrides_for's docstring -- sidesteps the backend's per-(site, PCS,
    rule) alarm cache."""
    ov = overrides_for(rule_ids, use_alt=use_alt, baseline=baseline, pcs_override=pcs_override)
    data = {
        "alarms": sorted(rule_ids),
        "set": {str(r): m for r, m in ov.set.items()},
        "clear": {str(r): m for r, m in ov.clear.items()},
        "replace": {str(r): m for r, m in ov.replace.items()},
        "unsupported": ov.unsupported,
    }
    with open(state_file_for(site_name), "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2, ensure_ascii=False)
    return ov


def read_state(site_name):
    """What the proxy applies for that site: (set, clear, replace). No file
    -> no injection (everything empty)."""
    path = state_file_for(site_name)
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


def clear_state(site_name):
    """Turns off all injection for that site (deletes its state file)."""
    path = state_file_for(site_name)
    if os.path.exists(path):
        os.remove(path)


# ---------------------------------------------------------------------------
def _self_check():
    print("(fractal register injection brain test — pure logic, no network)\n")
    ok = True

    def check(desc, got, exp):
        nonlocal ok
        good = got == exp
        ok = ok and good
        print(f"  {desc:52} {'OK' if good else f'FAIL got={got!r} exp={exp!r}'}")

    # alarm 46: Ground Fault, pcs_index=1, bits alarm_word_4:[4]
    # addr = PCS_BASES[0](5000) + PCS_ALARM_WORD_1_OFFSET(260) + (4-1) = 5263
    o46 = overrides_for([46])
    check("alarm 46 -> set{5263: 0x10}", o46.set, {5263: 0b10000})

    # alarm 38: DC Bus Overvoltage, pcs_index=1, analog vdc=950 (scale 0.1)
    # addr = 5000 + 15 = 5015, raw = 950/0.1 = 9500 = 0x251C
    o38 = overrides_for([38])
    check("alarm 38 -> replace{5015: 9500}", o38.replace, {5015: 9500})

    # alarm 78 (corrected 2026-09-17): p_ac_kw=8 (INT32, scale 0.1) + bits
    # status_word_1:[5], pcs_index=1
    # p_ac_kw addr = 5000+8=5008/5009, raw=8/0.1=80 -> hi=0, lo=80
    # status_word_1 addr = 5000+250+0=5250, mask=1<<5=32
    o78 = overrides_for([78])
    check("alarm 78 analog -> replace{5008:0, 5009:80}",
          {5008: o78.replace.get(5008), 5009: o78.replace.get(5009)}, {5008: 0, 5009: 80})
    check("alarm 78 bits -> set{5250: 0x20}", o78.set, {5250: 0b100000})

    # alarm 52: EMS-PCS Comm Lost, EMU-level, emu_bits status_word_3:[0,1,2]
    # addr = 100 + 118 + (3-1) = 220, mask = 0b111
    o52 = overrides_for([52])
    check("alarm 52 -> set{220: 0b111} (EMU-level)", o52.set, {220: 0b111})

    # alarm 70's inject_alt: emu_bits alarm_word_1:[5]
    # addr = 100 + 128 + 0 = 228, mask = 1<<5 = 32
    o70 = overrides_for([70], use_alt={70})
    check("alarm 70 inject_alt -> set{228: 0x20} (EMU alarm_word_1)", o70.set, {228: 0b100000})
    # and the DEFAULT (non-alt) path must NOT touch that register
    o70_default = overrides_for([70])
    check("alarm 70 default does NOT touch EMU alarm_word_1", 228 in o70_default.set, False)

    # merging: two alarms with bits on the SAME register OR together
    # (37: alarm_word_29 [0,1] on pcs 3) + (46: alarm_word_4 [4] on pcs 1) --
    # different registers, but combine 37 alone should still give both bits
    o37 = overrides_for([37])
    addr37 = PCS_BASES[2] + PCS_ALARM_WORD_1_OFFSET + (29 - 1)
    check("alarm 37 combines bit0+bit1", o37.set.get(addr37), 0b11)

    # unknown alarm id -> unsupported, not silently ignored
    ou = overrides_for([9999])
    check("unknown alarm id -> unsupported, not crash", len(ou.unsupported), 1)

    # alarm 82 has inject=None -> unsupported (can't be triggered this way)
    o82 = overrides_for([82])
    check("alarm 82 (no inject) -> unsupported", len(o82.unsupported), 1)

    # baseline: forces vdc healthy on all 3 PCS + EMU "connected" bits,
    # WITHOUT any alarm requested (rule_ids=[])
    ob = overrides_for([], baseline=True)
    check("baseline forces vdc on PCS1/2/3", {
        5015: ob.replace.get(5015), 5315: ob.replace.get(5315), 5615: ob.replace.get(5615),
    }, {5015: 7500, 5315: 7500, 5615: 7500})
    check("baseline sets EMU status_word_3 bits 0-2 (PCS RS485 connected)",
          ob.set.get(_word_addr("status_word_3", EMU_BASE, EMU_STATUS_WORD_1_OFFSET, EMU_ALARM_WORD_1_OFFSET)),
          0b111)
    check("baseline sets EMU status_word_7 bit0 (meter RS485 connected)",
          ob.set.get(_word_addr("status_word_7", EMU_BASE, EMU_STATUS_WORD_1_OFFSET, EMU_ALARM_WORD_1_OFFSET)),
          0b1)

    # baseline + a real alarm (70): baseline's vdc/comm fixes coexist with
    # #70's own AlarmWord6 bit0/1 override, untouched by each other
    ob70 = overrides_for([70], baseline=True)
    addr_aw6 = PCS_BASES[0] + PCS_ALARM_WORD_1_OFFSET + (6 - 1)
    check("baseline+70: vdc fix still present", ob70.replace.get(5015), 7500)
    # catalog's #70 inject only sets bit0 (sufficient -- the real condition
    # is an OR of bit0/bit1, see fractal_alarm_catalog.py's note)
    check("baseline+70: alarm 70's own bit still present", ob70.set.get(addr_aw6), 0b1)

    # baseline should NOT clobber a real alarm that also touches vdc: #39
    # (undervoltage, pcs_index=2, vdc=500) must win over the baseline's 750
    # on that SAME PCS (5315) -- PCS1/PCS3 (5015/5615) keep the baseline fix
    ob_and_39 = overrides_for([39], baseline=True)
    check("baseline does not override a real alarm's own vdc value (#39 wins on its PCS)",
          ob_and_39.replace.get(5315), 5000)  # 500V / 0.1 = 5000
    check("baseline's vdc fix still applies to the OTHER PCS (not touched by #39)",
          ob_and_39.replace.get(5015), 7500)

    # pcs_override: alarm 70 forced onto PCS-2 instead of the catalog's PCS-1
    # (sidesteps the backend's per-(site,PCS,rule) alarm cache -- see
    # the internal QA note 'FRACTAL_ALARM_INJECTION_SETUP')
    o70_pcs2 = overrides_for([70], pcs_override={70: 2})
    addr_aw6_pcs2 = PCS_BASES[1] + PCS_ALARM_WORD_1_OFFSET + (6 - 1)
    check("pcs_override moves alarm 70 onto PCS-2's AlarmWord6",
          o70_pcs2.set.get(addr_aw6_pcs2), 0b1)
    addr_aw6_pcs1 = PCS_BASES[0] + PCS_ALARM_WORD_1_OFFSET + (6 - 1)
    check("pcs_override leaves PCS-1's AlarmWord6 untouched",
          addr_aw6_pcs1 in o70_pcs2.set, False)

    # round-trip through the state file (real filesystem, a scratch site name)
    save_state("SELFCHECK_TMP", [46])
    set_, clear_, replace_ = read_state("SELFCHECK_TMP")
    check("save/read round-trip preserves the override", set_, {5263: 0b10000})
    clear_state("SELFCHECK_TMP")
    check("clear_state removes the file", os.path.exists(state_file_for("SELFCHECK_TMP")), False)

    print("\n=> " + ("ALL OK" if ok else "DIFFERENCES FOUND"))
    return ok


if __name__ == "__main__":
    if "--self-check" in sys.argv:
        sys.exit(0 if _self_check() else 1)
