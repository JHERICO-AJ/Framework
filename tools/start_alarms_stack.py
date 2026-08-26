"""
start_alarms_stack.py — ONE command that brings everything up to test alarms, in order:

    real simulator (5021)  ->  proxy (5020)  ->  edge (MODBUS_PORT=5020)  ->  OmniOps

Waits for each port to be ready before the next one, and when you interrupt
with Ctrl+C it BRINGS DOWN the simulator and the edge it started (the proxy
runs in a thread and dies with this process). You start Docker + OmniOps
separately.

The simulator repo's paths come from settings.py (SIM_REPO_DIR / SIM_SCRIPT /
EDGE_SCRIPT / EDGE_CONFIG). Adjust them there if your repo is somewhere else.

Run:  python -m tools.start_alarms_stack
"""

from __future__ import annotations

import os
import subprocess
import sys
import threading
import time

from shared.config.settings import (SIM_HOST, SIM_PORT, SIM_REAL_HOST, SIM_REAL_PORT, SIM_TICK_S,
                    SIM_REPO_DIR, SIM_SCRIPT, EDGE_SCRIPT, EDGE_CONFIG, EDGE_PYTHON)
from tools.sim_launcher import port_open, wait_for_port

processes = []       # [(name, Popen)]

# the sim and the edge run with the edge repo's Python (it has its own deps)
PY = EDGE_PYTHON if os.path.exists(EDGE_PYTHON) else sys.executable


def _launch(name, cmd, cwd, env=None):
    print(f"→ {name}")
    p = subprocess.Popen(cmd, cwd=cwd, env=env)
    processes.append((name, p))
    return p


def shutdown_all():
    for name, p in reversed(processes):
        if p.poll() is None:
            print(f"  ⏹ stopping {name}…")
            p.terminate()
    for _, p in reversed(processes):
        try:
            p.wait(timeout=8)
        except Exception:
            p.kill()


def main():
    # 0) check the other repo's paths
    missing = [(p, q) for p, q in (
        (SIM_SCRIPT, "simulator"), (EDGE_SCRIPT, "edge"),
        (EDGE_CONFIG, "site config")) if not os.path.exists(p)]
    if missing:
        print("Can't find these files from the simulator repo:")
        for p, q in missing:
            print(f"  - {q}: {p}")
        print("\nAdjust SIM_REPO_DIR in settings.py to point at your omniops-bess-edge.")
        return

    try:
        # 1) real simulator on 5021
        if port_open(SIM_REAL_HOST, SIM_REAL_PORT):
            print(f"Something is already listening on {SIM_REAL_PORT}; not starting the sim again.")
        else:
            _launch(f"simulator ({SIM_REAL_PORT})",
                    [PY, SIM_SCRIPT, SIM_REAL_HOST,
                     str(SIM_REAL_PORT), str(SIM_TICK_S)], cwd=SIM_REPO_DIR)
            if not wait_for_port(SIM_REAL_HOST, SIM_REAL_PORT, timeout=30):
                print("The simulator didn't open 5021.")
                shutdown_all()
                return

        # 2) proxy on 5020 (in a thread; dies with this process)
        from tools.sim_proxy import run as run_proxy
        threading.Thread(target=run_proxy, daemon=True).start()
        if not wait_for_port(SIM_HOST, SIM_PORT, timeout=15):
            print("The proxy didn't open 5020.")
            shutdown_all()
            return

        # 3) edge pointing at the proxy (5020)
        env = os.environ.copy()
        env["MODBUS_HOST"] = SIM_HOST
        env["MODBUS_PORT"] = str(SIM_PORT)
        _launch(f"edge (MODBUS_PORT={SIM_PORT})",
                [PY, EDGE_SCRIPT, EDGE_CONFIG],
                cwd=SIM_REPO_DIR, env=env)

        print("\n Everything up:  sim(5021) → proxy(5020) → edge → OmniOps")
        print(" (start Docker + OmniOps separately if you haven't)\n")
        print(" Inject :  python -m alarms.inject <id>     (clear: --clear)")
        print(" Monitor:  python -m monitors.watch_alarms")
        print("\n Ctrl+C to bring everything down.\n")

        while True:
            for name, p in processes:
                if p.poll() is not None:
                    print(f"\n⚠ '{name}' exited on its own (code {p.returncode}). "
                          "Bringing down the rest.")
                    shutdown_all()
                    return
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nBringing everything down…")
        shutdown_all()
        print("Done.")


if __name__ == "__main__":
    main()
