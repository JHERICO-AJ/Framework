"""probar.py — operational command to inject and verify alarms (cross-layer).

Orchestrates 3 layers: it injects the condition (domain + proxy), reads the raw
value (oracle) and reads the API (AlarmsService), and gives a verdict per alarm.
It is NOT "API-only": that is why it lives in tools/ (a tool), not in framework_api/.

  python -m tools.probar 16                       # simple
  python -m tools.probar 16 29 --vivo             # several, live
  python -m tools.probar 16 --at 10 --hasta 30 --vivo   # timed scene
  python -m tools.probar 16 --with-ui             # also check it shows on screen
  python -m tools.probar --criticals              # all injectable critical alarms

verify_alarms() is reused by tests/cross_layer/test_alarms.py (same logic).
Requires the chain up (simulator + proxy + edge + OmniOps).

NOTE: functions imported from the domain still keep Spanish names
(guardar_estado, evaluar, clasificar, ...). They will be renamed in the global
English pass; renaming them now would ripple across the whole repo.
"""
from __future__ import annotations

import datetime
import sys
import time

from shared.config.settings import BASE_URL, OMNIOPS_EVERY_S
from shared.datasource.modbus_source import LectorModbus
from shared.domain import alarm_catalog as cat
from shared.domain.injection import guardar_estado, limpiar_estado
from shared.domain.oracle import evaluar
from shared.domain.verdict import clasificar, PASA, PASA_SANO, NO_VERIFICABLE
from framework_api.client.api_client import ApiClient
from framework_api.services.alarms_service import AlarmsService

TIMEOUT_S = 45
TOL_S = 25


def _near(ts, ref, tol_s):
    return bool(ts and abs((ts - ref).total_seconds()) <= tol_s)


def _api_snapshot(alarms_service):
    """(set of open rule_ids, dict rule_id -> latest lastOccurred)."""
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
        self.verdict = NO_VERIFICABLE
        self.last = None
        self.appeared_in_s = None
        self.time_ok = None
        self.ui_shown = None          # with --with-ui: the alarm shows on screen

    @property
    def ok(self):
        base = self.verdict in (PASA, PASA_SANO, NO_VERIFICABLE)
        return base and (self.ui_shown is not False)


def _check_ui(ids, res):
    """Open the /alarms screen and mark, per alarm, whether it shows in the table."""
    from shared.config.credentials import load_credentials
    from framework_ui.browser.browser_factory import BrowserFactory
    from framework_ui.pages.auth.login_page import LoginPage
    from framework_ui.pages.alarms_events.alarms_page import AlarmsPage

    creds = load_credentials()
    factory = BrowserFactory()
    page = factory.__enter__()
    try:
        LoginPage(page).login(creds["email"], creds["password"])
        rows = AlarmsPage(page).open().rows()
        shown = {(r.name or "").strip().lower() for r in rows}
        for rid in ids:
            name = cat.BY_RULE_ID.get(rid, {}).get("name", "")
            res[rid].ui_shown = name.strip().lower() in shown
    finally:
        factory.__exit__(None, None, None)


def verify_alarms(ids, alarms_service, reader=None, timeout=TIMEOUT_S, tol_s=TOL_S,
                  at=0, live=False, with_ui=False):
    """Inject ids, verify cause(raw)+API+time, clean up. Returns [Result].
    With with_ui=True it also opens the /alarms screen and checks they show."""
    own_reader = reader is None
    if own_reader:
        reader = LectorModbus()
        reader.leer_registro(cat.ADDR["evt1_802"])   # fails clearly if no proxy/sim

    res = {r: Result(r, cat.BY_RULE_ID.get(r, {}).get("name", f"rule {r}")) for r in ids}
    if at:
        if live:
            print(f"Firing in {at}s…")
        time.sleep(at)

    moment = datetime.datetime.now(datetime.timezone.utc)
    try:
        guardar_estado(ids)
        if live:
            print(f"[{moment.astimezone():%H:%M:%S}] injected {ids}. Waiting for OmniOps…")
        t0 = time.time()
        while time.time() - t0 < timeout:
            states, _ = evaluar(reader)
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
                res[r].verdict = clasificar(res[r].cause, res[r].in_api, bool(fresh))
                if res[r].verdict not in (PASA, NO_VERIFICABLE):
                    done = False
            if live:
                _live_line(res, ids)
            if done:
                break
            time.sleep(OMNIOPS_EVERY_S)

        if with_ui:                       # SCREEN layer: does it show in /alarms?
            if live:
                print("  Checking the /alarms screen…")
            _check_ui(ids, res)
    finally:
        limpiar_estado()
        if own_reader:
            reader.close()
    return [res[r] for r in ids]


