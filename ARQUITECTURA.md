# Proposed architecture — OmniOps QA Framework

> **Two frameworks, one repo.** `framework_ui/` uses **Page Object Model
> (POM)**. `framework_api/` uses **Service Object Model (SOM)** — POM's twin
> for APIs. Both rest on a common `shared/`. Nothing more.

Goal: anyone can open the repo, understand in 5 minutes where everything is,
and know exactly where to create the automation for something new — without
asking.

---

## 0. What changes compared to today (and why)

What's already good and **stays**: central `config.py`, `core/` as the
shared foundation, incipient POM in `ui/pages/`, the differential oracle
(simulator → API → UI), each module's `--self-check` (a great idea), `docs/`.

What changes:

| Today | Problem | Proposal |
|---|---|---|
| `alarms/api.py` + `calc/check_pcs_power.py` each talk HTTP on their own | the transport (URL, token, timeout, retries) is duplicated | **one** `ApiClient` + **one service per domain** (SOM) |
| Previous guide: `api/clients/` **and** `api/controllers/` | two levels for the same thing; "controller" is an MVC word, confusing | **a single level**: `services/`. If a flow crosses domains, it goes in the test or in `domain/` |
| API responses as `dict` (`d.get("alarmRuleId")`) | tests index raw JSON; a field rename breaks in 10 places | `models/` with `@dataclass` (DTO). The JSON is parsed **once** |
| Previous guide: a `ui/locators/` tree mirroring `ui/pages/` | two trees to navigate and keep in sync; they drift apart on their own | locators **next to** their page (`monitoring/monitoring_locators.py`). Still separate, but one file away |
| `alarms/`, `calc/` mix domain + network | pure domain logic can't be tested without the stack running | `shared/domain/` **with no network**: catalog, oracle, verdict |
| `omniops_login.txt` with the password in the repo root | plaintext credential, easy to commit by mistake | environment variables + `.env` (gitignored), versioned `.env.example` |
| `_load_creds()` duplicated in `core/auth.py` and `ui/ui_reader.py` | two sources of truth for the same thing | a single one in `shared/config/credentials.py` |
| `UiSession` builds Playwright by hand; tests do `time.sleep(2)` | the browser lifecycle lives inside the reading logic; fixed sleeps = flaky | **pytest fixtures** for browser/page/session; Playwright auto-wait, zero `sleep` |
| Mixed naming (`leer_pcs_power`, `read_sim_total_kw`, `esperar_carga`) | hard to guess what something is called | **code in English, comments and docs in English** |
| `core/reporter.py` reports test runs | reinvents what pytest already does | pytest + `pytest-html` for tests; `Reporter` is kept **only** for the live monitors |

---

## 1. The two patterns (this is everything you need to understand)

### UI → Page Object Model

One class per screen. The class holds **actions**; the selectors live in its
`*_locators.py` file right next to it.

```
Test  ->  Page (actions)  ->  Locators (selectors)  ->  Playwright
```

- **Page** = a full screen/URL (`MonitoringPage`).
- **Component** = a reusable piece within a page (`PowerCard`,
  `AlarmsTable`). If it appears on two screens, it's a component.
- **Locators** = strings only. Zero logic.
- The test **never** sees a selector.

### API → Service Object Model (SOM)

Exactly the same spirit as POM, one level down:

```
Test  ->  Service (endpoints of a domain)  ->  ApiClient (transport)  ->  HTTP
                     |
                     v
                  Model (dataclass)
```

- **`ApiClient`** = the *how*. A single file: base URL, auth header,
  timeout, retry on 401, JSON parsing, log. No one else does HTTP.
- **`Service`** = the *what*. One service per API domain
  (`MonitoringService`, `AlarmsService`). Its methods are that domain's
  endpoints and **return models, not dicts**.
- **`Model`** = one `@dataclass` per resource (`Alarm`, `SiteSummary`) with a
  `from_json()`. It's the only place that knows the backend's field names.

**Mental equivalence** (which makes it easy): `Page` ↔ `Service`,
`locators` ↔ `models`, `Playwright` ↔ `ApiClient`.

**Anti-complexity rule:** one service = one domain. If a flow needs two
services (e.g. "fetch the summary and the alarms for the same site"), that
does **not** create a new layer: it lives in the test or, if it's pure
business logic, in `shared/domain/`.

