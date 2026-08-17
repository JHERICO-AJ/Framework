"""
diagnostico_websocket.py — ¿por qué SignalR no actualiza el navegador de Playwright?

Escucha, durante ~25s, lo que pasa por dentro del navegador:
  - WebSockets que se abren (SignalR usa WebSocket para el tiempo real)
  - errores en la consola del navegador
  - pedidos de red que fallan (sobre todo los que mencionan 'hub' o 'negotiate')

Con eso vemos si SignalR intenta conectar y falla, o ni lo intenta.

Correr:  python diagnostico_websocket.py
"""

import time

from playwright.sync_api import sync_playwright
from ui.ui_reader import _load_creds, LOGIN_URL, MONITORING_URL

eventos = {"ws": [], "console_err": [], "req_fail": []}

pw = sync_playwright().start()
browser = pw.chromium.launch(headless=False)
page = browser.new_page()

# --- espías ---
def on_ws(ws):
    eventos["ws"].append(ws.url)
    print(f"  [WebSocket ABIERTO] {ws.url}")
    ws.on("close", lambda: print(f"  [WebSocket CERRADO] {ws.url}"))
    ws.on("socketerror", lambda e: print(f"  [WebSocket ERROR] {ws.url}"))

page.on("websocket", on_ws)
page.on("console", lambda m: (eventos["console_err"].append(m.text)
         or print(f"  [CONSOLA {m.type}] {m.text[:160]}")) if m.type in ("error", "warning") else None)
page.on("requestfailed", lambda r: (eventos["req_fail"].append(r.url)
         or print(f"  [PEDIDO FALLÓ] {r.url}  ({r.failure})")))

# --- login + dashboard ---
creds = _load_creds()
print("Login...")
page.goto(LOGIN_URL)
page.locator("#loginUser").fill(creds["email"])
page.locator("#loginPassword").fill(creds["password"])
page.locator("button.login-submit-button").click()
page.wait_for_load_state("networkidle", timeout=15000)
for _ in range(5):
    page.goto(MONITORING_URL)
    page.wait_for_load_state("networkidle", timeout=15000)
    if "login" not in page.url:
        break
    time.sleep(2)

print(f"\nEn el dashboard ({page.url}). Escuchando 25s...\n")
time.sleep(25)

print("\n=== RESUMEN ===")
print(f"WebSockets abiertos : {len(eventos['ws'])}")
for u in eventos["ws"]:
    print(f"    {u}")
print(f"Errores de consola  : {len(eventos['console_err'])}")
print(f"Pedidos que fallaron: {len(eventos['req_fail'])}")
hub = [u for u in eventos["ws"] + eventos["req_fail"] if "hub" in u.lower() or "negotiate" in u.lower()]
print("\nRelacionado con SignalR (hub/negotiate):")
for u in hub:
    print(f"    {u}")
if not eventos["ws"]:
    print("\n=> No se abrió NINGÚN WebSocket. SignalR ni intentó conectar en este navegador.")
elif hub:
    print("\n=> SignalR intentó (hay hub/negotiate). Miralo arriba: puede haber fallado.")

for paso in (browser.close, pw.stop):
    try:
        paso()
    except Exception:
        pass
