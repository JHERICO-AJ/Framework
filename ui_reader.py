"""
ui_reader.py — capa PANTALLA (Playwright), ahora como FACHADA sobre el POM.

Los selectores ya no viven acá: están en pages/ (LoginPage, MonitoringPage).
Este archivo solo orquesta: abre el navegador una vez, se loguea y lee muchas
veces. watch_3capas.py sigue usando UiSession.read() igual que antes.

Requiere:  pip install playwright   y luego   playwright install chromium
SOLO LEE la pantalla; no hace clics que cambien nada.
"""

from __future__ import annotations

from config import HEADLESS
from pages.login_page import LoginPage
from pages.monitoring_page import MonitoringPage, MONITORING_URL, parse_kw

LOGIN_URL = LoginPage.URL


def _load_creds(path="omniops_login.txt"):
    creds = {}
    for line in open(path, encoding="utf-8"):
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            creds[k.strip().lower()] = v.strip()
    return creds


def leer_ui_pcs_power(headless=True):
    """Abre el dashboard, se loguea y devuelve 'Actual PCS Power' en kW (one-shot)."""
    from playwright.sync_api import sync_playwright

    creds = _load_creds()
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        context = browser.new_context(ignore_https_errors=True)  # cert dev del hub
        page = context.new_page()
        login = LoginPage(page)
        monitoring = MonitoringPage(page)
        login.login(creds["email"], creds["password"])
        monitoring.ir()
        result = monitoring.leer_pcs_power()
        browser.close()
        return result


class UiSession:
    """Sesión de navegador persistente: se loguea UNA vez y lee muchas veces."""

    def __init__(self, headless=HEADLESS, recargar=False):
        from playwright.sync_api import sync_playwright
        self._pw = sync_playwright().start()
        self.browser = self._pw.chromium.launch(headless=headless)
        # ignore_https_errors=True: el hub de SignalR (https://localhost:7187) usa
        # un certificado de desarrollo autofirmado que el Chromium automatizado no
        # confía -> el negotiate rebota con ERR_CERT_AUTHORITY_INVALID y SignalR no
        # conecta. Ignorando el error de cert, el WebSocket conecta y el dashboard
        # se actualiza SOLO -> ya no hace falta recargar en cada lectura.
        self.context = self.browser.new_context(ignore_https_errors=True)
        self.page = self.context.new_page()
        # recargar=False (por defecto): lee el DOM en vivo (SignalR lo actualiza).
        # recargar=True: vuelve al "modo recargar" (fallback si el tiempo real falla).
        self.recargar = recargar

        self._creds = _load_creds()
        self.login_page = LoginPage(self.page)
        self.monitoring = MonitoringPage(self.page)

        self._login()
        self._entrar_al_dashboard()

    # --- orquestación de sesión ---
    def _login(self):
        self.login_page.login(self._creds["email"], self._creds["password"])

    def _en_login(self):
        return self.monitoring.esta_en_login()

    def _entrar_al_dashboard(self, intentos=5):
        """Va al dashboard y confirma que entró; si rebota al login, reintenta."""
        import time as _t
        for i in range(intentos):
            self.monitoring.ir()
            if not self._en_login():
                try:
                    self.monitoring.esperar_card()
                    return
                except Exception:
                    pass
            _t.sleep(2)          # respiro y reintento
            if self._en_login():
                self._login()
        raise RuntimeError("no pude entrar al dashboard tras varios intentos")

    def _asegurar_sesion(self):
        """Si OmniOps me pateó al login (sesión vencida), me re-logueo solo."""
        if self._en_login():
            self._login()
            self._entrar_al_dashboard()

    def _leer_dom(self):
        return self.monitoring.leer_pcs_power()

    # --- lecturas ---
    def read(self):
        """Por defecto NO recarga: lee el DOM en vivo, que SignalR mantiene
        actualizado. Si recargar=True, vuelve al modo recargar. Si la sesión
        venció, se re-loguea solo."""
        try:
            if self.recargar:
                self.monitoring.recargar()
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
        for paso in (self.context.close, self.browser.close, self._pw.stop):
            try:
                paso()
            except Exception:
                pass


if __name__ == "__main__":
    # prueba: parseo del texto, sin abrir navegador
    for t in ["-2373.2 kW", "5043.0 kW", "  1,200.5 kW ", "—"]:
        print(f"'{t}' -> {parse_kw(t)}")
