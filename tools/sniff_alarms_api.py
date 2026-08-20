"""sniff_alarms_api — descubre la API de alarmas capturando el tráfico de red.
Abre /alarms logueado y vuelca las llamadas cuya URL menciona alarm/alert/events.
Herramienta de investigación (tools/). No es un test.
    python -m tools.sniff_alarms_api
"""
from __future__ import annotations

import json
import time

from shared.config.settings import BASE_URL, ALARMS_UI_PATH
from shared.config.credentials import load_credentials
from framework_ui.browser.browser_factory import BrowserFactory
from framework_ui.pages.auth.login_page import LoginPage


def _interesa(url):
    u = url.lower()
    return "alarm" in u or "alert" in u or "/events/" in u


def sniff(segundos=8):
    capturas = []
    creds = load_credentials()
    factory = BrowserFactory(headless=False)
    page = factory.__enter__()

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

    try:
        LoginPage(page).login(creds["email"], creds["password"])
        page.on("response", on_response)
        page.goto(BASE_URL + ALARMS_UI_PATH)
        time.sleep(segundos)
    finally:
        factory.__exit__(None, None, None)

    if not capturas:
        print("No capté llamadas con alarm/alert/events. ¿La tabla estaba visible?")
        return
    for met, url, st, cuerpo in capturas:
        print("\n" + "=" * 70)
        print(f"{met} {url}\nstatus: {st}")
        if cuerpo:
            try:
                print(json.dumps(json.loads(cuerpo), indent=2, ensure_ascii=False)[:1800])
            except Exception:
                print(cuerpo[:600])


if __name__ == "__main__":
    sniff()
