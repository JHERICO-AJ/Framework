"""
sniff_alarms_api.py — descubrí QUÉ API de alarmas usa OmniOps, de verdad.

Abre el dashboard logueado (reusa el POM) y escucha el tráfico de red: captura
las llamadas cuya URL menciona "alarm" y vuelca la URL completa (con sus query
params: SiteId, Status, FromDate/ToDate…) y el JSON de respuesta, para fijar los
nombres reales de los campos (alarmRuleId, severity, subsystem, firstOccurred,
lastOccurred, status…).

Con esto después ajustamos check_alarms.py a los nombres exactos.

SOLO ESCUCHA: no hace clics que cambien nada.

Correr:  python sniff_alarms_api.py
"""

from __future__ import annotations

import json
import time

from ui.ui_reader import UiSession


def _interesa(url):
    u = url.lower()
    return "alarm" in u or "alert" in u or "/events/" in u


def sniff(segundos=8):
    capturas = []

    def on_response(resp):
        try:
            if _interesa(resp.url):
                cuerpo = None
                try:
                    cuerpo = resp.text()
                except Exception:
                    pass
                capturas.append((resp.request.method, resp.url, resp.status, cuerpo))
        except Exception:
            pass

    print("Abriendo dashboard y escuchando la red…")
    ui = UiSession(headless=False)
    ui.page.on("response", on_response)
    try:
        ui.monitoring.recargar()      # forzar que el dashboard pida las alarmas
        time.sleep(segundos)
    finally:
        ui.close()

    if not capturas:
        print("\nNo capté ninguna llamada con 'alarm'/'alert'/'/events/' en la URL.\n"
              "¿La tabla de alarmas está visible en el dashboard? Probá subir el "
              "tiempo de espera o abrir la vista de alarmas.")
        return

    print(f"\nCapturé {len(capturas)} llamada(s):")
    for met, url, st, cuerpo in capturas:
        print("\n" + "=" * 70)
        print(f"{met} {url}")
        print(f"status: {st}")
        if cuerpo:
            try:
                data = json.loads(cuerpo)
                muestra = json.dumps(data, indent=2, ensure_ascii=False)
                print("json (recortado a 1800 chars):")
                print(muestra[:1800])
            except Exception:
                print("body (texto, recortado):", cuerpo[:600])


if __name__ == "__main__":
    sniff()