---

## 2. The full tree

```
omniops-qa/
│
├── .env.example                    # credentials/environment template (IS versioned)
├── .env                            # the real one (gitignored, NEVER committed)
├── conftest.py                     # root fixtures (settings, credentials)
├── pytest.ini
├── requirements.txt
├── README.md   ARQUITECTURA.md     # how to run / where everything is
│
├── shared/                         # ── COMMON CORE (used by both frameworks)
│   ├── config/
│   │   ├── settings.py               # ALL config, with environment-variable override
│   │   └── credentials.py            # the single place credentials are read (.env)
│   ├── auth/
│   │   ├── base.py                   # Auth contract + shared HTTP helpers (timeout, retry)
│   │   ├── token_auth.py             # TokenAuth (email/password)
│   │   ├── cookie_auth.py            # CookieAuth (browser session cookie)
│   │   └── factory.py                # make_auth() picks the right one
│   ├── datasource/
│   │   └── modbus_source.py          # THE ONLY place that reads the simulator (+ offline FakeSource)
│   ├── domain/                       # PURE LOGIC — zero network, testable on its own
│   │   ├── alarm_catalog.py            # the 39 alarms: bits, thresholds, metadata
│   │   ├── oracle.py                   # the EXPECTED result, from the raw data
│   │   ├── verdict.py                  # the judge (PASS / false / not detected / healthy)
│   │   ├── injection.py                # "alarm X" -> which register/bit to force
│   │   └── power.py                    # PCS sum, conversions, tolerances
│   └── utils/
│       ├── time_anchor.py            # time anchoring (comparing the same instant)
│       ├── omniops_time.py           # parsing OmniOps dates
│       └── logger.py                 # single logger (shared format)
│
├── framework_api/                  # ══ API FRAMEWORK — Service Object Model ══
│   ├── client/
│   │   └── api_client.py             # transport: GET/POST, auth, timeout, retry, log
│   ├── services/                     # one service per API DOMAIN
│   │   ├── base_service.py             # receives the client, common helpers
│   │   ├── monitoring_service.py       # GET /api/monitoring/summary/{siteId}
│   │   ├── alarms_service.py           # GET /api/events/alarms/filtered
│   │   └── dispatch_service.py         # (example of a new domain)
│   └── models/                       # DTOs: the JSON is parsed ONCE
│       ├── site_summary.py
│       └── alarm.py
│
├── framework_ui/                   # ══ UI FRAMEWORK — Page Object Model ══
│   ├── browser/
│   │   └── browser_factory.py        # opens/closes Playwright, context, options
│   ├── base/
│   │   ├── base_page.py              # common to every page (goto, is_on_login, wait_loaded)
│   │   └── base_component.py         # common to every component (root locator + scope)
│   ├── components/                   # REUSABLE COMPONENTS (2+ screens)
│   │   ├── nav_bar.py
│   │   └── data_table.py
│   └── pages/                        # MIRRORS OMNIOPS'S NAVIGATION
│       ├── auth/
│       │   ├── login_page.py
│       │   └── login_locators.py
│       ├── fleet_overview/
│       │   ├── fleet_overview_page.py
│       │   └── fleet_overview_locators.py
│       ├── site_view/
│       │   ├── site_view_page.py
│       │   ├── site_view_locators.py
│       │   └── components/             # components ONLY for this screen
│       │       ├── dispatch_limits.py
│       │       └── dispatch_limits_locators.py
│       ├── monitoring/
│       │   ├── monitoring_page.py
│       │   ├── monitoring_locators.py
│       │   └── components/
│       │       ├── power_card.py
│       │       └── power_card_locators.py
│       └── alarms_events/
│           ├── alarms_page.py
│           ├── alarms_locators.py
│           └── components/
│               ├── alarms_table.py
│               └── alarms_table_locators.py
│
├── tests/                          # ── PYTEST: mirrors the app's modules
│   ├── conftest.py                   # common test fixtures
│   ├── api/                          # API only (fast, no browser)
│   │   ├── conftest.py                 # fixture: api_client, services
│   │   ├── monitoring/test_summary.py
│   │   └── alarms_events/test_alarms_api.py
│   ├── ui/                           # UI only (needs a browser)
│   │   ├── conftest.py                 # fixtures: browser, page, logged_in_page
│   │   ├── monitoring/test_power_card.py
│   │   └── alarms_events/test_alarms_table.py
│   ├── cross_layer/                  # THE DIFFERENTIAL: simulator vs API vs UI
│   │   ├── test_power_three_layers.py
│   │   └── test_alarms_three_layers.py
│   └── fixtures/                     # test data (sample JSON)
│       └── alarms_sample.json
│
├── monitors/                       # LIVE monitors (loop, for demo/observing)
│   ├── watch_power.py                # calculation: simulator vs API
│   ├── watch_three_layers.py         # calculation + screen
│   └── reporter.py                   # technical + executive report (monitors only)
│
├── tools/                          # utilities, NOT part of testing
│   ├── sim_proxy.py                  # Modbus proxy for injection
│   ├── sim_launcher.py               # brings up the environment
│   ├── sniff_alarms_api.py           # discovers endpoints
│   └── diagnostics/                  # ad hoc investigation scripts
│
├── reports/                        # output (gitignored)
└── docs/
    ├── BIT_MAP.md
    └── ALARMS.md
```

