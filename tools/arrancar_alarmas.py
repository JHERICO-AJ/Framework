"""
arrancar_alarmas.py — UN comando que levanta todo para probar alarmas, en orden:

    simulador real (5021)  ->  proxy (5020)  ->  edge (MODBUS_PORT=5020)  ->  OmniOps

Espera a que cada puerto esté listo antes del siguiente, y al cortar con Ctrl+C
BAJA el simulador y el edge que levantó (el proxy corre en un hilo y muere con
este proceso). Docker + OmniOps los prendés vos aparte.

Las rutas del repo del simulador salen de config.py (SIM_REPO_DIR / SIM_SCRIPT /
EDGE_SCRIPT / EDGE_CONFIG). Ajustalas ahí si tu repo está en otro lado.

Correr:  python -m tools.arrancar_alarmas
"""

from __future__ import annotations

import os
import subprocess
import sys
import threading
import time

from config import (SIM_HOST, SIM_PORT, SIM_REAL_HOST, SIM_REAL_PORT, SIM_TICK_S,
                    SIM_REPO_DIR, SIM_SCRIPT, EDGE_SCRIPT, EDGE_CONFIG)
from tools.sim_launcher import puerto_abierto, esperar_puerto

procesos = []       # [(nombre, Popen)]


def _lanzar(nombre, cmd, cwd, env=None):
    print(f"→ {nombre}")
    p = subprocess.Popen(cmd, cwd=cwd, env=env)
    procesos.append((nombre, p))
    return p


def bajar_todo():
    for nombre, p in reversed(procesos):
        if p.poll() is None:
            print(f"  ⏹ bajando {nombre}…")
            p.terminate()
    for _, p in reversed(procesos):
        try:
            p.wait(timeout=8)
        except Exception:
            p.kill()


def main():
    # 0) chequear rutas del otro repo
    faltan = [(p, q) for p, q in (
        (SIM_SCRIPT, "simulador"), (EDGE_SCRIPT, "edge"),
        (EDGE_CONFIG, "config del sitio")) if not os.path.exists(p)]
    if faltan:
        print("No encuentro estos archivos del repo del simulador:")
        for p, q in faltan:
            print(f"  - {q}: {p}")
        print("\nAjustá SIM_REPO_DIR en config.py para que apunte a tu omniops-bess-edge.")
        return

    try:
        # 1) simulador real en 5021
        if puerto_abierto(SIM_REAL_HOST, SIM_REAL_PORT):
            print(f"Ya hay algo escuchando en {SIM_REAL_PORT}; no levanto el sim de nuevo.")
        else:
            _lanzar(f"simulador ({SIM_REAL_PORT})",
                    [sys.executable, SIM_SCRIPT, SIM_REAL_HOST,
                     str(SIM_REAL_PORT), str(SIM_TICK_S)], cwd=SIM_REPO_DIR)
            if not esperar_puerto(SIM_REAL_HOST, SIM_REAL_PORT, timeout=30):
                print("El simulador no abrió el 5021.")
                bajar_todo()
                return

        # 2) proxy en 5020 (en un hilo; muere con este proceso)
        from tools.sim_proxy import run as run_proxy
        threading.Thread(target=run_proxy, daemon=True).start()
        if not esperar_puerto(SIM_HOST, SIM_PORT, timeout=15):
            print("El proxy no abrió el 5020.")
            bajar_todo()
            return

        # 3) edge apuntando al proxy (5020)
        env = os.environ.copy()
        env["MODBUS_HOST"] = SIM_HOST
        env["MODBUS_PORT"] = str(SIM_PORT)
        _lanzar(f"edge (MODBUS_PORT={SIM_PORT})",
                [sys.executable, EDGE_SCRIPT, EDGE_CONFIG],
                cwd=SIM_REPO_DIR, env=env)

        print("\n Todo arriba:  sim(5021) → proxy(5020) → edge → OmniOps")
        print(" (prendé Docker + OmniOps aparte si no lo hiciste)\n")
        print(" Inyectar:  python -m alarms.inject <id>     (apagar: --clear)")
        print(" Monitor :  python -m monitors.watch_alarms")
        print("\n Ctrl+C para bajar todo.\n")

        while True:
            for nombre, p in procesos:
                if p.poll() is not None:
                    print(f"\n⚠ '{nombre}' terminó solo (código {p.returncode}). "
                          "Bajo el resto.")
                    bajar_todo()
                    return
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nBajando todo…")
        bajar_todo()
        print("Listo.")


if __name__ == "__main__":
    main()
