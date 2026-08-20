"""
diagnostico_sesion.py — ¿cuánto dura la sesión del navegador antes de expirar?

Se loguea, va al dashboard, y cada 2s dice en qué página está (dashboard vs login).
Así vemos si la sesión se vence enseguida y por qué el monitor perdía la pantalla.

Correr:  python diagnostico_sesion.py
"""

import re
import time

from playwright.sync_api import sync_playwright
from framework_ui.pages.monitoring.monitoring_page import MonitoringPage

creds = _load_creds()
pw = sync_playwright().start()
browser = pw.chromium.launch(headless=False)
page = browser.new_page()

print("Login...")
page.goto(LOGIN_URL)
page.locator("#loginUser").fill(creds["email"])
page.locator("#loginPassword").fill(creds["password"])
page.locator("button.login-submit-button").click()
page.wait_for_load_state("networkidle", timeout=15000)
print(f"Después del login estoy en: {page.url}")

page.goto(MONITORING_URL)
print("Fui al dashboard. Vigilando la URL cada 2s...\n")

t0 = time.time()
try:
    for _ in range(30):   # ~60s
        url = page.url
        seg = time.time() - t0
        en_login = "login" in url
        estado = "EN LOGIN (sesión perdida)" if en_login else "en dashboard OK"
        print(f"  {seg:5.0f}s  {estado}   ({url})")
        if en_login:
            print("\n=> La sesión se venció / no se mantuvo. Ese es el problema a resolver.")
            break
        time.sleep(2)
    else:
        print("\n=> La sesión se mantuvo estable. El problema era otro.")
finally:
    for paso in (browser.close, pw.stop):
        try:
            paso()
        except Exception:
            pass
