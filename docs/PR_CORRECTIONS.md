# Context for Claude Code — Apply PR review corrections (Framework #2)

> Paste into the branch you use to fix the structure PR (e.g. `docs/PR_CORRECTIONS.md`)
> and point Claude Code at it. These are review comments from a teammate on PR #2
> (the dual-architecture migration). They are mostly **organization/style**, not logic.
> Apply them WITHOUT changing behavior; after each change, run the offline checks to
> confirm nothing broke.

## Guardrails (read first)

- **Do not change behavior.** These are refactors: move/rename/split, keep logic identical.
- After each group, run:
  - `pytest -v` (offline: unit tests pass, stack tests skip)
  - the domain self-checks: `python -m shared.domain.oracle --self-check`,
    `... verdict --self-check`, `... injection --self-check`, `... power --self-check`,
    `python -m tools.sim_proxy --self-check`
- Keep everything **in English** (the whole PR is meant to be English for the Dallas team).
- Update imports everywhere a symbol moves. Don't leave dangling imports.
- The framework verifies OmniOps live; you can't run the live stack here, so rely on the
  offline checks + import checks after each change.

---

## Correction 0 — Translate EVERYTHING to English (highest priority)

This was the teammate's FIRST request on the PR: *"Kindly consider to have everything in
English because we work with people from Dallas, so they need to be able to understand our
framework."* It applies to the WHOLE repo, so do it as a sweep BEFORE the other corrections
(so you don't rename twice).

Translate to English, keeping behavior identical:
- **Identifiers** (functions, methods, variables, classes) still in Spanish. Known ones in
  the domain and tools:
  - `guardar_estado` → `save_state`, `leer_estado` → `read_state`, `limpiar_estado` → `clear_state`
  - `evaluar` → `evaluate`, `causa_de` → `cause_of`, `clasificar` → `classify`
  - `overrides_para` → `overrides_for`, `leer_registro` → `read_register`
  - `raw_extremo` → `extreme_raw_value`, `probar` → `check` / `run_check`
  - verdict constants: `PASA` → `PASS`, `PASA_SANO` → `PASS_HEALTHY`,
    `FALLA_FALSA` → `FAIL_FALSE_ALARM`, `FALLA_NO_DETECTADA` → `FAIL_NOT_DETECTED`,
    `NO_VERIFICABLE` → `NOT_VERIFIABLE`
  - any Spanish variable names (`causa`, `fresca`, `abierta`, `alarmas`, `estado`, etc.)
- **Comments and docstrings** in Spanish → English.
- **User-facing strings** (CLI messages, prints) → English. (Keep any `--vivo`/`--criticas`
  aliases if you want backward compatibility, but the primary flag is the English one.)
- **Dict keys used as internal data** (e.g. catalog fields `nombre`, `limite`, `dir`,
  `tipo`, `aprox`) → decide with care: if they're internal, translate (`nombre`→`name`,
  `limite`→`limit`, `tipo`→`type`, `aprox`→`approx`) and update every reader. Do NOT
  translate keys that must match the backend JSON (those are external contracts).

**This is a rename that ripples across the whole repo** — update every caller. After the
sweep, run `pytest -v` and all self-checks to confirm nothing broke. Only once the repo is
fully English, proceed with Corrections 1–10 below.

> Note: file/doc content already in English (README.md, docs/COMO_FUNCIONA.md is Spanish →
> translate or rename to COMO_FUNCIONA is fine to leave as an ES doc if the team wants a
> Spanish reference, but the reviewer asked for English — confirm. Default: translate docs
> too, or keep a single English HOW_IT_WORKS.md.)

---

## Correction 1 — Move standalone functions out of "data"/class files

The reviewer flagged several files that mix a plain function with data or with a class.
Create a single home for pure parsing/format helpers and move them there.

