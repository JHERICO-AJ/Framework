# Arquitectura propuesta — Framework de QA de OmniOps

> **Dos frameworks, un repo.** `framework_ui/` usa **Page Object Model (POM)**.
> `framework_api/` usa **Service Object Model (SOM)** — el hermano gemelo de POM
> para APIs. Los dos se apoyan en un `shared/` común. Nada más.

Objetivo: que cualquiera abra el repo, entienda en 5 minutos dónde está cada cosa
y sepa exactamente dónde crear la automatización de algo nuevo — sin preguntar.

---

## 0. Qué cambia respecto a hoy (y por qué)

Lo que ya está bien y **se conserva**: `config.py` central, `core/` como
fundación compartida, POM incipiente en `ui/pages/`, el oráculo diferencial
(simulador → API → UI), los `--self-check` de cada módulo (excelente idea),
`docs/`.

Lo que cambia:

| Hoy | Problema | Propuesta |
|---|---|---|
| `alarms/api.py` + `calc/check_pcs_power.py` hablan HTTP cada uno por su lado | el transporte (URL, token, timeout, reintentos) se repite | **un** `ApiClient` + **un service por dominio** (SOM) |
| Guía anterior: `api/clients/` **y** `api/controllers/` | dos niveles para lo mismo; "controller" es palabra de MVC, confunde | **un solo nivel**: `services/`. Si un flujo cruza dominios, va al test o a `domain/` |
| Respuestas de la API como `dict` (`d.get("alarmRuleId")`) | los tests indexan JSON crudo; un rename de campo rompe en 10 lugares | `models/` con `@dataclass` (DTO). El JSON se parsea **una vez** |
| Guía anterior: árbol `ui/locators/` espejando `ui/pages/` | dos árboles que hay que navegar y mantener sincronizados; se desincronizan solos | locators **al lado** de su page (`monitoring/monitoring_locators.py`). Sigue separado, pero a un archivo de distancia |
| `alarms/`, `calc/` mezclan dominio + red | el dominio puro no se puede testear sin el stack prendido | `shared/domain/` **sin red**: catálogo, oráculo, veredicto |
| `omniops_login.txt` con la contraseña en la raíz | credencial en texto plano, fácil de subir por error | variables de entorno + `.env` (gitignored), `.env.example` versionado |
| `_load_creds()` duplicado en `core/auth.py` y `ui/ui_reader.py` | dos fuentes de verdad para lo mismo | una sola en `shared/config/credentials.py` |
| `UiSession` construye Playwright a mano; tests hacen `time.sleep(2)` | el ciclo de vida del browser vive dentro de la lógica de lectura; sleeps fijos = flaky | **fixtures de pytest** para browser/página/sesión; auto-wait de Playwright, cero `sleep` |
| Nombres mezclados (`leer_pcs_power`, `read_sim_total_kw`, `esperar_carga`) | cuesta adivinar cómo se llama algo | **código en inglés, comentarios y docs en español** |
| `core/reporter.py` reporta corridas de tests | reinventa lo que pytest ya hace | pytest + `pytest-html` para tests; el `Reporter` queda **solo** para los monitores en vivo |

---

## 1. Los dos patrones (esto es todo lo que hay que entender)

### UI → Page Object Model

Una clase por pantalla. La clase guarda **acciones**; los selectores viven en su
archivo `*_locators.py` al lado.

```
Test  ->  Page (acciones)  ->  Locators (selectores)  ->  Playwright
```

- **Page** = una pantalla/URL completa (`MonitoringPage`).
- **Component** = un pedazo reutilizable dentro de una página (`PowerCard`,
  `AlarmsTable`). Si aparece en dos pantallas, es un component.
- **Locators** = solo strings. Cero lógica.
- El test **nunca** ve un selector.

### API → Service Object Model (SOM)

Exactamente el mismo espíritu que POM, un nivel más abajo:

```
Test  ->  Service (endpoints de un dominio)  ->  ApiClient (transporte)  ->  HTTP
                     |
                     v
                  Model (dataclass)
```

- **`ApiClient`** = el *cómo*. Un solo archivo: base URL, header de auth,
  timeout, reintento en 401, parseo de JSON, log. Nadie más hace HTTP.
- **`Service`** = el *qué*. Un service por dominio de la API
  (`MonitoringService`, `AlarmsService`). Sus métodos son los endpoints de ese
  dominio y **devuelven models, no dicts**.
