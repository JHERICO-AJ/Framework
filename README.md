# QA Framework — OmniOps

Automated QA for the **OmniOps** BESS monitoring platform, based on a
**differential oracle**: we read the raw value from the Modbus simulator
*independently* and compare it against what OmniOps calculates (**API**) and
displays (**UI**). For alarms, we also **inject** conditions through a
Modbus proxy and verify that OmniOps generates the expected alarm.

The simulator only exposes **raw telemetry** (temperatures, voltages, bits).
OmniOps is the system under test: it converts that telemetry into
calculations and alarms. This framework verifies that it does so correctly.

---

## Architecture (5 layers)

Each layer has a single responsibility. Dependencies point downward: tests
and monitors use everything; `framework_api` / `framework_ui` / `domain` use
`shared`; `shared` depends on nothing except `config`.

```
config (settings)                        a single place: URLs, ports, tolerances
   └── shared/        foundations: auth, credentials, Modbus source, domain, utils
        ├── framework_api/   API layer (SOM): ApiClient + services + models
        ├── framework_ui/    UI layer (POM): browser factory + pages + locators
        └── domain/          pure logic: what SHOULD happen (oracle, rules)
             └── tests/       the tests (the assert lives here) + monitors/ (live view)
```

| Layer | Folder | Responsibility |
|------|---------|-----------------|
| Config | `shared/config/` | `settings.py` (central config) + `credentials.py` (.env) |
| Core | `shared/` | auth, Modbus source, time utilities, logger |
| Domain | `shared/domain/` | pure logic: alarm catalog, oracle, verdict, injection, power |
| API | `framework_api/` | `ApiClient` (transport) + `services/` + `models/` (dataclasses) |
| UI | `framework_ui/` | `BrowserFactory` + `pages/` (page objects) + locators next to each page |
| Tests | `tests/` | `api/`, `ui/`, `cross_layer/` — the assert lives here |
| Monitors | `monitors/` | live observers (loop, for demo/debug) — they observe, they don't assert |
| Tools | `tools/` | proxy, launcher, `probar` (injection CLI), sniffer, diagnostics |

---

## Installation

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

The simulator repo (`omniops-bess-edge`) needs to sit **next to** this
project (same parent folder). If it's somewhere else, adjust `SIM_REPO_DIR`
in `shared/config/settings.py`.

---

## Running the tests

```bash
# Offline (without the stack): unit tests pass, stack-dependent ones are skipped
pytest -v

# Live (needs the stack + OmniOps): the differential between layers
pytest tests/cross_layer -v

# HTML report (pass/fail for each test, to share or save)
pytest --html=reports/report.html --self-contained-html
```

Test groups (markers): `api`, `ui`, `cross_layer`.

```bash
pytest -m api          # API only (fast, no browser)
pytest -m cross_layer  # simulator vs API vs UI
```

The **report** shows, for each test, whether it passed or failed, with
detail and — if it failed — the error. It's regenerated on every run with
`--html=...`.

---

## Alarm injection

Two commands. Docker + OmniOps have to be running separately.

```bash
python -m tools.start_alarms_stack        # brings up simulator(5021) + proxy(5020) + edge
python -m tools.run_check 16 --live       # injects alarm 16, verifies (cause + API + timing) and clears
python -m tools.run_check 16 --at 10 --until 30 --live   # timed scene
```

Data flow: `simulator (5021) -> proxy (5020) -> edge -> Event Hub -> OmniOps`.
The proxy injects the condition into the Modbus stream; OmniOps should then
generate the alarm. OmniOps timestamps come in **UTC**; the framework
compares in UTC and displays in local time.

---

## Live monitors (they observe, they don't assert)

```bash
python -m monitors.watch_power           # simulator vs API (power)
python -m monitors.watch_three_layers    # simulator vs API vs UI
python -m monitors.watch_alarms          # live alarms (you inject from another terminal)
python -m monitors.watch_fleet_power     # Fleet Overview: simulator vs API vs UI, all 6 BOLIVIA sites
```

---

## Where does X go?

| What you have | Goes in |
|---|---|
| A UI selector | `framework_ui/pages/<module>/*_locators.py` |
| A UI action/read | `framework_ui/pages/<module>/*_page.py` |
| A reusable component (table, card) | `framework_ui/pages/<module>/components/` |
| A raw HTTP call | `framework_api/services/` (via `ApiClient`) |
| A JSON model | `framework_api/models/` (dataclass with `from_json`) |
| Business logic / "expected value" | `shared/domain/` |
| A config value (URL, port, threshold) | `shared/config/settings.py` |
| A check (pass/fail) | `tests/` (the assert goes here) |
| A live monitor | `monitors/` |
| An investigation script | `tools/` |
| A read-only Postgres query used as "expected value" | `shared/datasource/` (e.g. `db_source.py`), via the `db_conn` fixture |

Rule of thumb: if something needs the system to respond, it's not `domain`.
If it crosses layers (simulator + API, or API + UI), it's `cross_layer` (a
test) or a `tools/` command. The API layer must never know about Modbus.

**Fleet Overview (Fractal sites)** is a second cross-layer test area under
`tests/ui/fleet_overview/` + `framework_ui/pages/fleet_overview/` — same
Page Object conventions as the rest of `framework_ui`, but a different
verification style than the alarm-injection oracle above: it's **read-only**
(no proxy, no injection), comparing the simulator's own live Modbus reading,
OmniOps' DB, and OmniOps' API/UI against each other for values the
backend calculates from real telemetry (Power, alarm counts, availability).
See `docs/HOW_IT_WORKS.md` §7 for the reasoning behind that approach.

---

## Offline self-checks

Most of the domain modules validate their own logic without the stack:

```bash
python -m shared.domain.oracle --self-check
python -m shared.domain.verdict --self-check
python -m shared.domain.injection --self-check
python -m shared.domain.power --self-check
python -m tools.sim_proxy --self-check
```

---

## Notes

- `pymodbus` pinned at **3.7.4** — it has to match the simulator. Newer
  versions break `ModbusSlaveContext`.
- The `.env` (real credentials) is in `.gitignore`; only `.env.example` is
  committed.
- **How and why it works (in depth): see `docs/HOW_IT_WORKS.md`** — explains
  the differential oracle, the proxy step by step, and the QA findings
  (OmniOps evaluates by telemetry and doesn't close alarms). Recommended
  reading before touching the code.
- See `MIGRATION_STATUS.md` for the migration history and `ARQUITECTURA.md`
  for the architecture details.