def _api_state(alarms_service, rid):
    """(is_open, first_occurred, last_occurred) for a rule_id, from the API."""
    is_open = False
    first = last = None
    for a in alarms_service.get_alarms():
        if a.rule_id == rid:
            if a.is_open:
                is_open = True
            if a.first_occurred and (first is None or a.first_occurred < first):
                first = a.first_occurred
            if a.last_occurred and (last is None or a.last_occurred > last):
                last = a.last_occurred
    return is_open, first, last


def _read_ui_row(alarm_name):
    """Open /alarms once and return the row (AlarmRow) for `alarm_name`, or None."""
    from shared.config.credentials import load_credentials
    from framework_ui.browser.browser_factory import BrowserFactory
    from framework_ui.pages.auth.login_page import LoginPage
    from framework_ui.pages.alarms_events.alarms_page import AlarmsPage

    creds = load_credentials()
    factory = BrowserFactory()
    page = factory.__enter__()
    try:
        LoginPage(page).login(creds["email"], creds["password"])
        rows = AlarmsPage(page).open().rows()
        target = alarm_name.strip().lower()
        for r in rows:
            if (r.name or "").strip().lower() == target:
                return r
        return None
    finally:
        factory.__exit__(None, None, None)


def run_scene(alarm_id, alarms_service, at=5, until=40, reader=None, tol_s=TOL_S):
    """Full end-to-end scene for one alarm, shown live:

      0..at   : before injection (alarm absent)
      at      : inject; record the exact moment
      verify  : API creates it, firstOccurred ~ injection moment (time OK);
                UI shows it and its last matches the API's last
      at..until: injection stays; lastOccurred rises live
      until   : clear; verify cause is gone (raw) and lastOccurred freezes
    """
    from framework_ui.pages.alarms_events.components.alarms_table import parse_ui_datetime

    own_reader = reader is None
    if own_reader:
        reader = LectorModbus()
        reader.leer_registro(cat.ADDR["evt1_802"])

    name = cat.BY_RULE_ID.get(alarm_id, {}).get("name", f"rule {alarm_id}")
    out = {"alarm_id": alarm_id, "name": name}
    start = time.time()

    def secs():
        return round(time.time() - start, 1)

    try:
        print(f"\n=== SCENE: alarm {alarm_id} ({name}) — fire at {at}s, clear at {until}s ===\n")

        # phase 0: before injection
        while time.time() - start < at:
            cause = evaluar(reader)[0].get(alarm_id, (None, ""))[0]
            print(f"  [t={secs():>4}s] before injection   cause:{_et(cause)}")
            time.sleep(OMNIOPS_EVERY_S)

        # phase 1: inject
        moment = datetime.datetime.now(datetime.timezone.utc)
        guardar_estado([alarm_id])
        print(f"\n  [t={secs():>4}s] >>> INJECT ({moment.astimezone():%H:%M:%S} local)\n")

        # phase 2: wait until API creates it (fresh), then check timestamps + UI
        api_first = api_last = None
        appeared_at = None
        while time.time() - start < until:
            cause = evaluar(reader)[0].get(alarm_id, (None, ""))[0]
            is_open, api_first, api_last = _api_state(alarms_service, alarm_id)
            fresh = bool(api_last and api_last >= moment - datetime.timedelta(seconds=tol_s))
            rising = f" last={api_last.astimezone():%H:%M:%S}" if api_last else ""
            if is_open and fresh and appeared_at is None:
                appeared_at = secs()
                out["appeared_in_s"] = appeared_at
                out["first_is_inject"] = _near(api_first, moment, tol_s)   # alarm was NEW
                out["last_is_fresh"] = _near(api_last, moment, tol_s)       # re-triggered now
                # "time OK" = OmniOps registered it at the moment we injected,
                # whether it's a brand-new alarm (first~inject) or a pre-existing
                # one re-triggered now (last~inject).
                out["time_ok"] = out["first_is_inject"] or out["last_is_fresh"]
                pre = "" if out["first_is_inject"] else " (pre-existing: check by last)"
                print(f"  [t={secs():>4}s] cause:{_et(cause)} api:YES{rising}  "
                      f"time OK: {'YES' if out['time_ok'] else 'no'}{pre}  -> visible")
            else:
                print(f"  [t={secs():>4}s] cause:{_et(cause)} "
                      f"api:{'YES' if is_open else 'no'}{rising}")
            time.sleep(OMNIOPS_EVERY_S)

        # phase 2b: read the UI once and compare its timestamp with the API
        print(f"\n  [t={secs():>4}s] reading /alarms screen…")
        row = _read_ui_row(name)
        if row is None:
            out["ui_shown"] = False
            print("     alarm NOT found on screen")
        else:
            out["ui_shown"] = True
            ui_last = parse_ui_datetime(row.last)
            # API last is UTC; convert to local naive to compare with the UI value
            api_last_local = api_last.astimezone().replace(tzinfo=None) if api_last else None
            match = bool(ui_last and api_last_local and
                         abs((ui_last - api_last_local).total_seconds()) <= tol_s)
            out["ui_time_match"] = match
            print(f"     UI  first={row.first}  last={row.last}")
            print(f"     API last={api_last.astimezone():%d/%m/%Y, %H:%M:%S} (local)")
            print(f"     UI last ~ API last: {'YES' if match else 'no'}")

        # re-read the API right before clearing, so the freeze reference is fresh
        # (reading the UI above took time; last kept rising legitimately).
        _, _, api_last = _api_state(alarms_service, alarm_id)

        # phase 3: clear and verify freeze
        clear_moment = datetime.datetime.now(datetime.timezone.utc)
        last_before = api_last
        limpiar_estado()
        print(f"\n  [t={secs():>4}s] <<< CLEAR ({clear_moment.astimezone():%H:%M:%S} local). "
              "Verifying cause disappears and lastOccurred freezes…\n")
        time.sleep(OMNIOPS_EVERY_S * 2 + 2)
        cause = evaluar(reader)[0].get(alarm_id, (None, ""))[0]
        _, _, api_last_after = _api_state(alarms_service, alarm_id)
        out["cause_gone"] = (cause is False)
        out["frozen"] = bool(api_last_after and last_before and
                             (api_last_after - last_before).total_seconds() <= tol_s)
        print(f"  [t={secs():>4}s] cause:{_et(cause)} (gone: {'YES' if out['cause_gone'] else 'no'})  "
              f"last={api_last_after.astimezone():%H:%M:%S} "
              f"(frozen: {'YES' if out['frozen'] else 'no'})")
    finally:
        limpiar_estado()
        if own_reader:
            reader.close()

    # summary
    print("\n=== SCENE RESULT ===")
    print(f"  alarm {alarm_id} ({name})")
    when = ("first ~ inject" if out.get("first_is_inject")
            else "last ~ inject (pre-existing alarm)")
    print(f"  appeared in API : {out.get('appeared_in_s', '—')}s  "
          f"(registered at inject time: {'YES' if out.get('time_ok') else 'no'} — {when})")
    print(f"  shown on screen : {'YES' if out.get('ui_shown') else 'no'}  "
          f"(UI time ~ API time: {'YES' if out.get('ui_time_match') else 'no'})")
    print(f"  after clear     : cause gone: {'YES' if out.get('cause_gone') else 'no'}  "
          f"| lastOccurred frozen: {'YES' if out.get('frozen') else 'no'}")
    return out