**Create `shared/utils/parsing.py`** and move these pure functions into it (keep behavior
identical), then update all imports:
- `parse_kw`  — currently in `framework_ui/pages/monitoring/components/power_card.py`
- `_parse_dt` — currently in `framework_api/models/alarm.py` (rename to `parse_api_datetime`)
- `parse_ui_datetime` — currently in `framework_ui/pages/alarms_events/components/alarms_table.py`
- `raw_extremo` — currently in `shared/domain/telemetry_map.py` (rename to `extreme_raw_value`)
- `unwrap` — currently in `framework_api/services/base_service.py`
  (rename to something explicit like `extract_list_payload`)

For each: the original file imports it from `shared/utils/parsing.py` instead of defining it.
`PowerCard`, `AlarmsTable`, `Alarm`, `AlarmsService` keep calling the same function, now imported.

> Reviewer's words: "Functions (parse_kw, _parse_dt) outside classes. Move to
> shared/utils/parsing.py or make static methods." We choose the shared module.

---

## Correction 2 — One class per file (don't put two classes together)

**`framework_ui/pages/alarms_events/components/alarms_table.py`** currently defines BOTH
`AlarmRow` (dataclass) and `AlarmsTable`. Split:
- Move `AlarmRow` to its own file: `framework_ui/pages/alarms_events/components/alarm_row.py`.
- `alarms_table.py` imports `AlarmRow` from there.
- Update any other importers of `AlarmRow`.

> Reviewer: "Two classes shouldn't share the same file. Put this class in another file
> and in the corresponding folder."

---

## Correction 3 — Separate test helper classes from the tests

**`tests/api/alarms_events/test_alarms_service.py`** defines a `FakeClient` class inline.
Move `FakeClient` to a test-support module, e.g.
`tests/api/alarms_events/fakes.py` (or `tests/support/fakes.py`), and import it in the test.
The test file should contain only test functions.

> Reviewer: "Do not mix Class definitions and test in one file."

---

## Correction 4 — telemetry_map.py: data vs function

**`shared/domain/telemetry_map.py`** mixes the telemetry constants (the dict) with the
`raw_extremo` function. After Correction 1 moves `raw_extremo` to `shared/utils/parsing.py`,
this file should contain ONLY the data (the map/constants) plus clear section comments.
If any small derivation must stay, isolate it with a header comment. End state: this file
is data-only.

> Reviewer: "You are mixing data and function in one file."

---

## Correction 5 — Split auth classes into separate files

**`shared/auth/auth.py`** holds multiple classes (`Auth`, `TokenAuth`, `CookieAuth`, plus
`make_auth`). Split into a small package so each class is easy to find and extend:
- `shared/auth/base.py`      → the abstract `Auth`
- `shared/auth/token_auth.py`→ `TokenAuth`
- `shared/auth/cookie_auth.py`→ `CookieAuth`
- `shared/auth/factory.py`   → `make_auth`
- keep `shared/auth/__init__.py` re-exporting the public names so existing imports
  (`from shared.auth.auth import make_auth`) keep working — OR update all importers.
  Prefer updating importers to the new modules and re-export from `__init__` for safety.

Also: the reviewer flagged a block in `auth.py` as "should not be part of this file" and
asked to review the credentials wiring — the `_load_creds`/`load_credentials` bridge. Make
sure credential loading lives in `shared/config/credentials.py` only, and auth just calls it.

> Reviewer: "Many classes in only one file could be difficult to understand... separate
> the classes in different files."

---

## Correction 6 — Add timeout (and basic retry) to network calls

**`make_auth` and the API transport can hang.** Add an explicit `timeout` parameter:
- `make_auth(base_url, timeout=...)` and pass it down to the auth HTTP calls.
- `ApiClient.__init__(self, base_url, auth=None, timeout=10)` — store it and apply it to
  every request (the `authorized_get` / underlying urllib/requests call must receive a
  timeout).
- Add a small, bounded retry (e.g. 2–3 attempts with short backoff) for transient network
  errors on GET. Keep it simple; don't retry on 4xx.

