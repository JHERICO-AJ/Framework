"""
ui_reader.py — lee el número que se MUESTRA en la pantalla (con Playwright).

Cierra la última capa de validación: API -> pantalla. Lee "Actual PCS Power"
tal como lo ve el usuario (con un decimal y en kW) para compararlo contra la API.

Login por ahora: email/contraseña (lee omniops_login.txt, el mismo de siempre).

Requiere:  pip install playwright   y luego   playwright install chromium
SOLO LEE la pantalla; no hace clics que cambien nada.
"""

from __future__ import annotations

import re

MONITORING_URL = "http://localhost:5173/monitoring?timeRange=24h"
LOGIN_URL = "http://localhost:5173/login"   # ajustar si la pantalla de login es otra


def _load_creds(path="omniops_login.txt"):
    creds = {}
    for line in open(path, encoding="utf-8"):
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            creds[k.strip().lower()] = v.strip()
    return creds


def parse_kw(texto):
    """De un texto tipo '-2373.2 kW' saca el número. Sin dato (N/A, —) -> None."""
    if texto is None:
        return None
    t = texto.strip().lower()
    if t in ("n/a", "na", "—", "-", "", "sin dato"):
        return None
    m = re.search(r"-?\d[\d,]*\.?\d*", texto.replace(",", ""))
    return float(m.group()) if m else None


def leer_ui_pcs_power(headless=True):
    """Abre el dashboard, se loguea, y devuelve el valor de 'Actual PCS Power' en kW."""
    from playwright.sync_api import sync_playwright

    creds = _load_creds()
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        page = browser.new_page()

        # 1) login por email/contraseña (campos por su id: #loginUser / #loginPassword)
        page.goto(LOGIN_URL)
        page.locator("#loginUser").fill(creds["email"])
        page.locator("#loginPassword").fill(creds["password"])
        page.locator("button.login-submit-button").click()

        # 2) esperar a que el login procese y luego ir al dashboard
        page.wait_for_load_state("networkidle", timeout=15000)
        page.goto(MONITORING_URL)

        # 3) ubicar el número por su rótulo "Actual PCS Power"
        #    (el device-card que contiene ese título, y dentro su metric-value)
        card = page.locator(".device-card", has_text="Actual PCS Power")
        card.wait_for(timeout=15000)
        texto = card.locator(".metric-value").inner_text()

        browser.close()
        return parse_kw(texto), texto



class UiSession:
    """Sesión de navegador persistente: se loguea UNA vez y lee muchas veces."""

    def __init__(self, headless=True):
        from playwright.sync_api import sync_playwright
        self._pw = sync_playwright().start()
        self.browser = self._pw.chromium.launch(headless=headless)
        self.page = self.browser.new_page()
        self._login()
        self._entrar_al_dashboard()

    def _entrar_al_dashboard(self, intentos=5):
        """Va al dashboard y confirma que entró; si rebota al login, reintenta
        (le da a la app el respiro para dejar la sesión lista)."""
        import time as _t
        for i in range(intentos):
            self.page.goto(MONITORING_URL)
            self.page.wait_for_load_state("networkidle", timeout=15000)
            if "login" not in (self.page.url or ""):
                try:
                    self.page.locator(".device-card",
                                      has_text="Actual PCS Power").wait_for(timeout=10000)
                    return
                except Exception:
                    pass
            _t.sleep(2)          # respiro y reintento
            if "login" in (self.page.url or ""):
                self._login()
        raise RuntimeError("no pude entrar al dashboard tras varios intentos")

    def _login(self):
        creds = _load_creds()
        self.page.goto(LOGIN_URL)
        self.page.locator("#loginUser").fill(creds["email"])
        self.page.locator("#loginPassword").fill(creds["password"])
        self.page.locator("button.login-submit-button").click()
        self.page.wait_for_load_state("networkidle", timeout=15000)

    def _leer_dom(self):
        card = self.page.locator(".device-card", has_text="Actual PCS Power")
        card.wait_for(timeout=15000)
        texto = card.locator(".metric-value").inner_text()
        return parse_kw(texto), texto

    def _en_login(self):
        return "login" in (self.page.url or "")

    def _asegurar_sesion(self):
        """Si OmniOps me pateó al login (sesión vencida), me re-logueo solo,
        igual que auth.py hacía ante un 401 en la API."""
        if self._en_login():
            self._login()
            self._entrar_al_dashboard()

    def read(self):
        """Lee el valor recargando la página para traer el dato fresco.
        Si la sesión venció, se re-loguea solo y reintenta."""
        try:
            self.page.reload()
            self.page.wait_for_load_state("networkidle", timeout=15000)
            if self._en_login():
                self._asegurar_sesion()
            return self._leer_dom()
        except Exception:
            self._asegurar_sesion()
            return self._leer_dom()

    def read_fresh(self, esperar_cambio_s=8.0):
        """Lee el DOM esperando a que el valor CAMBIE respecto al anterior,
        señal de que SignalR actualizó en vivo. Si no cambia, devuelve lo último."""
        import time as _t
        val0, txt0 = self._leer_dom()
        t0 = _t.time()
        while _t.time() - t0 < esperar_cambio_s:
            _t.sleep(0.4)
            val, txt = self._leer_dom()
            if val != val0:
                return val, txt, True     # cambió: SignalR está vivo
        return val0, txt0, False          # no cambió en el tiempo dado

    def close(self):
        for paso in (self.browser.close, self._pw.stop):
            try:
                paso()
            except Exception:
                pass


if __name__ == "__main__":
    # prueba: parseo del texto, sin abrir navegador
    for t in ["-2373.2 kW", "5043.0 kW", "  1,200.5 kW ", "—"]:
        print(f"'{t}' -> {parse_kw(t)}")
