"""
settings.py — CENTRAL CONFIGURATION for the framework.

Everything that used to be duplicated and scattered around (URLs, ports,
intervals, tolerances) now lives here. If something changes per environment,
only ONE place needs to change.
The rest of the files do `from shared.config.settings import ...`.
"""

import os

from shared.config.credentials import _load_dotenv

_load_dotenv()

# project root (to resolve file paths without depending on the cwd)
# project root. settings.py lives in shared/config/, so we go up 2 levels.
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _env_bool(name, default):
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in ("1", "true", "yes", "on")


# --- OmniOps (API) ----------------------------------------------------------
BASE_URL = os.environ.get("BASE_URL", "http://localhost:5173")

# "microsoft" (SSO, default -- matches the credentials currently in .env) or
# "native" (OmniOps' own email/password form, still present on /login).
LOGIN_METHOD = os.environ.get("LOGIN_METHOD", "microsoft")

# Default timeout (seconds) for every HTTP call made against OmniOps.
HTTP_TIMEOUT_S = float(os.environ.get("HTTP_TIMEOUT_S", 10))
SITE_ID = "10000000-0000-0000-0000-000000000001"
SUMMARY_PATH = f"/api/monitoring/summary/{SITE_ID}"
ALARMS_PATH = "/api/events/alarms/filtered"
ALARMS_UI_PATH = "/alarms"      # alarms table view in the frontend

# plausible physical power range (for the smoke test)
POWER_MIN_KW = -50000
POWER_MAX_KW = 50000

# --- Simulator (Modbus) -----------------------------------------------------
SIM_HOST = "127.0.0.1"
SIM_PORT = 5020         # port that the edge and the oracle READ (with the proxy, it's the proxy)
SIM_UNIT = 1
PCS_W_REGS = [(17014, 17015), (17114, 17115), (17214, 17215)]  # power W per PCS (Model 103)

# --- Injection proxy (to trigger alarms) ------------------------------------
# The proxy listens on SIM_HOST:SIM_PORT (5020, where the edge already points) and
# forwards to the REAL simulator, which runs on SIM_REAL_PORT (5021). On every
# read it applies whatever is in INJECT_STATE_FILE (written by alarms/inject.py).
SIM_REAL_HOST = "127.0.0.1"
SIM_REAL_PORT = 5021
INJECT_STATE_FILE = os.path.join(ROOT, "inject_state.json")

# --- Fractal simulators (per-BOLIVIA-site Modbus TCP, for cross-layer power
# checks -- shared/datasource/fractal_modbus_source.py). {site_name: (port,
# unit_id)}. Ports come from launch_sites.py's own startup log each run
# (auto-assigned, confirmed stable across restarts as of 2026-08-28); unit_ids
# come from each site's fractal-*.local.yaml (modbus_unit_id).
FRACTAL_SITE_MODBUS = {
    "BOLIVIA":   (5020, 9),
    "BOLIVIA 1": (5021, 7),
    "BOLIVIA 2": (5022, 8),
    "BOLIVIA 3": (5023, 10),
    "BOLIVIA 4": (5024, 11),
    "BOLIVIA 5": (5025, 12),
}

# --- DB (read-only cross-layer checks) ---------------------------------------
# All None if unset -- tests/conftest.py's db_conn fixture SKIPS (not fails)
# when any of these is missing, same pattern as require_omniops.
DB_HOST = os.environ.get("DB_HOST")
DB_PORT = os.environ.get("DB_PORT", "5432")
DB_NAME = os.environ.get("DB_NAME")
DB_USER = os.environ.get("DB_USER")
DB_PASSWORD = os.environ.get("DB_PASSWORD")

# --- Launcher (bring up sim + proxy + edge in order) ------------------------
# Path to the simulator/edge repo (omniops-bess-edge). By default it looks for it
# as a sibling folder of this project; override with SIM_REPO_DIR in .env if
# it's somewhere else on your machine.
SIM_REPO_DIR = os.environ.get(
    "SIM_REPO_DIR", os.path.abspath(os.path.join(ROOT, "..", "omniops-bess-edge")))
SIM_SCRIPT = os.path.join(SIM_REPO_DIR, "simulator", "bess_modbus_simulator.py")
EDGE_SCRIPT = os.path.join(SIM_REPO_DIR, "edge", "main.py")
EDGE_CONFIG = os.path.join(SIM_REPO_DIR, "data", "generated_configs",
                           f"site_snapshot_config_{SITE_ID}.yaml")
SIM_TICK_S = 5          # how often (seconds) the simulator sends data
# Python interpreter used to run the EDGE (has its own deps: pyyaml, dotenv, azure SDK).
# Machine-specific: set EDGE_PYTHON in .env. No hardcoded machine path here -- if unset,
# this is empty and the caller (tools/start_alarms_stack.py) falls back to sys.executable.
EDGE_PYTHON = os.environ.get("EDGE_PYTHON", "")

# --- Tolerances for the CALC layer (sim vs API) -----------------------------
TOL_ABS_KW = 50.0
TOL_REL = 0.02

# --- Live monitoring (timings) ----------------------------------------------
OMNIOPS_EVERY_S = 6     # how often we ask OmniOps. Lower = more responsive but
                        # risks a 429 error. 6 is safe.
SIM_EVERY_S = 1         # anchor resolution. With a persistent Modbus connection
                        # (modbus_source) reading every 1s is almost free.
BUFFER_S = 30           # simulator history. The anchor only looks back ~1-2s,
                        # so 30 is plenty (used to be 90).

# --- Time anchoring (TWO thresholds, deliberately different) ---------------
# Beyond this, the comparison is NOT reliable -> DISCARDED.
RELIABLE_GAP_S = 1.0
# In watch_compare_anchored: it tries to anchor up to this gap (between this and
# RELIABLE_GAP_S it records it but the reporter marks it discarded). In
# watch_three_layers the cutoff is directly RELIABLE_GAP_S.
MAX_ANCHOR_GAP_S = 1.5

# --- SCREEN layer (UI / Playwright) -----------------------------------------
UI_TOL_KW = 0.6         # margin for the screen's rounding to 1 decimal
HEADLESS = _env_bool("HEADLESS", False)  # True = hidden browser (starts lighter/
                        # faster); False = visible window (for demos). This is
                        # the one that most changes startup speed. Override with
                        # HEADLESS=true in .env (e.g. for CI).

# Visual evidence: take a screenshot of the dashboard when a FAILURE appears.
# Only fires when ENTERING a failure (one capture per episode), so it doesn't
# affect speed under normal conditions (everything PASSing).
CAPTURE_FAILURES = _env_bool("CAPTURE_FAILURES", True)
CAPTURES_DIR = "reports/captures"

# Playwright trace (step-by-step replay: screenshots, DOM snapshots, network,
# console -- viewable with `playwright show-trace <file>.zip`, same UI as
# Playwright Test's trace viewer). Same "only on failure" principle as
# CAPTURE_FAILURES -- see tests/conftest.py's _trace_per_test fixture.
CAPTURE_TRACES = _env_bool("CAPTURE_TRACES", True)
TRACES_DIR = "reports/traces"

# Alternative command (used by tools/sim_launcher.py, which brings up sim+edge
# together via launch_site.py). For injection use the launcher (tools/start_alarms_stack).
SIM_LAUNCH_CMD = ["py", r".\utils\launch_site.py", "{site}", "{port}", "{tick}"]