Put the default timeout value in `settings.py` (see Correction 8) e.g. `HTTP_TIMEOUT_S`.

> Reviewer: "make_auth() calls can hang. Add timeout parameter. Network calls need
> timeout and retry logic."

---

## Correction 7 — Descriptive parameter names

Across the models/services (and anywhere else), rename terse params:
- `d` → `alarm_dict` / `payload_dict` (as fits)
- `a` → `alarm`
- `v` → `value`
- any other single-letter or vague names in method signatures → explicit names.
Do this in `from_json` methods of `Alarm` and `SiteSummary`, and review every method in
the classes. Keep the public method names the same; only the parameters change.

> Reviewer: "Review the parameter names. They should be more descriptive... (Review all
> the methods of your classes)."

---

## Correction 8 — Configurable data from .env

**`shared/config/settings.py`**: values that vary per machine/environment must come from
the environment, not be hardcoded. At minimum:
- `EDGE_PYTHON = os.environ["EDGE_PYTHON"]` (with a helpful error if missing, or
  `os.environ.get` + a clear fallback). The reviewer explicitly cited this one.
- Review the rest of the file for other machine-specific/hardcoded values (paths, URLs,
  credentials-ish) and move them to `.env` / `os.environ`, documenting each in `.env.example`.
- Keep pure constants (tolerances, register numbers) in code — those are not environment
  config. Use judgment: environment-specific → `.env`; domain constants → stay.

Update `.env.example` with every new variable.

> Reviewer: "The configurable data should be extracted from the .env file, like
> EDGE_PYTHON = os.environ['EDGE_PYTHON']."

---

## Correction 9 — Break up long functions

**`monitors/watch_alarms.py`** `run()` has too much logic. Refactor into smaller focused
helpers (e.g. `_build_baseline()`, `_read_state()`, `_print_line()`), keeping the loop in
`run()` thin. Same behavior, smaller pieces. Scan the other `monitors/*.py` for the same
issue and apply the same treatment where a function is clearly doing too much.

> Reviewer: "Too much logic in a single function. Refactor into smaller, more focused
> methods."

---

## Correction 10 — `base_service.unwrap` → a response class

The reviewer suggested the response-shape handling should be a class, not a loose function.
After Correction 1 moves the helper, consider modeling the API response explicitly (a small
class that knows how to yield the list of items) rather than a bare `unwrap`. Minimal
version: a `class ApiListResponse` with a method returning the items; services use it.
Keep it small — don't over-engineer.

> Reviewer: "The correct form should use a class for the expected response."

---

## Order of work (each step leaves the repo green)

0. **Correction 0 FIRST** — translate the whole repo to English, run `pytest -v` + all
   self-checks. Don't start the rest until the repo is fully English (avoids renaming twice).
1. Correction 1 (create `shared/utils/parsing.py`, move the 5 helpers, fix imports) → run checks.
2. Correction 2 (`AlarmRow` to its own file) → run checks.
3. Correction 3 (`FakeClient` out of the test) → run `pytest`.
4. Correction 4 (telemetry_map data-only) → run checks.
5. Correction 7 (descriptive params) → run checks.
6. Correction 8 (.env for EDGE_PYTHON etc.) → run checks.
7. Correction 6 (timeouts + retry) → run checks.
8. Correction 5 (split auth classes) → run checks (bigger; do carefully).
9. Correction 9 (split long monitor functions) → import-check monitors.
10. Correction 10 (response class) → run `pytest`.

After all: full `pytest -v` + all self-checks, confirm green, then push and reply on the PR.

## Note on `tools/probar.py`

The reviewer ALSO asked "why do we have this file / is it necessary?" — that is a
**question to answer in the PR conversation**, not a code change. Do NOT delete `probar.py`.
It is the operational command that orchestrates injection + cross-layer verification, and
the pytest tests reuse its logic (`verify_alarms`, `run_scene`). See the separate reply.
