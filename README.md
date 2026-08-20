# Framework de QA — OmniOps

QA automatizado para la plataforma de monitoreo BESS **OmniOps**, basado en un
**oráculo diferencial**: leemos el valor crudo del simulador Modbus de forma
*independiente* y lo comparamos contra lo que OmniOps calcula (**API**) y muestra
(**UI**). Para alarmas, además **inyectamos** condiciones a través de un proxy
Modbus y verificamos que OmniOps genere la alarma esperada.

El simulador solo expone **telemetría cruda** (temperaturas, tensiones, bits).
OmniOps es el sistema bajo prueba: convierte esa telemetría en cálculos y
alarmas. Este framework verifica que lo haga bien.

---

## Arquitectura (5 capas)

Cada capa tiene una sola responsabilidad. Las dependencias apuntan hacia abajo:
tests y monitores usan todo; `framework_api` / `framework_ui` / `domain` usan
`shared`; `shared` no depende de nada salvo `config`.

```
config (settings)                        un solo lugar: URLs, puertos, tolerancias
   └── shared/        fundaciones: auth, credenciales, fuente Modbus, domain, utils
        ├── framework_api/   capa API (SOM): ApiClient + services + models
        ├── framework_ui/    capa UI (POM): browser factory + pages + locators
        └── domain/          lógica pura: qué DEBERÍA pasar (oráculo, reglas)
             └── tests/       las pruebas (el assert vive acá) + monitors/ (vista en vivo)
```

| Capa | Carpeta | Responsabilidad |
|------|---------|-----------------|
| Config | `shared/config/` | `settings.py` (config central) + `credentials.py` (.env) |
| Core | `shared/` | auth, fuente Modbus, utilidades de tiempo, logger |
| Domain | `shared/domain/` | lógica pura: catálogo de alarmas, oráculo, verdict, inyección, potencia |
| API | `framework_api/` | `ApiClient` (transporte) + `services/` + `models/` (dataclasses) |
| UI | `framework_ui/` | `BrowserFactory` + `pages/` (page objects) + locators al lado de cada page |
| Tests | `tests/` | `api/`, `ui/`, `cross_layer/` — el assert vive acá |
| Monitores | `monitors/` | observadores en vivo (bucle, para demo/debug) — observan, no afirman |
| Tools | `tools/` | proxy, launcher, `probar` (CLI de inyección), sniffer, diagnósticos |

---

## Instalación

```bash
# 1. Entorno virtual
python -m venv venv
venv\Scripts\Activate.ps1          # Windows PowerShell
# source venv/bin/activate         # Linux / macOS

# 2. Dependencias
pip install -r requirements.txt
playwright install chromium         # navegador para la capa UI

# 3. Credenciales  (nunca subir el .env)
copy .env.example .env              # Windows  (cp en Linux/macOS)
# editá .env y poné OMNIOPS_EMAIL y OMNIOPS_PASSWORD
```

El repo del simulador (`omniops-bess-edge`) tiene que estar **al lado** de este
proyecto (misma carpeta padre). Si está en otro lado, ajustá `SIM_REPO_DIR` en
`shared/config/settings.py`.

---

## Correr las pruebas

```bash
# Offline (sin stack): los unit tests pasan, los de stack se saltan
pytest -v

# En vivo (necesita el stack + OmniOps): el diferencial entre capas
pytest tests/cross_layer -v

# Reporte HTML (verde/rojo de cada prueba, para compartir o guardar)
pytest --html=reports/report.html --self-contained-html
```

Grupos de pruebas (markers): `api`, `ui`, `cross_layer`.

```bash
pytest -m api          # solo API (rápidas, sin navegador)
pytest -m cross_layer  # simulador vs API vs UI
```

El **reporte** muestra, por cada prueba, si pasó o falló, con el detalle y —si
falló— el error. Se regenera en cada corrida con `--html=...`.

---

## Inyección de alarmas

Dos comandos. Docker + OmniOps tienen que estar prendidos aparte.

```bash
python -m tools.arrancar_alarmas          # levanta simulador(5021) + proxy(5020) + edge
python -m tools.probar 16 --vivo          # inyecta la alarma 16, verifica (causa + API + hora) y limpia
python -m tools.probar 16 --at 10 --hasta 30 --vivo   # escena temporal
```

Flujo de datos: `simulador (5021) -> proxy (5020) -> edge -> Event Hub -> OmniOps`.
El proxy inyecta la condición en el stream Modbus; OmniOps debe entonces generar
la alarma. Los timestamps de OmniOps vienen en **UTC**; el framework compara en
UTC y muestra en hora local.

---

## Monitores en vivo (observan, no afirman)

```bash
python -m monitors.watch_power           # simulador vs API (potencia)
python -m monitors.watch_three_layers    # simulador vs API vs UI
python -m monitors.watch_alarms          # alarmas en vivo (inyectás desde otra terminal)
```

---

## ¿Dónde pongo cada cosa?

| Lo que tenés | Va en |
|---|---|
| Un selector de UI | `framework_ui/pages/<módulo>/*_locators.py` |
| Una acción/lectura de UI | `framework_ui/pages/<módulo>/*_page.py` |
| Un componente reutilizable (tabla, tarjeta) | `framework_ui/pages/<módulo>/components/` |
| Una llamada HTTP cruda | `framework_api/services/` (vía `ApiClient`) |
| Un modelo del JSON | `framework_api/models/` (dataclass con `from_json`) |
| Lógica de negocio / "valor esperado" | `shared/domain/` |
| Un valor de config (URL, puerto, umbral) | `shared/config/settings.py` |
| Una verificación (verde/rojo) | `tests/` (el assert acá) |
| Un monitor en vivo | `monitors/` |
| Un script de investigación | `tools/` |

Regla práctica: si algo necesita que el sistema le responda, no es `domain`. Si
cruza capas (simulador + API, o API + UI), es `cross_layer` (un test) o un
comando de `tools/`. La capa API nunca debe saber de Modbus.

---

## Self-checks offline

La mayoría de los módulos de dominio validan su propia lógica sin el stack:

```bash
python -m shared.domain.oracle --self-check
python -m shared.domain.verdict --self-check
python -m shared.domain.injection --self-check
python -m shared.domain.power --self-check
python -m tools.sim_proxy --self-check
```

---

## Notas

- `pymodbus` fijado en **3.7.4** — tiene que coincidir con el simulador. Las
  versiones nuevas rompen `ModbusSlaveContext`.
- El `.env` (credenciales reales) está en `.gitignore`; solo se sube `.env.example`.
- **Cómo y por qué funciona (a fondo): ver `docs/COMO_FUNCIONA.md`** — explica el
  oráculo diferencial, el proxy paso a paso, y los hallazgos de QA (OmniOps evalúa
  por telemetría y no cierra alarmas). Lectura recomendada antes de tocar el código.
- Ver `MIGRATION_STATUS.md` para el historial de migración y `ARQUITECTURA.md`
  para el detalle de la arquitectura.
