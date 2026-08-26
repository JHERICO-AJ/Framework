"""run_check.py — OPERATIONAL command to trigger and verify alarms (cross-layer).

Orchestrates 3 layers: injects (domain+proxy), reads the raw data (oracle), and
reads the API (AlarmsService), and gives a verdict per alarm. It's NOT "just
API": that's why it lives in tools/ (a tool), not in framework_api/.

  python -m tools.run_check 16                         # simple
  python -m tools.run_check 16 29 --live               # several, live
  python -m tools.run_check 16 --at 10 --until 30 --live   # timed scene

The verify_alarms() function is reused by tests/cross_layer/test_alarms.py
(same logic). Needs the stack up above (sim + proxy + edge + OmniOps).
"""
from __future__ import annotations

import datetime
import sys
import time

from shared.config.settings import BASE_URL, OMNIOPS_EVERY_S
from shared.datasource.modbus_source import ModbusReader
from shared.domain import alarm_catalog as cat
from shared.domain.injection import save_state, clear_state
from shared.domain.oracle import evaluate
from shared.domain.verdict import classify, PASS, PASS_HEALTHY, NOT_VERIFIABLE
from framework_api.client.api_client import ApiClient
from framework_api.services.alarms_service import AlarmsService

TIMEOUT_S = 45
TOL_S = 25


def _near(ts, ref, tol_s):
    return bool(ts and abs((ts - ref).total_seconds()) <= tol_s)


def _api_snapshot(alarms_service):
    """(set of open rule_ids, dict rule_id -> max lastOccurred)."""
    alarms = alarms_service.get_alarms()
    open_ids = {a.rule_id for a in alarms if a.is_open and a.rule_id is not None}
    last_by_rule = {}
    for a in alarms:
        if a.last_occurred:
            prev = last_by_rule.get(a.rule_id)
            if prev is None or a.last_occurred > prev:
                last_by_rule[a.rule_id] = a.last_occurred
    return open_ids, last_by_rule


class Result:
    def __init__(self, rule_id, name):
        self.rule_id = rule_id
        self.name = name
        self.cause = None
        self.in_api = False
        self.verdict = NOT_VERIFIABLE
        self.last = None
        self.appeared_in_s = None
        self.time_ok = None

    @property
    def ok(self):
        return self.verdict in (PASS, PASS_HEALTHY, NOT_VERIFIABLE)


def verify_alarms(ids, alarms_service, reader=None, timeout=TIMEOUT_S, tol_s=TOL_S,
                  at=0, live=False):
    """Injects ids, verifies cause(raw)+API+time, clears. Returns [Result]."""
    own_reader = reader is None
    if own_reader:
        reader = ModbusReader()
        reader.read_register(cat.ADDR["evt1_802"])   # fails clearly if there's no proxy/sim

    res = {r: Result(r, cat.BY_RULE_ID.get(r, {}).get("name", f"rule {r}")) for r in ids}
    if at:
        if live:
            print(f"Firing in {at}s…")
        time.sleep(at)

    moment = datetime.datetime.now(datetime.timezone.utc)
    try:
        save_state(ids)
        if live:
            print(f"[{moment.astimezone():%H:%M:%S}] injected {ids}. Waiting for OmniOps…")
        t0 = time.time()
        while time.time() - t0 < timeout:
            states, _ = evaluate(reader)
            open_ids, last_by_rule = _api_snapshot(alarms_service)
            done = True
            for r in ids:
                res[r].cause = states.get(r, (None, ""))[0]
                res[r].in_api = r in open_ids
                ul = last_by_rule.get(r)
                res[r].last = ul
                fresh = _near(ul, moment, tol_s) or (ul and ul >= moment)
                if fresh and res[r].appeared_in_s is None:
                    res[r].appeared_in_s = round(time.time() - t0, 1)
                    res[r].time_ok = _near(ul, moment, tol_s)
                res[r].verdict = classify(res[r].cause, res[r].in_api, bool(fresh))
                if res[r].verdict not in (PASS, NOT_VERIFIABLE):
                    done = False
            if live:
                _live_line(res, ids)
            if done:
                break
            time.sleep(OMNIOPS_EVERY_S)
    finally:
        clear_state()
        if own_reader:
            reader.close()
    return [res[r] for r in ids]


def _et(cause):
    return {True: "YES", False: "no", None: "n/v"}[cause]


def _live_line(res, ids):
    hora = datetime.datetime.now().strftime("%H:%M:%S")
    parts = [f"ID{r} cause:{_et(res[r].cause)} api:{'YES' if res[r].in_api else 'no'} "
             f"{res[r].verdict}" for r in ids]
    print("  [" + hora + "] " + "  |  ".join(parts))


def _print(results):
    print("\n=== RESULT ===")
    for r in results:
        ts = f" last={r.last.astimezone():%H:%M:%S}" if r.last else ""
        extra = ""
        if r.appeared_in_s is not None:
            extra = f"  (appeared in {r.appeared_in_s}s, {'time✓' if r.time_ok else 'time✗'})"
        print(f"  ID {r.rule_id:2} {r.name:26} cause:{_et(r.cause)} "
              f"api:{'YES' if r.in_api else 'no'}{ts}  -> {r.verdict}{extra}")
    fail = [r.rule_id for r in results if not r.ok]
    print(f"\n  {'FAILING: ' + str(fail) if fail else 'All OK ✓'}")


def _parse_args(args):
    ids, at, until, live, skip = [], 0, 0, ("--live" in args or "--vivo" in args), set()
    for j, a in enumerate(args):
        if a == "--at" and j + 1 < len(args):
            at = int(args[j + 1]); skip.add(j + 1)
        elif a in ("--until", "--hasta") and j + 1 < len(args):
            until = int(args[j + 1]); skip.add(j + 1)
    for j, a in enumerate(args):
        if j not in skip and not a.startswith("--") and a.isdigit():
            ids.append(int(a))
    return ids, at, until, live


if __name__ == "__main__":
    ids, at, until, live = _parse_args(sys.argv[1:])
    if not ids:
        print("Usage: python -m tools.run_check <id> [<id> ...] [--at N] [--live]")
        sys.exit(1)
    service = AlarmsService(ApiClient(BASE_URL))
    print(f"Testing alarms {ids}…")
    try:
        results = verify_alarms(ids, service, at=at, live=live)
    except Exception as e:
        print(f"\nCouldn't test: {e}\nIs the stack up? (sim+proxy+edge) and OmniOps.")
        sys.exit(1)
    _print(results)
    sys.exit(0 if all(r.ok for r in results) else 1)