- **`Model`** = un `@dataclass` por recurso (`Alarm`, `SiteSummary`) con un
  `from_json()`. Es el único lugar que conoce los nombres de campo del backend.

**Equivalencia mental** (por eso es fácil): `Page` ↔ `Service`,
`locators` ↔ `models`, `Playwright` ↔ `ApiClient`.

**Regla anti-complejidad:** un service = un dominio. Si un flujo necesita dos
services (ej: "traer el summary y las alarmas del mismo sitio"), eso **no** crea
una capa nueva: vive en el test o, si es lógica de negocio pura, en
`shared/domain/`.

---

## 2. El árbol completo

```
omniops-qa/
│
├── .env.example                    # plantilla de credenciales/entorno (SÍ se versiona)
├── .env                            # el real (gitignored, NUNCA se sube)
├── conftest.py                     # fixtures raíz (settings, credenciales)
├── pytest.ini
├── requirements.txt
├── README.md   ARQUITECTURA.md     # cómo correr / dónde está cada cosa
│
├── shared/                         # ── NÚCLEO COMÚN (lo usan los dos frameworks)
│   ├── config/
│   │   ├── settings.py               # TODA la config, con override por variable de entorno
│   │   └── credentials.py            # única lectura de credenciales (.env)
│   ├── auth/
│   │   └── auth.py                   # TokenAuth / CookieAuth + make_auth()
│   ├── datasource/
│   │   └── modbus_source.py          # ÚNICA lectura del simulador (+ FakeSource offline)
│   ├── domain/                       # LÓGICA PURA — cero red, testeable sola
│   │   ├── alarm_catalog.py            # las 39 alarmas: bits, umbrales, metadatos
│   │   ├── oracle.py                   # el resultado ESPERADO desde el crudo
│   │   ├── verdict.py                  # el juez (PASS / falsa / no detectada / sano)
│   │   ├── injection.py                # "alarma X" -> qué registro/bit forzar
│   │   └── power.py                    # suma de PCS, conversiones, tolerancias
│   └── utils/
│       ├── time_anchor.py            # anclaje por tiempo (comparar el mismo instante)
│       ├── omniops_time.py           # parseo de fechas de OmniOps
│       └── logger.py                 # log único (formato compartido)
│
├── framework_api/                  # ══ FRAMEWORK API — Service Object Model ══
│   ├── client/
│   │   └── api_client.py             # transporte: GET/POST, auth, timeout, retry, log
│   ├── services/                     # un service por DOMINIO de la API
│   │   ├── base_service.py             # recibe el client, helpers comunes
│   │   ├── monitoring_service.py       # GET /api/monitoring/summary/{siteId}
│   │   ├── alarms_service.py           # GET /api/events/alarms/filtered
│   │   └── dispatch_service.py         # (ejemplo de nuevo dominio)
│   └── models/                       # DTOs: el JSON se parsea UNA vez
│       ├── site_summary.py
│       └── alarm.py
│
├── framework_ui/                   # ══ FRAMEWORK UI — Page Object Model ══
│   ├── browser/
│   │   └── browser_factory.py        # abre/cierra Playwright, contexto, opciones
│   ├── base/
│   │   ├── base_page.py              # común a toda page (goto, is_on_login, wait_loaded)
│   │   └── base_component.py         # común a todo component (root locator + scope)
│   ├── components/                   # COMPONENTES REUTILIZABLES (2+ pantallas)
│   │   ├── nav_bar.py
│   │   └── data_table.py
│   └── pages/                        # ESPEJA LA NAVEGACIÓN DE OMNIOPS
│       ├── auth/
│       │   ├── login_page.py
│       │   └── login_locators.py
│       ├── fleet_overview/
│       │   ├── fleet_overview_page.py
│       │   └── fleet_overview_locators.py
│       ├── site_view/
│       │   ├── site_view_page.py
│       │   ├── site_view_locators.py
│       │   └── components/             # componentes SOLO de esta pantalla
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
├── tests/                          # ── PYTEST: espeja los módulos de la app
│   ├── conftest.py                   # fixtures de test comunes
│   ├── api/                          # solo API (rápidos, sin browser)
│   │   ├── conftest.py                 # fixture: api_client, services
│   │   ├── monitoring/test_summary.py
│   │   └── alarms_events/test_alarms_api.py
│   ├── ui/                           # solo UI (necesitan browser)
│   │   ├── conftest.py                 # fixtures: browser, page, logged_in_page
│   │   ├── monitoring/test_power_card.py
│   │   └── alarms_events/test_alarms_table.py
│   ├── cross_layer/                  # EL DIFERENCIAL: simulador vs API vs UI
│   │   ├── test_power_three_layers.py
│   │   └── test_alarms_three_layers.py
│   └── fixtures/                     # datos de prueba (JSON de ejemplo)
│       └── alarms_sample.json
│
├── monitors/                       # monitores EN VIVO (bucle, para demo/observar)
│   ├── watch_power.py                # cálculo: simulador vs API
│   ├── watch_three_layers.py         # cálculo + pantalla
│   └── reporter.py                   # reporte técnico + ejecutivo (solo monitores)
│
├── tools/                          # utilidades, NO son parte del testing
│   ├── sim_proxy.py                  # proxy Modbus para inyectar
│   ├── sim_launcher.py               # levanta el entorno
│   ├── sniff_alarms_api.py           # descubre endpoints
│   └── diagnostics/                  # scripts de investigación puntual
│
├── reports/                        # salida (gitignored)
└── docs/
    ├── BIT_MAP.md
    └── ALARMS.md
```

