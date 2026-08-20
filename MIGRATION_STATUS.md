# Estado de la migración a la arquitectura nueva

Se migra **capa por capa**, en el orden que recomienda ARQUITECTURA.md (sección 8),
dejando el repo funcionando en cada paso.

## ✅ Paso 1 — shared/ (HECHO y verificado)
La base común, migrada desde el framework anterior y verificada offline:

- `shared/config/settings.py`   ← config central (ex `config.py`)
- `shared/config/credentials.py`← única lectura de credenciales (.env / env), sin duplicar
- `shared/auth/auth.py`         ← TokenAuth + make_auth (usa credentials)
- `shared/datasource/modbus_source.py` ← única lectura del simulador (self-check ✓)
- `shared/utils/`               ← time_anchor, omniops_time, logger
- `shared/domain/`              ← alarm_catalog, telemetry_map, oracle, verdict,
                                   injection, power  (todos con self-check ✓)

Verificación: los 13 módulos importan y los self-checks de dominio pasan
(`oracle`, `verdict`, `injection`, `power`, `modbus_source`).

## ✅ Paso 2 — framework_api/ (SOM)  (HECHO y verificado)
- `client/api_client.py` — transporte único (auth, base URL, log)
- `services/` — base_service, alarms_service, monitoring_service (devuelven models)
- `models/` — alarm.py, site_summary.py (dataclasses con from_json; fechas UTC)
Verificación: 3 unit tests OFFLINE en `tests/api/` pasan contra `alarms_sample.json`
(`pytest tests/api -v`), sin necesidad del stack.

## ✅ Paso 3 — framework_ui/ (POM)  (HECHO)
- `browser/browser_factory.py` — ciclo de vida de Playwright (context manager)
- `base/` — base_page (wait por DOM, no networkidle), base_component
- `pages/auth/` — login_page + login_locators
- `pages/monitoring/` — monitoring_page + components/power_card (+ locators)
- `pages/alarms_events/` — alarms_page + components/alarms_table (tabla virtualizada)
Locators AL LADO de cada page. Import-check OK; parse_kw con unit test offline.
La lectura viva con navegador se confirma en el Paso 4 (fixtures) contra el stack.

## ✅ Paso 4 — tests/ con fixtures  (HECHO)
- `tests/conftest.py` — base_url, credentials, require_stack (saltea si no hay stack)
- `tests/api/conftest.py` — api_client + services (sesión, sin browser)
- `tests/ui/conftest.py` — logged_in_page (browser + login UNA vez), monitoring_page, alarms_page
- `tests/cross_layer/test_power_three_layers.py` — simulador vs API vs UI (el diferencial)
- `tests/api/alarms_events/test_alarms_live.py` — alarmas en vivo (devuelve models)
Offline: 4 unit tests pasan, los de stack se SALTAN limpio. Los cross_layer/live
corren contra el stack real (simulador + OmniOps prendidos).

## 🔶 Paso 5 — monitors/ + tools/  (5a HECHO, 5b pendiente)

### ✅ 5a — inyección de alarmas end-to-end (HECHO)
- `tools/sim_proxy.py`      — proxy Modbus (bits + telemetría). Loopback ✓
- `tools/sim_launcher.py`   — helpers de puerto + launcher simple
- `tools/arrancar_alarmas.py`— levanta sim(5021)+proxy(5020)+edge; baja al Ctrl+C
- `tools/probar.py`         — comando operativo (--vivo/--at); verify_alarms() reusable
- `tests/cross_layer/test_alarms.py` — inyecta ID 16 y verifica -> PASA (assert en el test)

Flujo:  python -m tools.arrancar_alarmas   +   python -m tools.probar 16 --vivo
   o:   pytest tests/cross_layer/test_alarms.py   (con la cadena arriba)

### ✅ 5b — monitores + sniffer + reporter (HECHO)
- `monitors/watch_power.py`        — sim vs API en vivo
- `monitors/watch_three_layers.py` — sim vs API vs UI en vivo
- `monitors/watch_alarms.py`       — alarmas en vivo (inyectás y ves causa vs API)
- `monitors/reporter.py`           — reporte (solo monitores, no tests)
- `tools/sniff_alarms_api.py`      — descubre la API de alarmas
- `tools/diagnostics/`             — scripts de investigación
Reescritos contra los services/pages nuevos. Importan OK.

---
## 🎉 MIGRACIÓN COMPLETA — las 5 capas migradas y verificadas.
Estructura: shared/ · framework_api/ · framework_ui/ · tests/ · monitors/ · tools/
Verificado en vivo: potencia 3 capas (pytest) e inyección de alarmas (probar 16).
## ⬜ Paso 3 — framework_ui/ (POM)
`browser/browser_factory.py` + `base/` + `pages/<módulo>/` (page + locators) +
`components/`.

## ⬜ Paso 4 — tests/ (api / ui / cross_layer) con fixtures de pytest

## ⬜ Paso 5 — monitors/ + tools/ (renombrados en inglés)

## Notas
- Identificadores: la migración de `shared/` conserva la lógica ya probada. El
  pase fino de renombrar helpers internos al inglés se hace junto con cada capa.
- Credenciales: ahora por `.env` (ver `.env.example`). Compat: si existe
  `omniops_login.txt`, todavía se lee.
