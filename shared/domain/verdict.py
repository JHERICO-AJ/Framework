"""
verdict.py — the JUDGE of alarm validation.

Takes two independent facts and decides ONE verdict:

  - cause_active : does the ORACLE (raw data from the simulator) say that the
                   condition that should trigger the alarm is present? (Evt1
                   bit or telemetry threshold — computed by oracle.py).
  - alarm_open   : does OmniOps have that alarm as Open in the API/UI?

Crosses the two and gives one of these verdicts:

  cause | alarm | verdict              | what it means
  ------+-------+----------------------+------------------------------------------
   yes  |  yes  | PASS                 | correct detection (real alarm, detected)
   no   |  no   | PASS_HEALTHY         | healthy and no alarm: correct
   no   |  yes  | FAIL_FALSE_ALARM     | FALSE ALARM (fires with no cause) <<<
   yes  |  no   | FAIL_NOT_DETECTED    | NOT DETECTED (there is a cause and it doesn't fire) <<<

Special case: if the alarm is `oracle_independent=False` (ems/trend), we can't
compute the cause on our own -> NOT_VERIFIABLE (doesn't count as an error).

It's pure logic: no network, no Modbus. Can be tested standalone.

Run the self-check:  python verdict.py --self-check
"""

from __future__ import annotations

# labels (constants so we don't misspell them in other files)
PASS = "PASS"
PASS_HEALTHY = "PASS_HEALTHY"
FAIL_FALSE_ALARM = "FAIL_FALSE_ALARM"
FAIL_NOT_DETECTED = "FAIL_NOT_DETECTED"
NOT_VERIFIABLE = "NOT_VERIFIABLE"

# does the label count as reliable for the success rate?
RELIABLE = {PASS, PASS_HEALTHY, FAIL_FALSE_ALARM, FAIL_NOT_DETECTED}
# is the label an "OK"?
IS_OK = {PASS, PASS_HEALTHY}

DESCRIPTION = {
    PASS: "correct detection (real alarm and detected)",
    PASS_HEALTHY: "healthy and no alarm (correct)",
    FAIL_FALSE_ALARM: "FALSE ALARM: fires with no cause in the raw data",
    FAIL_NOT_DETECTED: "NOT DETECTED: there is a cause in the raw data and the alarm doesn't fire",
    NOT_VERIFIABLE: "not verifiable (oracle_independent=False: ems/trend)",
}


def verdict(cause_active, alarm_open, oracle_independent=True):
    """Returns one of the labels above.

    cause_active / alarm_open may come in as None if they couldn't be
    measured; in that case we also return NOT_VERIFIABLE (we don't risk a
    false error).
    """
    if not oracle_independent:
        return NOT_VERIFIABLE
    if cause_active is None or alarm_open is None:
        return NOT_VERIFIABLE

    cause = bool(cause_active)
    alarm = bool(alarm_open)
    if cause and alarm:
        return PASS
    if not cause and not alarm:
        return PASS_HEALTHY
    if not cause and alarm:
        return FAIL_FALSE_ALARM
    return FAIL_NOT_DETECTED          # cause and not alarm


def is_ok(label):
    return label in IS_OK


def is_reliable(label):
    return label in RELIABLE


def classify(cause_state, open_, fresh):
    """Verdict for alarms that are NOT closed (they use first/lastOccurred).
    An alarm that is open but NOT fresh (an old one stuck from another day) is
    treated as not-open, so it isn't flagged as a false alarm. cause None ->
    NOT_VERIFIABLE.
    Used both by the live monitor and the alarms check command (tools/run_check)."""
    if cause_state is None:
        return NOT_VERIFIABLE
    return verdict(cause_state, bool(open_ and fresh), oracle_independent=True)


# ---------------------------------------------------------------------------
def _self_check():
    print("(verdict test — pure logic, no network)\n")
    cases = [
        # (cause, alarm, oracle_independent, expected)
        (True,  True,  True,  PASS),
        (False, False, True,  PASS_HEALTHY),
        (False, True,  True,  FAIL_FALSE_ALARM),
        (True,  False, True,  FAIL_NOT_DETECTED),
        (True,  True,  False, NOT_VERIFIABLE),   # ems/trend: not verifiable
        (None,  True,  True,  NOT_VERIFIABLE),   # couldn't measure the cause
        (True,  None,  True,  NOT_VERIFIABLE),   # couldn't read the API
    ]
    all_ok = True
    for cause, alarm, oi, expected in cases:
        got = verdict(cause, alarm, oracle_independent=oi)
        ok = got == expected
        all_ok = all_ok and ok
        print(f"  cause={str(cause):5} alarm={str(alarm):5} oi={str(oi):5} "
              f"-> {got:18} {'OK' if ok else f'FAIL (expected {expected})'}")
    print("\n=> " + ("ALL OK ✓" if all_ok else "DIFFERENCES FOUND ✗"))
    return all_ok


if __name__ == "__main__":
    import sys
    ok = _self_check()          # this file only has the self-check
    sys.exit(0 if ok else 1)