---

## 3. The dependency rule (just one, and it's sacred)

```
                    tests/  ·  monitors/
                   /        |         \
        framework_ui   framework_api   shared/domain
                   \        |         /
                        shared/
```

1. **Arrows point downward.** `tests` and `monitors` use everything;
   the frameworks use `shared`; `shared` uses no one above it.
2. **`framework_ui` and `framework_api` NEVER import each other.** If a test
   needs both, the test brings them together — that's where cross-layer
   comparisons live (`tests/cross_layer/`). This keeps both frameworks
   usable on their own: API tests run without Playwright installed.
3. **`shared/domain/` never touches network, Modbus, or the browser.** It
   receives data, returns verdicts. That's why it can be tested with a
   `--self-check` or a unit test.
4. **No selector outside a `*_locators.py`. No URL outside `settings.py`.
   No `requests`/`urllib` outside `api_client.py`.** These three save the
   most pain.

---

## 4. "Where do I put X?"

| What you have | Goes in… |
|---|---|
| A selector (`#id`, `.class`, text) | `framework_ui/pages/<module>/<thing>_locators.py` |
| A UI action (click, read, wait) | `framework_ui/pages/<module>/<thing>_page.py` |
| A card/table reused on 2+ screens | `framework_ui/components/` |
| A card/table for a single screen | `framework_ui/pages/<module>/components/` |
| A new endpoint on an existing domain | a new method on that domain's service |
| A new API domain | `framework_api/services/<domain>_service.py` |
| The shape of a JSON response | `framework_api/models/` |
| Changing HTTP timeout / header / retry | `framework_api/client/api_client.py` (**only there**) |
| A URL, port, tolerance, threshold | `shared/config/settings.py` |
| Reading the simulator / raw data | `shared/datasource/modbus_source.py` |
| The EXPECTED result (the truth) | `shared/domain/oracle.py` |
| The PASS/FAIL rule | `shared/domain/verdict.py` |
| An alarm's bit/threshold | `shared/domain/alarm_catalog.py` |
| A test that validates only the API | `tests/api/<module>/` |
| A test that validates only the screen | `tests/ui/<module>/` |
| A test that compares layers (sim vs API vs UI) | `tests/cross_layer/` |
| A live monitor | `monitors/` |
| An investigation script | `tools/` |

---

## 5. What the code looks like (the 5 files that matter)

### `framework_api/client/api_client.py` — the transport, done once

```python
class ApiClient:
    """The single point that speaks HTTP. Auth, timeout and retries live here."""

    def __init__(self, base_url: str, auth: Auth, timeout: int = 10):
        self.base_url, self.auth, self.timeout = base_url.rstrip("/"), auth, timeout

    def get(self, path: str, **params) -> dict | list:
        log.debug("GET %s %s", path, params)
        return self.auth.authorized_get(f"{self.base_url}{path}", params, self.timeout)
```

### `framework_api/models/alarm.py` — the JSON is parsed once