def run_ui_only(alarm_id, at=0, wait_s=25, reader=None, tol_s=TOL_S):
    """Inject an alarm and verify it on the /alarms SCREEN only — no API.

    Reads the row by alarm name and checks its timestamps (from the UI table):
      - last occurred must be fresh (~ injection moment) -> our injection reached
        the screen (works whether the alarm is new or pre-existing).
      - first occurred fresh too -> the alarm is NEW (created now); otherwise it
        already existed and was re-triggered.
    Cleans up the injection at the end.
    """
    from framework_ui.pages.alarms_events.components.alarms_table import parse_ui_datetime

    own_reader = reader is None
    if own_reader:
        reader = LectorModbus()
        reader.leer_registro(cat.ADDR["evt1_802"])

    name = cat.BY_RULE_ID.get(alarm_id, {}).get("name", f"rule {alarm_id}")
    out = {"alarm_id": alarm_id, "name": name}
    try:
        if at:
            print(f"Firing in {at}s…")
            time.sleep(at)
        moment = datetime.datetime.now()          # local, to compare with UI (local)
        guardar_estado([alarm_id])
        print(f"[{moment:%H:%M:%S}] injected {alarm_id} ({name}). "
              f"Waiting {wait_s}s for OmniOps, then reading the screen…")
        time.sleep(wait_s)

        row = _read_ui_row(name)
        if row is None:
            out["ui_shown"] = False
            print(f"\n  Alarm '{name}' NOT found on the /alarms screen.")
        else:
            out["ui_shown"] = True
            ui_first = parse_ui_datetime(row.first)
            ui_last = parse_ui_datetime(row.last)
            fresh_last = bool(ui_last and abs((ui_last - moment).total_seconds()) <= tol_s
                              or (ui_last and ui_last >= moment - datetime.timedelta(seconds=tol_s)))
            fresh_first = bool(ui_first and ui_first >= moment - datetime.timedelta(seconds=tol_s))
            out["last_fresh"] = fresh_last
            out["is_new"] = fresh_first
            print(f"\n  Screen row: {name}  ({row.device})")
            print(f"    first occurred: {row.first}   ({'NEW alarm' if fresh_first else 'pre-existing'})")
            print(f"    last occurred : {row.last}   (fresh: {'YES' if fresh_last else 'no'})")
    finally:
        limpiar_estado()
        if own_reader:
            reader.close()

    print("\n=== UI-ONLY RESULT ===")
    ok = out.get("ui_shown") and out.get("last_fresh")
    print(f"  alarm {alarm_id} ({name})")
    print(f"  shown on screen     : {'YES' if out.get('ui_shown') else 'no'}")
    print(f"  last occurred fresh : {'YES' if out.get('last_fresh') else 'no'}  "
          f"(proves our injection reached the UI)")
    print(f"  new alarm (first fresh): {'YES' if out.get('is_new') else 'no'}")
    print(f"  -> {'PASS' if ok else 'FAIL'}")
    return out