---

## 3. La regla de dependencias (una sola, y es sagrada)

```
                    tests/  ·  monitors/
                   /        |         \
        framework_ui   framework_api   shared/domain
                   \        |         /
                        shared/
```

1. **Las flechas apuntan hacia abajo.** `tests` y `monitors` usan todo;
   los frameworks usan `shared`; `shared` no usa a nadie hacia arriba.
2. **`framework_ui` y `framework_api` NUNCA se importan entre sí.** Si un test
   necesita los dos, el test los junta — ahí es donde viven las comparaciones
   cruzadas (`tests/cross_layer/`). Esto mantiene los dos frameworks usables por
   separado: los tests de API corren sin Playwright instalado.
3. **`shared/domain/` no toca red ni Modbus ni browser.** Recibe datos, devuelve
   veredictos. Por eso se puede testear con un `--self-check` o un unit test.
4. **Ningún selector fuera de un `*_locators.py`. Ninguna URL fuera de
   `settings.py`. Ningún `requests`/`urllib` fuera de `api_client.py`.**
   Estas tres son las que más dolor ahorran.

---

## 4. "¿Dónde pongo X?"

| Lo que tenés | Va en… |
|---|---|
| Un selector (`#id`, `.clase`, texto) | `framework_ui/pages/<módulo>/<algo>_locators.py` |
| Una acción de UI (click, leer, esperar) | `framework_ui/pages/<módulo>/<algo>_page.py` |
| Una tarjeta/tabla reutilizada en 2+ pantallas | `framework_ui/components/` |
| Una tarjeta/tabla de una sola pantalla | `framework_ui/pages/<módulo>/components/` |
| Un endpoint nuevo de un dominio existente | método nuevo en el service de ese dominio |
| Un dominio de API nuevo | `framework_api/services/<dominio>_service.py` |
| La forma de una respuesta JSON | `framework_api/models/` |
| Cambiar timeout / header / reintento HTTP | `framework_api/client/api_client.py` (**solo ahí**) |
| Una URL, puerto, tolerancia, umbral | `shared/config/settings.py` |
| Leer el simulador / dato crudo | `shared/datasource/modbus_source.py` |
| El resultado ESPERADO (la verdad) | `shared/domain/oracle.py` |
| La regla de PASA/FALLA | `shared/domain/verdict.py` |
| Un bit/umbral de una alarma | `shared/domain/alarm_catalog.py` |
| Un test que valida solo la API | `tests/api/<módulo>/` |
| Un test que valida solo la pantalla | `tests/ui/<módulo>/` |
| Un test que compara capas (sim vs API vs UI) | `tests/cross_layer/` |
| Un monitor en vivo | `monitors/` |
| Un script de investigación | `tools/` |

---

## 5. Cómo se ve el código (los 5 archivos que importan)

### `framework_api/client/api_client.py` — el transporte, una sola vez