```python
@dataclass(frozen=True)
class Alarm:
    rule_id: int
    name: str
    severity: str
    status: str
    device_name: str
    first_occurred: datetime | None
    last_occurred: datetime | None

    @property
    def is_open(self) -> bool:
        return self.status.strip().lower() == "open"

    @classmethod
    def from_json(cls, d: dict) -> "Alarm":
        return cls(
            rule_id=d["alarmRuleId"],
            name=d.get("alarm", ""),
            severity=d.get("severity", ""),
            status=d.get("status", ""),
            device_name=d.get("deviceName", ""),
            first_occurred=parse_dt(d.get("firstOccurred")),
            last_occurred=parse_dt(d.get("lastOccurred")),
        )
```

> If the backend renames `alarmRuleId`, only **one line** needs to change.

### `framework_api/services/alarms_service.py` — the domain

```python
class AlarmsService(BaseService):
    PATH = "/api/events/alarms/filtered"

    def get_alarms(self, site_id: str) -> list[Alarm]:
        payload = self.client.get(self.PATH, siteId=site_id)
        return [Alarm.from_json(d) for d in ApiListResponse(payload).items()]

    def get_open_alarms(self, site_id: str) -> list[Alarm]:
        return [a for a in self.get_alarms(site_id) if a.is_open]

    def open_rule_ids(self, site_id: str) -> set[int]:
        return {a.rule_id for a in self.get_open_alarms(site_id)}
```

### `framework_ui/pages/monitoring/` — POM with locators alongside

```python
# monitoring_locators.py  — SELECTORS ONLY
DEVICE_CARD     = ".device-card"
METRIC_VALUE    = ".metric-value"
PCS_POWER_LABEL = "Actual PCS Power"

# monitoring_page.py  — ACTIONS ONLY
class MonitoringPage(BasePage):
    PATH = "/monitoring?timeRange=24h"

    def open(self) -> "MonitoringPage":
        self.goto(self.PATH)
        return self                                  # allows chaining

    def power_card(self) -> PowerCard:
        return PowerCard(self.page)                  # delegates to the component

    def read_pcs_power_kw(self) -> float | None:
        return self.power_card().value_kw()
```

### `tests/cross_layer/test_power_three_layers.py` — the differential, readable

```python
def test_omniops_calculates_and_displays_correctly(monitoring_service, monitoring_page, sim):
    expected_kw = sim.total_pcs_power_kw()                 # oracle (raw data)
    api_kw      = monitoring_service.get_summary(SITE_ID).actual_pcs_power_kw
    ui_kw       = monitoring_page.read_pcs_power_kw()

    assert power.matches(expected_kw, api_kw), "the BACKEND calculates it wrong"
    assert power.matches(api_kw, ui_kw, tol=UI_TOL_KW), "the FRONTEND displays it wrong"
```

A test that reads like a sentence. Zero selectors, zero URLs, zero `sleep`,
zero raw JSON.

---

## 6. Fixtures: the glue (once and for all)

```python
# tests/api/conftest.py — no browser, fast
@pytest.fixture(scope="session")
def api_client(settings, credentials):
    return ApiClient(settings.base_url, make_auth(settings, credentials))

@pytest.fixture(scope="session")
def alarms_service(api_client):
    return AlarmsService(api_client)

# tests/ui/conftest.py — the browser opens ONCE and logs in ONCE
@pytest.fixture(scope="session")
def logged_in_page(settings, credentials):
    with BrowserFactory(settings) as page:
        LoginPage(page).login(credentials.email, credentials.password)
        yield page

@pytest.fixture
def monitoring_page(logged_in_page):
    return MonitoringPage(logged_in_page).open()
```

With this, the browser lifecycle moves out of the reading logic (today it
lives inside `UiSession`) and into where it belongs: pytest.

---

## 7. End-to-end example: automating "Dispatch Limits & Tracking"

A Site View component, with its endpoint. Four steps, four obvious folders:

1. **Locators** → `framework_ui/pages/site_view/components/dispatch_limits_locators.py`
   ```python
   TABLE = ".dispatch-limits table"
   ROW   = ".dispatch-limits tbody tr"
   ```
2. **Component** → `framework_ui/pages/site_view/components/dispatch_limits.py`
   ```python
   class DispatchLimits(BaseComponent):
       def rows(self) -> list[LimitRow]: ...
   ```
