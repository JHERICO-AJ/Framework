"""
fractal_alarm_catalog.py — the 22 OmniOps alarm IDs that Fractal telemetry
can actually activate (EMU + PCS + Meter level), per the internal QA note 'Plan_Integral_Fractal'
section 4 ("Alcance de alarmas — matriz de trazabilidad Fractal").

Unlike shared/domain/alarm_catalog.py (EPC, register/bit overrides applied by
our own tools/sim_proxy.py), Fractal alarms are NOT triggered through that
proxy at all -- confirmed 2026-09-16 that EPC and Fractal use completely
different Modbus addressing, and our proxy only knows EPC's. Fractal alarms
are instead triggered by writing analog/bit overrides into a YAML file that
the REAL Fractal simulator (simulator/fractal_site_state.py, in the separate
omniops-bess-edge repo) reads directly and hot-reloads (confirmed live by the
user 2026-09-16 -- no simulator restart needed). shared/domain/fractal_injection.py
turns entries from this catalog into that YAML block.

Each entry's `inject` describes exactly what to force, in the same shape the
real YAML file uses:
  {"analog": {field_name: value, ...}}  -- e.g. {"vdc": 950}
  {"bits":   {word_name: [bit_index, ...]}}  -- e.g. {"alarm_word_4": [4]}
  a dict can combine both when an alarm needs an analog value AND a bit gate
`pcs_index` selects which PCS unit's `analog`/`bits` block the override goes
into (1-based, matching the YAML's own `pcs: 1: / 2: / 3:` keys) -- ignored
for EMU-level or meter-level alarms.
`sustain_s` documents the real sustained-duration/gating condition the
backend evaluates before opening the alarm (None if there's no such window,
i.e. it opens on the very next tick the condition is true).

REVISED 2026-09-17 against two more sources: the internal data-intake sheet omniops_data_intake_KIRUNA
(a teammate's real, live Data Intake config, in its "Alarm-Thresholds"
sheet) and the internal QA note 'Reporte_Alarmas_Fractal_Proto_Detalle' (a per-alarm test
report with real pass/fail results). Corrections this made vs. the earlier
version (transcribed from the internal QA note 'Plan_Integral_Fractal' alone):
  - Alarm #78's threshold ambiguity is RESOLVED: IdlePowerLimitKw=5 (kW) is
    confirmed the real configured value (matching Plan Integral, NOT the
    20kW a teammate's own YAML *comment* claimed -- that comment was stale).
  - The "doesn't respect its configured sustained duration" defect is
    confirmed for #42, #43, #52, #53 specifically -- NOT #51, which the test
    report shows passing correctly even with the same short duration
    configured. (Plan Integral had lumped 51/52/53 together as all broken.)
  - Every sustained-duration field below (CommTimeoutSec,
    PcsAcOvercurrentDurationSec, IdlePowerDurationSec,
    MeterMismatchWindowDays, ...) is a real Data-Intake-configurable value,
    NOT a fixed platform default -- a teammate's own site has all of them
    turned down to 1 second (or 1 day for the 74's 7-day window) SPECIFICALLY
    to make manual testing practical. BOLIVIA's own Data Intake currently has
    no "Alarm-Thresholds" sheet/overrides configured at all (confirmed via
    direct read 2026-09-17) -- to get the same fast testing turnaround for
    BOLIVIA, the same overrides need to be added there first. Field keys are
    recorded per-alarm below (`data_intake_fields`) so that's a concrete,
    checkable list rather than a vague "configure it somehow".
  - #74 (Meter vs PCS mismatch) is NOT structurally blocked once
    MeterMismatchWindowDays is configured down (1 day, as a teammate did) --
    it's genuinely testable, just takes ~1 day of continuous simulator+
    emitter runtime, confirmed by the test report itself ("Pendiente porque
    debe hacer paso 1 día mínimo para probar la alarma", i.e. pending
    because it takes a minimum of 1 day to test -- not "can't be tested").
"""

