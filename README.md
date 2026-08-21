# OmniOps QA Framework

Automated QA for the **OmniOps** BESS monitoring platform, based on a
**differential oracle**: we read the raw value from the Modbus simulator
*independently* and compare it against what OmniOps computes (**API**) and shows
(**UI**). For alarms, we also **inject** conditions through a Modbus proxy and
verify that OmniOps raises the expected alarm.

The simulator only exposes **raw telemetry** (temperatures, voltages, bits).
OmniOps is the system under test: it turns that telemetry into calculations and
alarms. This framework checks that it does so correctly.

---

## Architecture (5 layers)

Each layer has a single responsibility. Dependencies point downward: tests and
monitors use everything; `framework_api` / `framework_ui` / `domain` use
`shared`; `shared` depends on nothing but `config`.

```
config (settings)                        one place for URLs, ports, tolerances
   └── shared/        foundations: auth, credentials, modbus source, domain, utils
        ├── framework_api/   API layer (SOM): ApiClient + services + models
        ├── framework_ui/    UI layer (POM): browser factory + pages + locators
        └── domain/          pure logic: what SHOULD happen (oracle, rules)
             └── tests/       the checks (assert lives here) + monitors/ (live view)
```

| Layer | Folder | Responsibility |
|-------|--------|----------------|
| Config | `shared/config/` | `settings.py` (central config) + `credentials.py` (.env) |
| Core | `shared/` | auth, Modbus source, time utils, logger |
| Domain | `shared/domain/` | pure logic: alarm catalog, oracle, verdict, injection, power |
| API | `framework_api/` | `ApiClient` (transport) + `services/` + `models/` (dataclasses) |
| UI | `framework_ui/` | `BrowserFactory` + `pages/` (page objects) + locators next to each page |
| Tests | `tests/` | `api/`, `ui/`, `cross_layer/` — the assertions live here |
| Monitors | `monitors/` | live watchers (loop, for demo/debug) — they observe, not assert |
| Tools | `tools/` | proxy, launcher, `probar` (inject CLI), sniffer, diagnostics |

**Where things go (rule of thumb).** If it only talks to the screen → `framework_ui`.
If it only talks to the API → `framework_api`. If it **injects** into the simulator
or **crosses layers** (simulator + API/UI) → `tools/` (a command) or `tests/cross_layer/`
(a check). The UI and API layers never know about Modbus/injection. That is why
`tools/probar.py` — which injects *and* verifies — lives in `tools/`, even though it
reads the UI and the API: it imports from both layers, so it belongs to neither.

---

## Setup

```bash
# 1. Virtual environment
python -m venv venv
venv\Scripts\Activate.ps1          # Windows PowerShell
# source venv/bin/activate         # Linux / macOS

# 2. Dependencies
pip install -r requirements.txt
playwright install chromium         # browser for the UI layer

# 3. Credentials  (never commit the .env)
copy .env.example .env              # Windows  (cp on Linux/macOS)
# edit .env and set OMNIOPS_EMAIL and OMNIOPS_PASSWORD
```

The simulator repo (`omniops-bess-edge`) must sit **next to** this project (same
parent folder). If it lives elsewhere, adjust `SIM_REPO_DIR` in
`shared/config/settings.py`.

---

## Running the tests

```bash
# Offline (no stack needed): unit tests pass, stack tests are skipped
pytest -v

# Live (requires the stack up + OmniOps): the differential across layers
pytest tests/cross_layer -v

# HTML report (green/red evidence, shareable)
pytest --html=reports/report.html --self-contained-html
```

Test markers: `api`, `ui`, `cross_layer`.

Key live tests (in `tests/cross_layer/`):
- `test_power_three_layers` — power: simulator vs API vs UI.
- `test_alarms` — inject alarm 16, verify OmniOps creates it (API).
- `test_alarms_ui::test_injected_alarm_shows_on_screen` — inject 16, verify API + UI.
- `test_alarms_ui::test_alarm_scene_end_to_end` — full timeline (see below).

---

## Alarm injection & verification

Bring up the chain (Docker + OmniOps running separately):

```bash
python -m tools.arrancar_alarmas          # starts simulator(5021) + proxy(5020) + edge
```

Then inject and verify with `tools.probar`:

```bash
python -m tools.probar 16                       # cause (raw) + API
python -m tools.probar 16 --with-ui             # cause + API + UI (ui:YES)
python -m tools.probar 16 --ui-only             # SCREEN only (no API): by name + fresh timestamp
python -m tools.probar 16 --at 5 --hasta 40     # full scene (see below)
python -m tools.probar --criticals --with-ui    # all injectable critical alarms
python -m tools.probar --subsystem pcs          # alarms of a subsystem
```

**Full scene** (`--at N --hasta M`): the complete end-to-end timeline, shown live —
before injection (absent) → inject at N (records the exact moment) → verify it is
registered at inject time, shown on the /alarms screen, and that the screen timestamp
matches the API → `lastOccurred` rising live → clear at M → verify the cause is gone
and `lastOccurred` freezes.

**UI-only** (`--ui-only`): inject, then verify **on the screen only** (no API), reading
the row's `first`/`last occurred` from the /alarms table. A fresh `last occurred`
proves our injection reached the UI; a fresh `first occurred` means the alarm is NEW.

Data flow: `simulator (5021) -> proxy (5020) -> edge -> Event Hub -> OmniOps`.
Timestamps from OmniOps are in **UTC**; the framework compares in UTC and displays
in local time. OmniOps does not close alarms, so we verify freshness via
`lastOccurred` (see `docs/COMO_FUNCIONA.md`).

---

## Live monitors (observe, do not assert)

```bash
python -m monitors.watch_power           # simulator vs API (power)
python -m monitors.watch_three_layers    # simulator vs API vs UI
python -m monitors.watch_alarms          # alarms live (inject from another terminal)
```

---

## Offline self-checks

Most domain modules validate their own logic without the stack:

```bash
python -m shared.domain.oracle --self-check
python -m shared.domain.verdict --self-check
python -m shared.domain.injection --self-check
python -m shared.domain.power --self-check
python -m tools.sim_proxy --self-check
```

---

## Notes

- `pymodbus` is pinned to **3.7.4** — it must match the simulator. Newer versions
  break `ModbusSlaveContext`.
- The `.env` (real credentials) is git-ignored; only `.env.example` is committed.
- `EDGE_PYTHON` in `settings.py` points to the interpreter used to launch the edge
  (it has its own deps: pyyaml, dotenv, Azure SDK). Adjust it per machine.
- Deep dive on how the proxy and the oracle work: `docs/COMO_FUNCIONA.md`.
- Architecture rationale: `ARQUITECTURA.md`. Migration history: `MIGRATION_STATUS.md`.
