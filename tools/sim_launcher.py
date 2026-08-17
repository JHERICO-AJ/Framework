"""
sim_launcher.py — levanta (y baja) el simulador desde el framework.

Lanza el simulador como un subproceso (el mismo comando que corrías a mano) y
espera a que el puerto Modbus esté aceptando conexiones antes de seguir, así no
arrancás a monitorear "en el aire".

Ajustá en config.py: SIM_REPO_DIR (ruta del repo del simulador), SIM_LAUNCH_CMD,
SIM_TICK_S. Usa SITE_ID / SIM_HOST / SIM_PORT que ya están en config.

Uso directo (levanta y deja corriendo hasta Ctrl+C):
    python sim_launcher.py

Uso desde código:
    from sim_launcher import Simulador
    with Simulador() as sim:        # lo levanta y lo baja al salir
        ...                          # correr los monitores acá

Probar la lógica de espera de puerto (sin el simulador):
    python sim_launcher.py --self-check
"""

from __future__ import annotations

import socket
import subprocess
import sys
import time

from config import (SIM_HOST, SIM_PORT, SITE_ID,
                    SIM_REPO_DIR, SIM_LAUNCH_CMD, SIM_TICK_S)


def puerto_abierto(host, port, timeout=0.5):
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def esperar_puerto(host, port, timeout=30.0, cada=0.5):
    """Espera hasta que el puerto acepte conexiones. True si lo logró a tiempo."""
    t0 = time.time()
    while time.time() - t0 < timeout:
        if puerto_abierto(host, port):
            return True
        time.sleep(cada)
    return False


class Simulador:
    def __init__(self, site=SITE_ID, port=SIM_PORT, tick=SIM_TICK_S, host=SIM_HOST):
        self.site, self.port, self.tick, self.host = site, port, tick, host
        self.proc = None

    def start(self, esperar=True, timeout=30.0):
        if puerto_abierto(self.host, self.port):
            print(f"El simulador ya está escuchando en {self.host}:{self.port} "
                  "(no lo levanto de nuevo).")
            return self
        cmd = [str(p).format(site=self.site, port=self.port, tick=self.tick)
               for p in SIM_LAUNCH_CMD]
        print("Levantando simulador:", " ".join(cmd), f"(cwd={SIM_REPO_DIR})")
        try:
            self.proc = subprocess.Popen(cmd, cwd=SIM_REPO_DIR)
        except FileNotFoundError as e:
            raise FileNotFoundError(
                f"no pude ejecutar el simulador ({e}). Revisá SIM_REPO_DIR y "
                "SIM_LAUNCH_CMD en config.py.")
        if esperar and not esperar_puerto(self.host, self.port, timeout):
            self.stop()
            raise TimeoutError(
                f"el simulador no abrió {self.host}:{self.port} en {timeout}s.")
        print(f"Simulador listo en {self.host}:{self.port}.")
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
    print("(prueba de espera de puerto — con un socket local de mentira)\n")
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("127.0.0.1", 0))
    srv.listen(1)
    port = srv.getsockname()[1]
    ok_open = puerto_abierto("127.0.0.1", port)
    ok_wait = esperar_puerto("127.0.0.1", port, timeout=2.0)
    srv.close()
    ok_closed = not puerto_abierto("127.0.0.1", port)
    print(f"  puerto abierto detectado : {'OK' if ok_open else 'MAL'}")
    print(f"  esperar_puerto encuentra : {'OK' if ok_wait else 'MAL'}")
    print(f"  puerto cerrado detectado : {'OK' if ok_closed else 'MAL'}")
    todos = ok_open and ok_wait and ok_closed
    print("\n=> " + ("OK ✓" if todos else "MAL ✗"))
    return todos


if __name__ == "__main__":
    if "--self-check" in sys.argv:
        sys.exit(0 if _self_check() else 1)

    sim = Simulador().start()
    print("Simulador corriendo. Ctrl+C para bajarlo.")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nBajando simulador…")
        sim.stop()