def _et(cause):
    return {True: "YES", False: "no ", None: "n/a"}[cause]


def _live_line(res, ids):
    now = datetime.datetime.now().strftime("%H:%M:%S")
    parts = [f"ID{r} cause:{_et(res[r].cause)} api:{'YES' if res[r].in_api else 'no'} "
             f"{res[r].verdict}" for r in ids]
    print("  [" + now + "] " + "  |  ".join(parts))


def _print(results):
    print("\n=== RESULT ===")
    for r in results:
        ts = f" last={r.last.astimezone():%H:%M:%S}" if r.last else ""
        extra = ""
        if r.appeared_in_s is not None:
            extra = f"  (appeared in {r.appeared_in_s}s, {'time OK' if r.time_ok else 'time X'})"
        if r.ui_shown is not None:
            extra += f"  ui:{'YES' if r.ui_shown else 'no'}"
        print(f"  ID {r.rule_id:2} {r.name:26} cause:{_et(r.cause)} "
              f"api:{'YES' if r.in_api else 'no'}{ts}  -> {r.verdict}{extra}")
    fail = [r.rule_id for r in results if not r.ok]
    print(f"\n  {'FAILING: ' + str(fail) if fail else 'All OK'}")


def _parse_args(args):
    ids, at, hasta, live, skip = [], 0, 0, "--vivo" in args or "--live" in args, set()
    with_ui = "--with-ui" in args or "--con-ui" in args
    ui_only = "--ui-only" in args
    severity = subsystem = None
    for j, a in enumerate(args):
        if a == "--at" and j + 1 < len(args):
            at = int(args[j + 1]); skip.add(j + 1)
        elif a == "--hasta" and j + 1 < len(args):
            hasta = int(args[j + 1]); skip.add(j + 1)
        elif a == "--severity" and j + 1 < len(args):
            severity = args[j + 1]; skip.add(j + 1)
        elif a == "--subsystem" and j + 1 < len(args):
            subsystem = args[j + 1]; skip.add(j + 1)
    for j, a in enumerate(args):
        if j not in skip and not a.startswith("--") and a.isdigit():
            ids.append(int(a))
    # filters: expand to catalog rule_ids
    if "--criticals" in args or "--criticas" in args:
        ids += cat.rule_ids_by_severity("Critical")
    if severity:
        ids += cat.rule_ids_by_severity(severity)
    if subsystem:
        ids += cat.rule_ids_by_subsystem(subsystem)
    return sorted(set(ids)), at, hasta, live, with_ui, ui_only


