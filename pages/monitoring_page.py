"""
monitoring_page.py — el dashboard de monitoreo.

Selectores y lecturas de la pantalla principal: la tarjeta de "Actual PCS Power"
y su valor, más la tabla de alarmas (para cuando se sume esa validación).
Todo lo específico de esta pantalla vive acá.
"""

from __future__ import annotations

import re

from config import BASE_URL
from pages.base_page import BasePage

MONITORING_URL = f"{BASE_URL}/monitoring?timeRange=24h"


def parse_kw(texto):
    """De un texto tipo '-2373.2 kW' saca el número. Sin dato (N/A, —) -> None."""
    if texto is None:
        return None
    t = texto.strip().lower()
    if t in ("n/a", "na", "—", "-", "", "sin dato"):
        return None
    m = re.search(r"-?\d[\d,]*\.?\d*", texto.replace(",", ""))
    return float(m.group()) if m else None


class MonitoringPage(BasePage):
    URL = MONITORING_URL

    # --- selectores ---
    DEVICE_CARD = ".device-card"
    PCS_POWER_LABEL = "Actual PCS Power"
    METRIC_VALUE = ".metric-value"
    ALARM_TABLE = "#alarmTableBody"          # para la validación de alarmas (futuro)

    def ir(self):
        self.page.goto(self.URL)
        self.esperar_carga()

    def recargar(self):
        self.page.reload()
        self.esperar_carga()

    def _card_pcs(self):
        return self.page.locator(self.DEVICE_CARD, has_text=self.PCS_POWER_LABEL)

    def esperar_card(self, timeout=10000):
        self._card_pcs().wait_for(timeout=timeout)

    def leer_pcs_power(self):
        """Devuelve (kw, texto_crudo) de la tarjeta 'Actual PCS Power'."""
        card = self._card_pcs()
        card.wait_for(timeout=15000)
        texto = card.locator(self.METRIC_VALUE).inner_text()
        return parse_kw(texto), texto