3. **API** → `framework_api/models/dispatch_limit.py` +
   `framework_api/services/dispatch_service.py`
   (the transport already exists: `api_client.py` isn't touched)
4. **Test** → `tests/cross_layer/test_dispatch_limits.py`
   ```python
   def test_limits_match(dispatch_service, site_view_page):
       assert site_view_page.dispatch_limits().rows() == \
              dispatch_service.get_limits(SITE_ID)
   ```

None of this required inventing a new layer. That's the test of whether the
architecture holds up.

---

## 8. Migration map — from what exists today to this

| Current file | Goes to |
|---|---|
| `config.py` | `shared/config/settings.py` (+ env overrides) |
| `core/auth.py` | `shared/auth/` package — `base.py`/`token_auth.py`/`cookie_auth.py`/`factory.py` (without `_load_creds`, that goes to `credentials.py`) |
| `core/source_modbus.py` | `shared/datasource/modbus_source.py` |
| `core/timeanchor.py`, `core/omniops_time.py` | `shared/utils/` |
| `core/reporter.py` | `monitors/reporter.py` (monitors only) |
| `calc/compare_pcs_power.py` (comparison/tolerances) | `shared/domain/power.py` |
| `calc/compare_pcs_power.py` (API reading) | `framework_api/services/monitoring_service.py` |
| `calc/check_pcs_power.py` | `tests/api/monitoring/test_summary.py` |
| `alarms/api.py` (class `Alarma`) | `framework_api/models/alarm.py` |
| `alarms/api.py` (reading functions) | `framework_api/services/alarms_service.py` |
| `alarms/catalog.py` · `oracle.py` · `verdict.py` · `inject.py` | `shared/domain/` |
| `ui/pages/base_page.py` | `framework_ui/base/base_page.py` |
| `ui/pages/login_page.py` | `framework_ui/pages/auth/` (page + locators) |
| `ui/pages/monitoring_page.py` | `framework_ui/pages/monitoring/` (page + locators + `power_card`) |
| `ui/ui_reader.py` (Playwright, context) | `framework_ui/browser/browser_factory.py` |
| `ui/ui_reader.py` (session, relogin, retries) | fixtures in `tests/ui/conftest.py` |
| `tests/test_3capas.py` | `tests/cross_layer/test_power_three_layers.py` |
| `monitors/*`, `tools/*` | same (renamed to English) |
| `omniops_login.txt` | `.env` (and versioned `.env.example`) |

**Suggested order** (each step leaves the repo working):
`shared/` → `framework_api/` → `framework_ui/` → `tests/` → monitors.

---

## 9. Best practices taken for granted

- **One language per role:** identifiers in English, comments and `docs/`
  in English. Today they're mixed and it's hard to guess names.
- **Zero `time.sleep` in tests.** Playwright waits on its own; for
  everything else, `expect(...).to_have_text(...)` or a `wait_until(cond,
  timeout)` helper.
- **Tests don't print, they assert.** `print` belongs to the monitors.
- **One assert per concept**, with a message that says *where* the bug is
  (`"the BACKEND calculates it wrong"` vs `"the FRONTEND displays it
  wrong"`).
- **Pytest markers:** `@pytest.mark.api`, `ui`, `cross_layer`, `slow`.
  So `pytest -m api` runs in seconds and serves as a smoke test in CI.
- **Explicit `skip` if the stack is down** (already done: keep it, but as a
  `require_stack` fixture instead of repeating it in every file).
- **No credentials in the repo.** `.env` gitignored, `.env.example` with
  empty keys.
- **`--self-check` is kept** — it's one of the current framework's best
  ideas. Where possible, promote it to a unit test in `tests/` so it runs in
  CI.

---

## 10. Summary in three sentences

1. `framework_ui/` = **POM**: Page (actions) + Locators (selectors) +
   Components (reusable pieces), mirroring OmniOps's menus.
2. `framework_api/` = **SOM**: one `ApiClient` (transport) + one Service per
   domain + Models (dataclasses). No `controllers`, no extra layers.
3. `shared/` = config, auth, raw data source, and **pure domain** (oracle,
   verdict, catalog). The frameworks don't know about each other; they only
   meet in `tests/cross_layer/`.
