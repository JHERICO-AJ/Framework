"""
config.py — CONFIGURACIÓN CENTRAL del framework.

Todo lo que antes estaba repetido y desperdigado (URLs, puertos, intervalos,
tolerancias) vive ahora acá. Si algo cambia de entorno, se toca UN solo lugar.
El resto de los archivos hace `from config import ...`.
"""

# --- OmniOps (API) ----------------------------------------------------------
BASE_URL = "http://localhost:5173"
SITE_ID = "10000000-0000-0000-0000-000000000001"
SUMMARY_PATH = f"/api/monitoring/summary/{SITE_ID}"
ALARMS_PATH = "/api/events/alarms/filtered"

# rango físico plausible de potencia (para el smoke test)
POWER_MIN_KW = -50000
POWER_MAX_KW = 50000

# --- Simulador (Modbus) -----------------------------------------------------
SIM_HOST = "127.0.0.1"
SIM_PORT = 5020
SIM_UNIT = 1
# potencia W por PCS en el Model 103: (registro_valor, registro_scale_factor)
PCS_W_REGS = [(17014, 17015), (17114, 17115), (17214, 17215)]

# --- Tolerancias de la capa CÁLCULO (sim vs API) ---------------------------
TOL_ABS_KW = 50.0
TOL_REL = 0.02

# --- Monitoreo en vivo (tiempos) -------------------------------------------
OMNIOPS_EVERY_S = 6     # cada cuánto le preguntamos a OmniOps (suave para el 429)
SIM_EVERY_S = 1         # cada cuánto guardamos el simulador en el historial
BUFFER_S = 90           # cuánto historial del simulador guardamos

# --- Anclaje por tiempo (DOS umbrales, distintos a propósito) --------------
# Más lejos que esto, la comparación NO es confiable -> DESCARTADA.
GAP_CONFIABLE_S = 1.0
# En watch_compare_anchored: hasta este gap intenta anclar (entre este y
# GAP_CONFIABLE_S la registra pero el reporter la marca descartada). En
# watch_3capas el corte es directamente GAP_CONFIABLE_S.
GAP_MAX_ANCLAJE_S = 1.5

# --- Capa PANTALLA (UI / Playwright) ---------------------------------------
UI_TOL_KW = 0.6         # margen para el redondeo a 1 decimal de la pantalla
HEADLESS = False      # True = navegador oculto; False = visible
