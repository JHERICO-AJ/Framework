"""
diagnostico_signalr.py — ¿el número de la pantalla se actualiza solo (SignalR)?

Abre el dashboard con Playwright, y durante ~20s lee el valor SIN recargar,
para ver si cambia por su cuenta (señal de que SignalR está actualizando en vivo).

Correr:  python diagnostico_signalr.py
"""

import time

from framework_ui.pages.monitoring.monitoring_page import MonitoringPage

DURACION_S = 20

print("Abriendo navegador (visible) y logueando...")
ui = UiSession(headless=False)   # visible, para que veas la página
print(f"Listo. Miro el valor durante {DURACION_S}s SIN recargar...\n")

valores = []
t0 = time.time()
try:
    while time.time() - t0 < DURACION_S:
        val, txt = ui.read()          # lectura directa, sin recargar
        marca = time.strftime("%H:%M:%S")
        print(f"  [{marca}]  {txt}")
        valores.append(val)
        time.sleep(2)
finally:
    distintos = len(set(v for v in valores if v is not None))
    print("\n=== DIAGNÓSTICO ===")
    if distintos > 1:
        print(f"El valor CAMBIÓ solo ({distintos} valores distintos).")
        print("=> SignalR SÍ actualiza la pantalla en vivo. Podemos ir sin recargar.")
    else:
        print("El valor NO cambió (quedó fijo).")
        print("=> SignalR no está actualizando este navegador. Habría que ver por qué,")
        print("   o seguir con el modo recargar (que igual valida bien el dato).")
    ui.close()