FRACTAL_ALARMS = [
    dict(alarm_rule_id=34, name="PCS Overtemp", subsystem="PCS / Inverter",
         severity="Major/Critical", e2e="F01", pcs_index=1,
         inject={"analog": {"temp_cabinet_c": 95}, "bits": {"status_word_1": [3]}},
         inject_critical={"analog": {"temp_cabinet_c": 95}, "bits": {"status_word_7": [0]}},
         note="MAJOR needs temp_cabinet_c>90 + status_word_1 bit3 (derating). "
              "CRITICAL needs temp_cabinet_c>90 + status_word_7 bit0 or bit14 -- "
              "use `inject_critical` for that variant instead of `inject`."),
    dict(alarm_rule_id=35, name="PCS IGBT Overtemp", subsystem="PCS / Inverter",
         severity="Critical", e2e="F01", pcs_index=2,
         inject={"analog": {"temp_igbt_c": 90}},
         note="Threshold (85 C) is fixed in code, not configurable via Data Intake."),
    dict(alarm_rule_id=37, name="PCS Cooling Fan Failure", subsystem="PCS / Inverter",
         severity="Critical", e2e="F01", pcs_index=3,
         inject={"bits": {"alarm_word_29": [0, 1]}},
         note="Needs BOTH bit0 (inner fan) and bit1 (IGBT fan) set."),
    dict(alarm_rule_id=38, name="PCS DC Bus Overvoltage", subsystem="PCS / Inverter",
         severity="Critical", e2e="F02", pcs_index=1,
         inject={"analog": {"vdc": 950}},
         note="CAVEAT (Plan Integral): the simulator's vdc is fixed at 1200V by "
              "design -- with the 900V threshold this alarm is ALREADY always open "
              "in steady state. Validate the injected value specifically, don't "
              "assume steady-state proves nothing is wrong."),
    dict(alarm_rule_id=39, name="PCS DC Bus Undervoltage", subsystem="PCS / Inverter",
         severity="Critical", e2e="F02", pcs_index=2,
         inject={"analog": {"vdc": 500}}),
    dict(alarm_rule_id=40, name="PCS AC Overvoltage", subsystem="PCS / Inverter",
         severity="Major", e2e="F03", pcs_index=1,
         inject={"analog": {"vac_ab": 530}},
         note="Threshold: max(Vab,Vbc,Vca) > 1.1 x 480 = 528V."),
    dict(alarm_rule_id=41, name="PCS AC Undervoltage", subsystem="PCS / Inverter",
         severity="Major", e2e="F03", pcs_index=2,
         inject={"analog": {"vac_ab": 430}},
         note="Threshold: min(Vab,Vbc,Vca) < 0.9 x 480 = 432V."),
    dict(alarm_rule_id=42, name="PCS AC Overcurrent", subsystem="PCS / Inverter",
         severity="Critical", e2e="F04", pcs_index=1,
         inject={"analog": {"iac_a": 1350}}, sustain_s=1,
         data_intake_fields=["PcsAcOvercurrentDurationSec"],
         note="CONFIRMED DEFECT (the internal QA note 'Reporte_Alarmas_Fractal_Proto_Detalle', "
              "teammate's own live test): 'Fallo, se activa pero no repeta el time "
              "que se le programa desde data intake' -- fires immediately and "
              "ignores PcsAcOvercurrentDurationSec even when it's configured down "
              "to 1s (a teammate's real KIRUNA site config), so this is a genuine "
              "'ignores duration entirely' bug, not just a slow-default artifact."),
    dict(alarm_rule_id=43, name="PCS AC Undercurrent", subsystem="PCS / Inverter",
         severity="Minor", e2e="F04", pcs_index=2,
         inject={"analog": {"iac_a": 110}}, sustain_s=1,
         data_intake_fields=["PcsAcUndercurrentDurationSec"],
         note="Needs an active setpoint (PCS actually dispatching). CONFIRMED "
              "DEFECT: same as #42 -- fires immediately, ignores "
              "PcsAcUndercurrentDurationSec even at the 1s value a teammate "
              "configured (the internal QA note 'Reporte_Alarmas_Fractal_Proto_Detalle')."),
    dict(alarm_rule_id=44, name="Phase Loss", subsystem="PCS / Inverter",
         severity="Critical", e2e="F03", pcs_index=3,
         inject={"analog": {"vac_ab": 199}},
         note="Alt injection: iac_a=4 (with another phase still live) also triggers it."),
    dict(alarm_rule_id=45, name="Phase Imbalance", subsystem="PCS / Inverter",
         severity="Major", e2e="F03", pcs_index=4,
         inject={"analog": {"vac_ab": 300, "vac_bc": 480, "vac_ca": 480}},
         note="Threshold: (max-min)/avg > 20% while operating."),
    dict(alarm_rule_id=46, name="PCS Ground Fault", subsystem="PCS / Inverter",
         severity="Critical", e2e="F05", pcs_index=1,
         inject={"bits": {"alarm_word_4": [4]}}),
    dict(alarm_rule_id=47, name="PCS DC Grounding Fault", subsystem="PCS / Inverter",
         severity="Critical", e2e="F05", pcs_index=2,
         inject={"bits": {"alarm_word_4": [5]}}),
    dict(alarm_rule_id=48, name="PCS IGBT / SCR Failure", subsystem="PCS / Inverter",
         severity="Critical", e2e="F06", pcs_index=1,
         inject={"bits": {"alarm_word_11": [10]}},
         note="Any of bit10/11/12/13 triggers it -- bit10 used here."),
    dict(alarm_rule_id=49, name="PCS Pre-charge Failure", subsystem="PCS / Inverter",
         severity="Critical", e2e="F02", pcs_index=3,
         inject={"bits": {"alarm_word_2": [7]}}),
    dict(alarm_rule_id=51, name="EMS-BMS Comm Lost", subsystem="EMS / Gateway",
         severity="Critical", e2e="F07", pcs_index=1,
         inject={"bits": {"alarm_word_27": [1]}}, sustain_s=1,
         data_intake_fields=["CommTimeoutSec"],
         note="CORRECTED 2026-09-17: NOT part of the duration-defect group -- "
              "the internal QA note 'Reporte_Alarmas_Fractal_Proto_Detalle''s own test result "
              "for #51 is 'Paso la prueba' (passed), i.e. it DOES correctly "
              "respect CommTimeoutSec (confirmed at the 1s value a teammate "
              "configured). Plan Integral had lumped 51/52/53 together as all "
              "broken -- that grouping was wrong for #51 specifically."),
    dict(alarm_rule_id=52, name="EMS-PCS Comm Lost", subsystem="EMS / Gateway",
         severity="Critical", e2e="F07", pcs_index=None,
         inject={"emu_bits": {"status_word_3": [0, 1, 2]}}, sustain_s=1,
         data_intake_fields=["CommTimeoutSec"],
         note="Gate: EMU status_word_3 bit0/1/2 = 0 (Disconnected). Already used as "
              "the working 'Data path: Fault' signal in test_device_status_panel.py "
              "(_any_pcs_comm_disconnected). CONFIRMED DEFECT (teammate's own live "
              "test, the internal QA note 'Reporte_Alarmas_Fractal_Proto_Detalle'): 'Fallo, se "
              "activa pero no repeta el time' -- ignores CommTimeoutSec even at "
              "1s. Extra procedural note from that same report: 'Comentar el bit "
              "en el yaml para que la alarma se active' (the bit line may need to "
              "be commented out/back in the YAML to actually trigger it)."),
    dict(alarm_rule_id=53, name="EMS-Meter Comm Lost", subsystem="EMS / Gateway",
         severity="Warning", e2e="F07", pcs_index=None,
         inject={"emu_bits": {"status_word_7": [0]}}, sustain_s=1,
         data_intake_fields=["CommTimeoutSec"],
         note="Gate: EMU status_word_7 bit0 = 0 (Meter RS485 Disconnected). "
              "CONFIRMED DEFECT (teammate's own live test): same as #52 -- "
              "ignores CommTimeoutSec even at the 1s configured value."),
    dict(alarm_rule_id=66, name="Container Smoke Detected", subsystem="Safety / Fire",
         severity="Critical", e2e="F08", pcs_index=1,
         inject={"bits": {"alarm_word_27": [7]}},
         note="No numeric threshold, pure bit activation."),
    dict(alarm_rule_id=70, name="Lightning / SPD Alarm", subsystem="Safety / Fire",
         severity="Minor", e2e="F09", pcs_index=1,
         inject={"bits": {"alarm_word_6": [0]}},
         inject_alt={"emu_bits": {"alarm_word_1": [5]}},
         note="CORRECTED 2026-09-18 (re-tested live against BOLIVIA 4 after the "
              "the internal QA note 'Reporte_Alarmas_Fractal_Proto_Detalle_3' update): the "
              "EMU-side path (`inject_alt`, EMU alarm_word_1 bit5) is NOT broken --"
              " confirmed to open real Alerts in Alarms & Events. The two paths are "
              "simply DIFFERENT IN SCOPE, not one working/one broken: `inject` "
              "(PCS alarm_word_6 bit0/bit1) opens the alarm for exactly ONE PCS "
              "device; `inject_alt` (EMU alarm_word_1/2 bit5) opens it for the "
              "EMU/Gateway device AND cascades to EVERY PCS at the site at once "
              "(confirmed live: forcing the EMU bit produced fresh 'first occurred' "
              "rows for PCS-1, PCS-3, and the Gateway device simultaneously, "
              "matching that report's own note 'EMU activa los PCS y el gateway'). "
              "Use `inject` to target a single PCS (e.g. to avoid the per-device "
              "alarm-cache gotcha, see the internal QA note 'FRACTAL_ALARM_INJECTION_SETUP'); use "
              "`inject_alt` for an E2E-F11-style multi-device fan-out from one "
              "override. The earlier 2026-09-16 note calling inject_alt "
              "'confirmed-broken' was based on the OLDER Reporte_Alarmas_Fractal_"
              "Proto_Detalle.txt (pre-_3 update) and is now superseded."),
    dict(alarm_rule_id=74, name="Meter vs PCS data mismatch", subsystem="Early Warning",
         severity="Warning", e2e="F10", pcs_index=None,
         inject={"meter_total_active_power_kw_factor": 1.05},
         sustain_s=24 * 3600,
         data_intake_fields=["MeterMismatchWindowDays", "MeterMismatchTolPct"],
         note="CORRECTED 2026-09-17: NOT structurally blocked. The simulator's own "
              "1.5% transformer/line loss (LOSS_FACTOR=0.985 in "
              "fractal_site_state.py) already exceeds a 1% MeterMismatchTolPct by "
              "design -- no extra injection needed for the CONDITION. The real "
              "gate is TIME: MeterMismatchWindowDays is a genuine Data-Intake "
              "field (not a fixed default) -- a teammate's own KIRUNA site has it "
              "configured to 1 day (not the 7-day default the Plan Integral "
              "assumed). the internal QA note 'Reporte_Alarmas_Fractal_Proto_Detalle' confirms "
              "this directly: status 'Pendiente porque debe hacer paso 1 día "
              "mínimo para probar la alarma' -- pending because it takes a "
              "minimum of 1 day to test, NOT blocked. BOLIVIA's Data Intake has "
              "no Alarm-Thresholds override for this yet (confirmed via direct "
              "read -- no such sheet exists at all); add one set to 1 day to get "
              "the same fast turnaround for BOLIVIA's own E2E-F10 run."),
    dict(alarm_rule_id=78, name="PCS Idle Power Drift", subsystem="Early Warning",
         severity="Warning", e2e="F10", pcs_index=1,
         inject={"analog": {"p_ac_kw": 8}, "bits": {"status_word_1": [5]}},
         sustain_s=1,
         data_intake_fields=["IdlePowerLimitKw", "IdlePowerDurationSec"],
         note="CORRECTED 2026-09-17: threshold ambiguity RESOLVED -- "
              "IdlePowerLimitKw=5kW confirmed real (matches Plan Integral; a "
              "teammate's own YAML *comment* claiming a 20kW runtime default was "
              "stale/wrong). p_ac_kw=8 is the teammate's own confirmed-working "
              "injection value (the internal QA note 'Reporte_Alarmas_Fractal_Proto_Detalle': "
              "'p_ac_kw = 8 > idle power limit 5kw sostenido >= 1s'), not the "
              "100kW guess used previously. IdlePowerDurationSec is likewise a "
              "real Data-Intake field, configured to 1s on that teammate's site "
              "(not a fixed 3600s wait) -- BOLIVIA's Data Intake has no override "
              "for either field yet (confirmed via direct read of 'Intake "
              "Fields' -- no 'idle' field exists there at all); add both to "
              "BOLIVIA's Data Intake (5 / 1) to get the same fast local test. "
              "GATING BIT CONFIRMED EMPIRICALLY 2026-09-19 (live A/B/C test "
              "against BOLIVIA 5, one variant per PCS to rule out cross-"
              "contamination): p_ac_kw alone (no bit) does NOT open the alarm; "
              "`alarm_word_1` bit5 (as the internal report Reporte_Alarmas_Fractal_Proto_"
              "Detalle_3.txt's table literally says) does NOT open it either; "
              "`status_word_1` bit5 (what this entry actually injects) DOES. "
              "The `_3.txt` report's 'PcsModule.alarm_word_1' mention for #78 "
              "is confirmed a typo -- keep using status_word_1 here regardless "
              "of what a future revision of that report says, unless a new "
              "live test says otherwise."),
    dict(alarm_rule_id=73, name="PCS Power Factor Anomalous Deviation", subsystem="PCS / Inverter",
         severity="Minor", e2e=None, pcs_index=1,
         inject={"analog": {"p_ac_kw": 100, "q_ac_kvar": 62}, "bits": {"status_word_1": [5]}},
         sustain_s=None,
         data_intake_fields=["PowerFactorTarget", "PowerFactorDeviationLimit"],
         note="NOT in Plan Integral's 22-alarm list -- found only in "
              "the internal QA note 'Reporte_Alarmas_Fractal_Proto_Detalle', marked PARCIAL. "
              "p_ac_kw=100/q_ac_kvar=62 gives PF~0.85, a delta of 0.15 against "
              "PowerFactorTarget=1 with PowerFactorDeviationLimit=0.05 (a "
              "teammate's real KIRUNA config) -- deviation clearly exceeds the "
              "band. No confirmed pass/fail result yet (report's Estado column "
              "shows an ambiguous 'X' marker, not 'Paso la prueba') and it has no "
              "assigned E2E-F0x scenario in the Plan Integral -- treat as "
              "exploratory/unconfirmed, not proven, until independently verified."),
    dict(alarm_rule_id=82, name="System Boot Time Abnormally Prolonged", subsystem="PCS / Inverter",
         severity="Warning", e2e=None, pcs_index=1,
         inject=None, sustain_s=None,
         data_intake_fields=["PcsBootTimeLimitSec"],
         note="NOT in Plan Integral's 22-alarm list -- found only in "
              "the internal QA note 'Reporte_Alarmas_Fractal_Proto_Detalle', marked Parcial, "
              "status 'No se puede activar, pedir mas detalles' (cannot activate, "
              "need to ask for more details) -- deliberately has no `inject` "
              "value here, don't guess one. Field: PcsModule.status_word_5 "
              "(bits 6-8, Startup process enum 0-7); logic opens WARNING if the "
              "state sits in sub-steps 1-6 for longer than PcsBootTimeLimitSec "
              "(default 5s) without reaching 7 ('Startup completed'). It already "
              "fires once automatically on simulator startup (real boot takes "
              "~6-7s); to force it again requires restarting the PCS OFF-> "
              "STARTING, which this YAML-only injection mechanism can't do by "
              "itself. Unresolved raw notes from that report: 'Alarma cada 60 "
              "segundos?' / 'Activa 2 dispositivos' -- needs follow-up with the "
              "dev/teammate before this can be automated."),
]

