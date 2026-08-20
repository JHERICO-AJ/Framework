"""
config.py — CONFIGURACIÓN CENTRAL del framework.

Todo lo que antes estaba repetido y desperdigado (URLs, puertos, intervalos,
tolerancias) vive ahora acá. Si algo cambia de entorno, se toca UN solo lugar.
El resto de los archivos hace `from shared.config.settings import ...`.
"""

import os

# raíz del proyecto (para resolver rutas de archivos sin depender del cwd)
# raíz del proyecto. settings.py vive en shared/config/, así que subimos 2 niveles.
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# --- OmniOps (API) ----------------------------------------------------------
BASE_URL = "http://localhost:5173"
SITE_ID = "10000000-0000-0000-0000-000000000001"
SUMMARY_PATH = f"/api/monitoring/summary/{SITE_ID}"
ALARMS_PATH = "/api/events/alarms/filtered"
ALARMS_UI_PATH = "/alarms"      # vista de la tabla de alarmas en el frontend

# rango físico plausible de potencia (para el smoke test)
POWER_MIN_KW = -50000
POWER_MAX_KW = 50000

# --- Simulador (Modbus) -----------------------------------------------------
SIM_HOST = "127.0.0.1"
SIM_PORT = 5020         # puerto que LEEN el edge y el oráculo (con proxy, es el proxy)
SIM_UNIT = 1
PCS_W_REGS = [(17014, 17015), (17114, 17115), (17214, 17215)]  # potencia W por PCS (Model 103)

# --- Proxy de inyección (para disparar alarmas) ----------------------------
# El proxy escucha en SIM_HOST:SIM_PORT (5020, donde ya apunta el edge) y reenvía
# al simulador REAL, que se corre en SIM_REAL_PORT (5021). Sobre cada lectura
# aplica lo que haya en INJECT_STATE_FILE (lo escribe alarms/inject.py).
SIM_REAL_HOST = "127.0.0.1"
SIM_REAL_PORT = 5021
INJECT_STATE_FILE = os.path.join(ROOT, "inject_state.json")

# --- Arrancador (levantar sim + proxy + edge en orden) ---------------------
# Ruta del repo del simulador/edge (omniops-bess-edge). Por defecto lo busca como
# carpeta hermana de este proyecto; ajustá si está en otro lado.
SIM_REPO_DIR = os.path.abspath(os.path.join(ROOT, "..", "omniops-bess-edge"))
SIM_SCRIPT = os.path.join(SIM_REPO_DIR, "simulator", "bess_modbus_simulator.py")
EDGE_SCRIPT = os.path.join(SIM_REPO_DIR, "edge", "main.py")
EDGE_CONFIG = os.path.join(SIM_REPO_DIR, "data", "generated_configs",
                           f"site_snapshot_config_{SITE_ID}.yaml")
SIM_TICK_S = 5          # cada cuántos segundos el simulador manda datos
# Python con el que se corre el EDGE (tiene sus deps: pyyaml, dotenv, azure SDK).
# El simulador se corre con el mismo por defecto. Ajustá si usás otro intérprete.
EDGE_PYTHON = r"C:\Users\AJ\AppData\Local\Programs\Python\Python314\python.exe"

# --- Tolerancias de la capa CÁLCULO (sim vs API) ---------------------------
TOL_ABS_KW = 50.0
TOL_REL = 0.02

# --- Monitoreo en vivo (tiempos) -------------------------------------------
OMNIOPS_EVERY_S = 6     # cada cuánto le preguntamos a OmniOps. Más bajo = más
                        # responsivo pero arriesga el error 429. 6 es seguro.
SIM_EVERY_S = 1         # resolución del anclaje. Con conexión Modbus persistente
                        # (source_modbus) leer cada 1s sale casi gratis.
BUFFER_S = 30           # historial del simulador. El anclaje solo mira ~1-2s
                        # hacia atrás, así que 30 alcanza de sobra (antes 90).

# --- Anclaje por tiempo (DOS umbrales, distintos a propósito) --------------
# Más lejos que esto, la comparación NO es confiable -> DESCARTADA.
GAP_CONFIABLE_S = 1.0
# En watch_compare_anchored: hasta este gap intenta anclar (entre este y
# GAP_CONFIABLE_S la registra pero el reporter la marca descartada). En
# watch_3capas el corte es directamente GAP_CONFIABLE_S.
GAP_MAX_ANCLAJE_S = 1.5

# --- Capa PANTALLA (UI / Playwright) ---------------------------------------
UI_TOL_KW = 0.6         # margen para el redondeo a 1 decimal de la pantalla
HEADLESS = False        # True = navegador oculto (arranca más liviano/rápido);
                        # False = ventana visible (para demos). Este es el que
                        # más cambia la velocidad de arranque.

# Evidencia visual: sacar screenshot del dashboard cuando aparece una FALLA.
# Solo dispara al ENTRAR en falla (una captura por episodio), así que no afecta
# la velocidad en régimen normal (todo PASA).
CAPTURAR_FALLAS = True
CAPTURAS_DIR = "reportes/capturas"

# Comando alternativo (lo usa tools/sim_launcher.py, que levanta sim+edge juntos
# vía launch_site.py). Para inyección usá el arrancador (tools/arrancar_alarmas).
SIM_LAUNCH_CMD = ["py", r".\utils\launch_site.py", "{site}", "{port}", "{tick}"]
