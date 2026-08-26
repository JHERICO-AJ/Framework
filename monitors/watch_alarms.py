"""watch_alarms — LIVE alarm monitor: you inject (from another terminal) and
see cause (raw) vs API in real time. Watches in a loop, doesn't validate.

    python -m monitors.watch_alarms
    # in another terminal:  python -m tools.run_check 16   (or manual injection)
"""
from __future__ import annotations

import datetime
import time

from shared.config.settings import BASE_URL, OMNIOPS_EVERY_S, SIM_HOST, SIM_PORT
from shared.datasource.modbus_source import ModbusReader
from shared.domain import alarm_catalog as cat
from shared.domain.oracle import evaluate
from shared.domain.verdict import classify, FAIL_FALSE_ALARM, FAIL_NOT_DETECTED
from framework_api.client.api_client import ApiClient
from framework_api.services.alarms_service import AlarmsService

TOL_S = 20


def _api_snapshot(service):
    alarms = service.get_alarms()
    open_ids = {a.rule_id for a in alarms if a.is_open and a.rule_id is not None}
    last_by_rule = {}
    for a in alarms:
        if a.last_occurred:
            prev = last_by_rule.get(a.rule_id)
            if prev is None or a.last_occurred > prev:
                last_by_rule[a.rule_id] = a.last_occurred
    return open_ids, last_by_rule


def _connect_reader():
    reader = ModbusReader()
    reader.read_register(cat.ADDR["evt1_802"])
    return reader


def _build_baseline(service):
    start = datetime.datetime.now(datetime.timezone.utc)
    baseline, _ = _api_snapshot(service)
    print(f"watch_alarms — started {start.astimezone():%H:%M:%S}. "
          f"Already open: {sorted(baseline)}")
    print("Inject from another terminal (python -m tools.run_check <id>). Ctrl+C to exit.\n")
    return start, baseline


def _interesting_rule_ids(present, last_by_rule, start):
    interest = set(present)
    for rule_id, last_update in last_by_rule.items():
        if last_update >= start - datetime.timedelta(seconds=TOL_S):
            interest.add(rule_id)
    return interest


def _print_line(now_str, rule_id, states, open_ids, last_by_rule, start):
    name = cat.BY_RULE_ID.get(rule_id, {}).get("name", f"rule {rule_id}")
    cause = states.get(rule_id, (None, ""))[0]
    last_update = last_by_rule.get(rule_id)
    fresh = bool(last_update and last_update >= start - datetime.timedelta(seconds=TOL_S))
    verdict = classify(cause, rule_id in open_ids, fresh)
    mark = "  <<<" if verdict in (FAIL_FALSE_ALARM, FAIL_NOT_DETECTED) else ""
    cause_text = {True: "YES", False: "no ", None: "n/v"}[cause]
    print(f"[{now_str}] ID {rule_id:2} {name:24} cause:{cause_text} "
          f"api:{'YES' if rule_id in open_ids else 'no'}  -> {verdict}{mark}")


def _watch_loop(reader, service, start, baseline):
    while True:
        now_str = datetime.datetime.now().strftime("%H:%M:%S")
        states, present = evaluate(reader)
        open_ids, last_by_rule = _api_snapshot(service)

        interest = _interesting_rule_ids(present, last_by_rule, start)

        if not interest:
            print(f"[{now_str}] no injected causes or new alarms "
                  f"(already open: {len(baseline)})")
        else:
            for rule_id in sorted(interest):
                _print_line(now_str, rule_id, states, open_ids, last_by_rule, start)
        time.sleep(OMNIOPS_EVERY_S)


def run():
    service = AlarmsService(ApiClient(BASE_URL))
    try:
        reader = _connect_reader()
    except Exception as e:
        print(f"Can't read the simulator at {SIM_HOST}:{SIM_PORT}. "
              f"Did you start the proxy?\n  {e}")
        return

    start, baseline = _build_baseline(service)
    try:
        _watch_loop(reader, service, start, baseline)
    except KeyboardInterrupt:
        print("\ndone.")
    finally:
        reader.close()


if __name__ == "__main__":
    run()
