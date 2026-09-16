# Status of the migration to the new architecture

Migrated **layer by layer**, in the order recommended by ARQUITECTURA.md
(section 8), leaving the repo working at every step.

## ✅ Step 1 — shared/ (DONE and verified)
The common base, migrated from the previous framework and verified offline:

- `shared/config/settings.py`   ← central config (formerly `config.py`)
- `shared/config/credentials.py`← the single place credentials are read (.env / env), no duplication
- `shared/auth/`                ← base/token_auth/cookie_auth/factory (TokenAuth + make_auth, uses credentials)
- `shared/datasource/modbus_source.py` ← the only place that reads the simulator (self-check ✓)
- `shared/utils/`               ← time_anchor, omniops_time, logger
- `shared/domain/`              ← alarm_catalog, telemetry_map, oracle, verdict,
                                   injection, power  (all with self-check ✓)

Verification: the 13 modules import fine and the domain self-checks pass
(`oracle`, `verdict`, `injection`, `power`, `modbus_source`).

## ✅ Step 2 — framework_api/ (SOM)  (DONE and verified)
- `client/api_client.py` — single transport (auth, base URL, log)
- `services/` — base_service, alarms_service, monitoring_service (return models)
- `models/` — alarm.py, site_summary.py (dataclasses with from_json; UTC dates)
Verification: 3 OFFLINE unit tests in `tests/api/` pass against
`alarms_sample.json` (`pytest tests/api -v`), no stack needed.

## ✅ Step 3 — framework_ui/ (POM)  (DONE)
- `browser/browser_factory.py` — Playwright lifecycle (context manager)
- `base/` — base_page (wait by DOM, not networkidle), base_component
- `pages/auth/` — login_page + login_locators
- `pages/monitoring/` — monitoring_page + components/power_card (+ locators)
- `pages/alarms_events/` — alarms_page + components/alarms_table (virtualized table)
Locators live NEXT TO each page. Import check OK; parse_kw with an offline unit test.
Live reading with a browser is confirmed in Step 4 (fixtures) against the stack.

## ✅ Step 4 — tests/ with fixtures  (DONE)
- `tests/conftest.py` — base_url, credentials, require_stack (skips cleanly if no stack)
- `tests/api/conftest.py` — api_client + services (session, no browser)
- `tests/ui/conftest.py` — logged_in_page (browser + login ONCE), monitoring_page, alarms_page
- `tests/cross_layer/test_power_three_layers.py` — simulator vs API vs UI (the differential)
- `tests/api/alarms_events/test_alarms_live.py` — live alarms (returns models)
Offline: 4 unit tests pass, the stack-dependent ones SKIP cleanly. The
cross_layer/live ones run against the real stack (simulator + OmniOps up).

## 🔶 Step 5 — monitors/ + tools/  (5a DONE, 5b pending)

### ✅ 5a — end-to-end alarm injection (DONE)
- `tools/sim_proxy.py`      — Modbus proxy (bits + telemetry). Loopback ✓
- `tools/sim_launcher.py`   — port helpers + simple launcher
- `tools/start_alarms_stack.py`— brings up sim(5021)+proxy(5020)+edge; tears down on Ctrl+C
- `tools/run_check.py`      — operational command (--live/--at); reusable verify_alarms()
- `tests/cross_layer/test_alarms.py` — injects ID 16 and verifies -> PASS (assert in the test)

Flow:  python -m tools.start_alarms_stack   +   python -m tools.run_check 16 --live
   or: pytest tests/cross_layer/test_alarms.py   (with the chain above)

### ✅ 5b — monitors + sniffer + reporter (DONE)
- `monitors/watch_power.py`        — sim vs API live
- `monitors/watch_three_layers.py` — sim vs API vs UI live
- `monitors/watch_alarms.py`       — live alarms (you inject and see cause vs API)
- `monitors/reporter.py`           — report (monitors only, not tests)
- `tools/sniff_alarms_api.py`      — discovers the alarms API
- `tools/diagnostics/`             — investigation scripts
Rewritten against the new services/pages. Import fine.

---
## 🎉 MIGRATION COMPLETE — all 5 layers migrated and verified.
Structure: shared/ · framework_api/ · framework_ui/ · tests/ · monitors/ · tools/
Verified live: three-layer power (pytest) and alarm injection (probar 16).
## ⬜ Step 3 — framework_ui/ (POM)
`browser/browser_factory.py` + `base/` + `pages/<module>/` (page + locators) +
`components/`.

## ⬜ Step 4 — tests/ (api / ui / cross_layer) with pytest fixtures

## ⬜ Step 5 — monitors/ + tools/ (renamed to English)

## Notes
- Identifiers: the `shared/` migration keeps the already-proven logic. The
  fine-grained pass of renaming internal helpers to English happens
  together with each layer.
- Credentials: now via `.env` (see `.env.example`). Compat: if
  `omniops_login.txt` exists, it's still read.
