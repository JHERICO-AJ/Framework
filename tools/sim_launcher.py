"""
sim_launcher.py — starts (and stops) the simulator from the framework.

Launches the simulator as a subprocess (the same command you'd run by hand)
and waits for the Modbus port to accept connections before continuing, so you
don't start monitoring "into thin air".

Adjust in settings.py: SIM_REPO_DIR (path to the simulator repo), SIM_LAUNCH_CMD,
SIM_TICK_S. Uses SITE_ID / SIM_HOST / SIM_PORT already in settings.

Direct use (starts it and leaves it running until Ctrl+C):
    python sim_launcher.py

Use from code:
    from sim_launcher import Simulator
    with Simulator() as sim:        # starts it and stops it on exit
        ...                          # run the monitors here

Test the port-waiting logic (without the simulator):
    python sim_launcher.py --self-check
"""

from __future__ import annotations

import socket
import subprocess
import sys
import time

from shared.config.settings import (SIM_HOST, SIM_PORT, SITE_ID,
                    SIM_REPO_DIR, SIM_LAUNCH_CMD, SIM_TICK_S)


def port_open(host, port, timeout=0.5):
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def wait_for_port(host, port, timeout=30.0, every=0.5):
    """Waits until the port accepts connections. True if it succeeded in time."""
    t0 = time.time()
    while time.time() - t0 < timeout:
        if port_open(host, port):
            return True
        time.sleep(every)
    return False


class Simulator:
    def __init__(self, site=SITE_ID, port=SIM_PORT, tick=SIM_TICK_S, host=SIM_HOST):
        self.site, self.port, self.tick, self.host = site, port, tick, host
        self.proc = None

    def start(self, wait=True, timeout=30.0):
        if port_open(self.host, self.port):
            print(f"The simulator is already listening on {self.host}:{self.port} "
                  "(not starting it again).")
            return self
        cmd = [str(p).format(site=self.site, port=self.port, tick=self.tick)
               for p in SIM_LAUNCH_CMD]
        print("Starting simulator:", " ".join(cmd), f"(cwd={SIM_REPO_DIR})")
        try:
            self.proc = subprocess.Popen(cmd, cwd=SIM_REPO_DIR)
        except FileNotFoundError as e:
            raise FileNotFoundError(
                f"couldn't run the simulator ({e}). Check SIM_REPO_DIR and "
                "SIM_LAUNCH_CMD in settings.py.")
        if wait and not wait_for_port(self.host, self.port, timeout):
            self.stop()
            raise TimeoutError(
                f"the simulator didn't open {self.host}:{self.port} in {timeout}s.")
        print(f"Simulator ready at {self.host}:{self.port}.")
        return self

    def stop(self):
        if self.proc and self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=5)
            except Exception:
                self.proc.kill()
        self.proc = None

    def __enter__(self):
        return self.start()

    def __exit__(self, *exc):
        self.stop()


def _self_check():
    print("(port-waiting test — with a fake local socket)\n")
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("127.0.0.1", 0))
    srv.listen(1)
    port = srv.getsockname()[1]
    ok_open = port_open("127.0.0.1", port)
    ok_wait = wait_for_port("127.0.0.1", port, timeout=2.0)
    srv.close()
    ok_closed = not port_open("127.0.0.1", port)
    print(f"  open port detected     : {'OK' if ok_open else 'FAIL'}")
    print(f"  wait_for_port finds it : {'OK' if ok_wait else 'FAIL'}")
    print(f"  closed port detected   : {'OK' if ok_closed else 'FAIL'}")
    all_ok = ok_open and ok_wait and ok_closed
    print("\n=> " + ("OK ✓" if all_ok else "FAIL ✗"))
    return all_ok


if __name__ == "__main__":
    if "--self-check" in sys.argv:
        sys.exit(0 if _self_check() else 1)

    sim = Simulator().start()
    print("Simulator running. Ctrl+C to stop it.")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nStopping simulator…")
        sim.stop()
