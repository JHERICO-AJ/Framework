"""
diagnostico_token.py — ¿dónde queda el token después del login, y sobrevive?

Se loguea y revisa dónde guarda la app el token (localStorage, sessionStorage,
cookies). Después navega al dashboard y vuelve a mirar, para ver si el token
sobrevivió o se perdió (que sería la causa de los 401).

Correr:  python diagnostico_token.py
"""

import json
import re
import time

from playwright.sync_api import sync_playwright
from ui_reader import _load_creds, LOGIN_URL, MONITORING_URL

PISTAS = ("token", "jwt", "auth", "bearer", "access", "session")


def es_interesante(clave, valor):
    txt = f"{clave} {valor}".lower()
    if any(p in txt for p in PISTAS):
        return True
    return isinstance(valor, str) and len(valor) > 40  # cadenas largas = posibles tokens


def volcar_almacen(page, momento):
    ls = page.evaluate("() => Object.entries(window.localStorage)")
    ss = page.evaluate("() => Object.entries(window.sessionStorage)")
    cookies = page.context.cookies()
    print(f"\n----- {momento} (url: {page.url}) -----")
    print("localStorage:")
    for k, v in ls:
        marca = "  <-- posible token" if es_interesante(k, v) else ""
        print(f"    {k} = {str(v)[:60]}{marca}")
    print("sessionStorage:")
    for k, v in ss:
        marca = "  <-- posible token" if es_interesante(k, v) else ""
        print(f"    {k} = {str(v)[:60]}{marca}")
    print("cookies:")
    for c in cookies:
        marca = "  <-- posible token" if es_interesante(c['name'], c.get('value','')) else ""
        print(f"    {c['name']} = {str(c.get('value',''))[:60]}{marca}")


pw = sync_playwright().start()
browser = pw.chromium.launch(headless=False)
page = browser.new_page()

creds = _load_creds()
print("Login...")
page.goto(LOGIN_URL)
page.locator("#loginUser").fill(creds["email"])
page.locator("#loginPassword").fill(creds["password"])
page.locator("button.login-submit-button").click()
page.wait_for_load_state("networkidle", timeout=15000)
time.sleep(2)   # dar tiempo a que guarde el token

volcar_almacen(page, "JUSTO DESPUÉS DEL LOGIN")

print("\nNavegando al dashboard...")
page.goto(MONITORING_URL)
page.wait_for_load_state("networkidle", timeout=15000)
time.sleep(2)

volcar_almacen(page, "DESPUÉS DE IR AL DASHBOARD")
print(f"\n=> ¿Terminé en el dashboard o en login?  {page.url}")

for paso in (browser.close, pw.stop):
    try:
        paso()
    except Exception:
        pass