if __name__ == "__main__":
    ids, at, hasta, live, with_ui, ui_only = _parse_args(sys.argv[1:])
    if not ids:
        print("Usage: python -m tools.probar <id> [<id> ...] [options]\n"
              "  Options:\n"
              "    --at N --hasta M   timed scene (fire at N, clear at M)\n"
              "    --live             show live progress\n"
              "    --with-ui          also verify it shows on the /alarms screen\n"
              "    --ui-only          verify ONLY on the screen (no API), by name + fresh timestamp\n"
              "    --criticals        test all injectable critical alarms\n"
              "    --severity X       test alarms with severity X (e.g. Critical, Major)\n"
              "    --subsystem X      test alarms of subsystem X (e.g. battery, pcs)\n"
              "  e.g.: python -m tools.probar 16 --ui-only\n"
              "        python -m tools.probar 16 --at 10 --hasta 30 --live")
        sys.exit(1)

    if ui_only:                            # inject -> verify on screen only (no API)
        try:
            out = run_ui_only(ids[0], at=at)
        except Exception as e:
            print(f"\nCould not run: {e}\nIs the chain up? (sim+proxy+edge) and OmniOps.")
            sys.exit(1)
        sys.exit(0 if (out.get("ui_shown") and out.get("last_fresh")) else 1)

    service = AlarmsService(ApiClient(BASE_URL))
    if hasta:                              # scene mode: --at ... --hasta ...
        try:
            out = run_scene(ids[0], service, at=at or 5, until=hasta)
        except Exception as e:
            print(f"\nCould not run scene: {e}\nIs the chain up? (sim+proxy+edge) and OmniOps.")
            sys.exit(1)
        ok = (out.get("ui_shown") and out.get("time_ok") and
              out.get("cause_gone") and out.get("frozen"))
        sys.exit(0 if ok else 1)

    print(f"Testing alarms {ids}…")
    try:
        results = verify_alarms(ids, service, at=at, live=live, with_ui=with_ui)
    except Exception as e:
        print(f"\nCould not run: {e}\nIs the chain up? (sim+proxy+edge) and OmniOps.")
        sys.exit(1)
    _print(results)
    sys.exit(0 if all(r.ok for r in results) else 1)