```python
class ApiClient:
    """Único punto que habla HTTP. Auth, timeout y reintentos viven acá."""

    def __init__(self, base_url: str, auth: Auth, timeout: int = 10):
        self.base_url, self.auth, self.timeout = base_url.rstrip("/"), auth, timeout

    def get(self, path: str, **params) -> dict | list:
        log.debug("GET %s %s", path, params)
        return self.auth.authorized_get(f"{self.base_url}{path}", params, self.timeout)
```

### `framework_api/models/alarm.py` — el JSON se parsea una vez

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

> Si el backend renombra `alarmRuleId`, se toca **una línea**.

### `framework_api/services/alarms_service.py` — el dominio

```python
class AlarmsService(BaseService):
    PATH = "/api/events/alarms/filtered"

    def get_alarms(self, site_id: str) -> list[Alarm]:
        payload = self.client.get(self.PATH, siteId=site_id)
        return [Alarm.from_json(d) for d in unwrap(payload)]

    def get_open_alarms(self, site_id: str) -> list[Alarm]:
        return [a for a in self.get_alarms(site_id) if a.is_open]

    def open_rule_ids(self, site_id: str) -> set[int]:
        return {a.rule_id for a in self.get_open_alarms(site_id)}
```

### `framework_ui/pages/monitoring/` — POM con locators al lado

```python
# monitoring_locators.py  — SOLO selectores
DEVICE_CARD     = ".device-card"
METRIC_VALUE    = ".metric-value"
PCS_POWER_LABEL = "Actual PCS Power"

# monitoring_page.py  — SOLO acciones
class MonitoringPage(BasePage):
    PATH = "/monitoring?timeRange=24h"

    def open(self) -> "MonitoringPage":
        self.goto(self.PATH)
        return self                                  # permite encadenar

    def power_card(self) -> PowerCard:
        return PowerCard(self.page)                  # delega al componente

    def read_pcs_power_kw(self) -> float | None:
        return self.power_card().value_kw()
```

### `tests/cross_layer/test_power_three_layers.py` — el diferencial, legible

```python
def test_omniops_calcula_y_muestra_bien(monitoring_service, monitoring_page, sim):
    expected_kw = sim.total_pcs_power_kw()                 # oráculo (crudo)
    api_kw      = monitoring_service.get_summary(SITE_ID).actual_pcs_power_kw
    ui_kw       = monitoring_page.read_pcs_power_kw()

    assert power.matches(expected_kw, api_kw), "el BACKEND calcula mal"
    assert power.matches(api_kw, ui_kw, tol=UI_TOL_KW), "el FRONT muestra mal"
```

Un test que se lee como una frase. Cero selectores, cero URLs, cero `sleep`,
cero JSON crudo.

---

## 6. Fixtures: el pegamento (una vez y para siempre)

```python
# tests/api/conftest.py — sin browser, rápido
@pytest.fixture(scope="session")
def api_client(settings, credentials):
    return ApiClient(settings.base_url, make_auth(settings, credentials))

@pytest.fixture(scope="session")
def alarms_service(api_client):
    return AlarmsService(api_client)

# tests/ui/conftest.py — el browser se abre UNA vez y se loguea UNA vez
@pytest.fixture(scope="session")
def logged_in_page(settings, credentials):
    with BrowserFactory(settings) as page:
        LoginPage(page).login(credentials.email, credentials.password)
        yield page

@pytest.fixture
def monitoring_page(logged_in_page):
    return MonitoringPage(logged_in_page).open()
```

Con esto, el ciclo de vida del navegador sale de la lógica de lectura (hoy vive
dentro de `UiSession`) y pasa a donde le corresponde: pytest.

---

## 7. Ejemplo end-to-end: automatizar "Dispatch Limits & Tracking"

Componente de Site View, con su endpoint. Cuatro pasos, cuatro carpetas obvias:

1. **Locators** → `framework_ui/pages/site_view/components/dispatch_limits_locators.py`
   ```python
   TABLE = ".dispatch-limits table"
   ROW   = ".dispatch-limits tbody tr"
   ```
2. **Componente** → `framework_ui/pages/site_view/components/dispatch_limits.py`
   ```python
   class DispatchLimits(BaseComponent):
       def rows(self) -> list[LimitRow]: ...
   ```
3. **API** → `framework_api/models/dispatch_limit.py` +
   `framework_api/services/dispatch_service.py`
   (el transporte ya existe: no se toca `api_client.py`)