BY_RULE_ID = {a["alarm_rule_id"]: a for a in FRACTAL_ALARMS}

# E2E scenario groupings, per the internal QA note 'Plan_Integral_Fractal' section 7.
E2E_SCENARIOS = {
    "F01": {"title": "PCS thermal chain", "alarm_ids": [34, 35, 37]},
    "F02": {"title": "PCS DC bus disturbance", "alarm_ids": [38, 39, 49]},
    "F03": {"title": "AC grid voltage disturbance", "alarm_ids": [40, 41, 44, 45]},
    "F04": {"title": "PCS AC current fault", "alarm_ids": [42, 43]},
    "F05": {"title": "Ground isolation fault", "alarm_ids": [46, 47]},
    "F06": {"title": "Power electronics fault", "alarm_ids": [48]},
    "F07": {"title": "Communication link loss", "alarm_ids": [51, 52, 53]},
    "F08": {"title": "Container fire detection", "alarm_ids": [66]},
    "F09": {"title": "Surge protection (SPD)", "alarm_ids": [70]},
    "F10": {"title": "Trend alarms (Early Warning)", "alarm_ids": [74, 78]},
    "F11": {"title": "Concurrent multi-site isolation", "alarm_ids": []},  # any alarm, any site
}


def _self_check():
    print("(fractal alarm catalog test — pure data, no network)\n")
    ok = True

    def check(desc, got, exp):
        nonlocal ok
        good = got == exp
        ok = ok and good
        print(f"  {desc:46} {'OK' if good else f'FAIL got={got} exp={exp}'}")

    check("24 alarms total (22 Plan Integral + #73/#82)", len(FRACTAL_ALARMS), 24)
    check("no duplicate alarm_rule_id", len(BY_RULE_ID), len(FRACTAL_ALARMS))
    check("alarm 70 is Minor", BY_RULE_ID[70]["severity"], "Minor")
    check("alarm 52 has no pcs_index (EMU-level)", BY_RULE_ID[52]["pcs_index"], None)
    check("every mapped alarm's e2e is a real E2E scenario",
          all(a["e2e"] in E2E_SCENARIOS for a in FRACTAL_ALARMS if a["e2e"] is not None), True)
    check("alarms 73/82 are deliberately unmapped (not in Plan Integral's 22)",
          {a["alarm_rule_id"] for a in FRACTAL_ALARMS if a["e2e"] is None}, {73, 82})
    check("alarm 82 has no inject value (can't be triggered via YAML alone)",
          BY_RULE_ID[82]["inject"], None)
    check("alarm 51 is NOT flagged with the duration defect (unlike 52/53)",
          "CONFIRMED DEFECT" not in BY_RULE_ID[51]["note"], True)

    print("\n=> " + ("ALL OK" if ok else "DIFFERENCES FOUND"))
    return ok


if __name__ == "__main__":
    import sys
    if "--self-check" in sys.argv:
        sys.exit(0 if _self_check() else 1)
