"""watch_power — monitor EN VIVO de potencia: simulador vs API (cálculo).

Observa en bucle (no valida). Para demo/debug. Ctrl+C para salir.
    python -m monitors.watch_power
"""
from __future__ import annotations

import time

from shared.config.settings import BASE_URL, SITE_ID, OMNIOPS_EVERY_S
from shared.datasource.modbus_source import read_sim_total_kw, close_sim
from shared.domain import power
from framework_api.client.api_client import ApiClient
from framework_api.services.monitoring_service import MonitoringService


def run():
    svc = MonitoringService(ApiClient(BASE_URL))
    print("watch_power — simulador vs API (Ctrl+C para salir)\n")
    try:
        while True:
            sim_kw, _ = read_sim_total_kw()
            api_kw = svc.get_summary(SITE_ID).actual_pcs_power_kw
            ok = api_kw is not None and power.matches(sim_kw, float(api_kw))
            api_txt = f"{float(api_kw):8.0f}" if api_kw is not None else "   —"
            print(f"sim={sim_kw:8.0f} kW   api={api_txt} kW   "
                  f"{'PASA' if ok else 'FALLA'}")
            time.sleep(OMNIOPS_EVERY_S)
    except KeyboardInterrupt:
        print("\nfin.")
    finally:
        close_sim()


if __name__ == "__main__":
    run()