4. **Test** → `tests/cross_layer/test_dispatch_limits.py`
   ```python
   def test_limites_coinciden(dispatch_service, site_view_page):
       assert site_view_page.dispatch_limits().rows() == \
              dispatch_service.get_limits(SITE_ID)
   ```

Nada de esto obligó a inventar una capa nueva. Ese es el test de si la
arquitectura aguanta.

---

## 8. Mapa de migración — de lo que hay hoy a esto

| Archivo actual | Va a |
|---|---|
| `config.py` | `shared/config/settings.py` (+ overrides por env) |
| `core/auth.py` | `shared/auth/auth.py` (sin `_load_creds`, eso a `credentials.py`) |
| `core/source_modbus.py` | `shared/datasource/modbus_source.py` |
| `core/timeanchor.py`, `core/omniops_time.py` | `shared/utils/` |
| `core/reporter.py` | `monitors/reporter.py` (solo monitores) |
| `calc/compare_pcs_power.py` (comparación/tolerancias) | `shared/domain/power.py` |
| `calc/compare_pcs_power.py` (lectura API) | `framework_api/services/monitoring_service.py` |
| `calc/check_pcs_power.py` | `tests/api/monitoring/test_summary.py` |
| `alarms/api.py` (clase `Alarma`) | `framework_api/models/alarm.py` |
| `alarms/api.py` (funciones de lectura) | `framework_api/services/alarms_service.py` |
| `alarms/catalog.py` · `oracle.py` · `verdict.py` · `inject.py` | `shared/domain/` |
| `ui/pages/base_page.py` | `framework_ui/base/base_page.py` |
| `ui/pages/login_page.py` | `framework_ui/pages/auth/` (page + locators) |
| `ui/pages/monitoring_page.py` | `framework_ui/pages/monitoring/` (page + locators + `power_card`) |
| `ui/ui_reader.py` (Playwright, contexto) | `framework_ui/browser/browser_factory.py` |
| `ui/ui_reader.py` (sesión, relogin, reintentos) | fixtures en `tests/ui/conftest.py` |
| `tests/test_3capas.py` | `tests/cross_layer/test_power_three_layers.py` |
| `monitors/*`, `tools/*` | igual (renombrados en inglés) |
| `omniops_login.txt` | `.env` (y `.env.example` versionado) |

**Orden sugerido** (cada paso deja el repo funcionando):
`shared/` → `framework_api/` → `framework_ui/` → `tests/` → monitores.

---

## 9. Buenas prácticas que se dan por sentadas

- **Un idioma por rol:** identificadores en inglés, comentarios y `docs/` en
  español. Hoy están mezclados y cuesta adivinar nombres.
- **Cero `time.sleep` en tests.** Playwright espera solo; para el resto,
  `expect(...).to_have_text(...)` o un helper `wait_until(cond, timeout)`.
- **Los tests no imprimen, afirman.** El `print` es de los monitores.
- **Un assert por concepto**, con mensaje que diga *dónde* está el bug
  (`"el BACKEND calcula mal"` vs `"el FRONT muestra mal"`).
- **Marcadores de pytest:** `@pytest.mark.api`, `ui`, `cross_layer`, `slow`.
  Así `pytest -m api` corre en segundos y sirve de smoke en CI.
- **`skip` explícito si el stack está apagado** (ya lo hacen: conservarlo, pero
  como fixture `require_stack` en vez de repetido en cada archivo).
- **Nada de credenciales en el repo.** `.env` gitignored, `.env.example` con las
  claves vacías.
- **`--self-check` se conserva** — es una de las mejores ideas del framework
  actual. Donde se pueda, promoverlo a unit test en `tests/` para que corra en CI.

---

## 10. Resumen en tres frases

1. `framework_ui/` = **POM**: Page (acciones) + Locators (selectores) +
   Components (piezas reutilizables), espejando los menús de OmniOps.
2. `framework_api/` = **SOM**: un `ApiClient` (transporte) + un Service por
   dominio + Models (dataclasses). Sin `controllers`, sin capas extra.
3. `shared/` = config, auth, fuente de datos cruda y **dominio puro** (oráculo,
   veredicto, catálogo). Los frameworks no se conocen entre sí; se encuentran
   solo en `tests/cross_layer/`.