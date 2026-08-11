# Framework de validación de OmniOps

Valida, **en tiempo real**, que OmniOps calcula bien la telemetría del BESS y que
la muestra bien en pantalla. Compara de forma independiente el dato crudo del
**simulador** contra lo que produce OmniOps, en **tres capas**:

```
  Simulador (Modbus)  --calcula-->  OmniOps API  --muestra-->  Pantalla (UI)
        \___________ oráculo ___________/               \____ Playwright ___/
                 CAPA CÁLCULO                              CAPA PANTALLA
```

- **Capa cálculo** (simulador → API): ¿OmniOps calcula bien la potencia? Sumamos
  la potencia de los PCS desde el crudo y la comparamos contra `actualPcsPower`.
- **Capa pantalla** (API → UI): ¿la UI muestra bien lo que la API calculó?
  Leemos el número renderizado con un navegador real y lo comparamos contra la API.

La métrica validada hoy es la **potencia total de PCS** (`actualPcsPower`).

---

## 1. Requisitos

- **Python 3.11 o más nuevo** (probado en 3.14).
- El **simulador BESS** corriendo (proyecto `omniops-bess-edge`).
- **OmniOps** corriendo en local (frontend en `http://localhost:5173`).
- Una cuenta de OmniOps de **email/contraseña** (para el login automático).

## 2. Instalación

Desde una terminal, dentro de esta carpeta:

```bash
# (opcional pero recomendado) entorno aislado
python -m venv venv
venv\Scripts\activate            # Windows
# source venv/bin/activate       # Mac / Linux

# instalar dependencias
pip install -r requirements.txt

# bajar el navegador que usa Playwright (una sola vez, tarda unos minutos)
playwright install chromium
```

## 3. Credenciales (una sola vez)

El login es automático, pero necesita tus datos. Copiá el archivo de ejemplo:

```
omniops_login.example.txt   ->   omniops_login.txt
```

y editá `omniops_login.txt` con tu cuenta:

```
email=tu_correo@omniops.com
password=tu_clave
```

> ⚠️ **`omniops_login.txt` NUNCA se sube** (tiene tu contraseña). Ya está en el
> `.gitignore`. No lo compartas.

## 4. Cómo correr las pruebas

Antes de cualquier prueba: **prendé el simulador** (en su propia terminal) y
**OmniOps**.

```bash
# terminal del simulador (dejar corriendo)
py .\utils\launch_site.py 10000000-0000-0000-0000-000000000001 5020 7
```

Hay tres formas de correr, de la más simple a la más completa:

### a) Comparación puntual (simulador vs API)
Una sola comparación, para probar la conexión.
```bash
python compare_pcs_power.py
```

### b) Monitor en vivo de CÁLCULO (simulador vs API) — sin navegador
Valida el cálculo en tiempo real, anclado por tiempo, y guarda reporte.
Es liviano: **no necesita Playwright**.
```bash
python watch_compare_anchored.py
```

### c) Monitor en vivo de las TRES CAPAS (cálculo + pantalla)
Lo completo: valida cálculo y pantalla a la vez. **Necesita Playwright.**
```bash
python watch_3capas.py
```

En todos: **Ctrl+C** para parar. Los monitores dejan un reporte en `reportes/`.

## 5. Cómo leer los resultados

Cada línea del monitor muestra el veredicto por capa:

```
[20:31:20]  cálculo:PASA   pantalla:PASA    (api=  2486.0  ui=2486.0 kW)
```

- **cálculo:PASA** → OmniOps calculó bien (coincide con el oráculo).
- **pantalla:PASA** → la UI muestra bien lo que la API calculó.
- **descartada** → no se pudo comparar de forma confiable (desfase de tiempo);
  no cuenta como error.
- **FALLA** → no coincidió *y* la medición fue confiable → **revisar, posible bug**.

El primer eslabón que falla te dice *dónde* está el problema: si falla `cálculo`
es el backend; si falla `pantalla` es el front.

## 6. Qué hace cada archivo

| Archivo | Qué es / qué valida |
|---|---|
| `auth.py` | Login automático a OmniOps. Renueva el token solo. Dos modos: email/contraseña (token) y cookie (Microsoft). |
| `check_pcs_power.py` | Lee la API y chequea que `actualPcsPower` esté presente, en rango y fresco. Provee la URL y utilidades a los demás. |
| `compare_pcs_power.py` | El **oráculo**: lee el simulador por Modbus, suma la potencia de los 3 PCS, y la compara contra la API. Es la capa cálculo. |
| `ui_reader.py` | Lee el número renderizado en la pantalla con Playwright (login incluido). Es la capa pantalla. |
| `reporter.py` | Guarda el reporte de cada corrida (`.txt` + `.json`) con 3 categorías: PASA / FALLA / descartada. |
| `watch_compare_anchored.py` | Monitor en vivo de **cálculo** (sim vs API), anclado por tiempo + reporte. |
| `watch_3capas.py` | Monitor en vivo de las **3 capas** (cálculo + pantalla). El más completo. |
| `omniops_login.example.txt` | Plantilla de credenciales. Copiar a `omniops_login.txt`. |
| `omniops_cookie.example.txt` | Plantilla para el modo cookie/Microsoft (opcional). |
| `diagnosticos/` | Herramientas de investigación puntual (no forman parte del monitor). |

## 7. Ajustes que podés cambiar

En la cabecera de los archivos:

- `compare_pcs_power.py`: `TOL_ABS_KW` y `TOL_REL` — qué tan exigente es la
  comparación (hoy 50 kW / 2%). `SIM_HOST`, `SIM_PORT` — dónde está el simulador.
- `watch_*.py`: `OMNIOPS_EVERY_S` — cada cuánto pregunta a la API (subilo si
  aparece el error `429 Too Many Requests`). `MATCH_MAX_GAP_S` — cuán estricto es
  el anclaje por tiempo.
- `watch_3capas.py`: `HEADLESS` — `True` navegador oculto (normal), `False` visible.

## 8. Los dos logins

- **Email/contraseña** (recomendado, automático): creá `omniops_login.txt`.
- **Cookie / Microsoft**: creá `omniops_cookie.txt` con la cookie del navegador.
  `auth.py` detecta solo cuál archivo existe y usa ese modo.

## 9. Limitación conocida y hallazgo

- **UI en modo recargar:** la capa pantalla recarga la página antes de leer, en
  vez de esperar la actualización en vivo de SignalR. Valida el dato igual de bien;
  solo es un poco más lento.
- **Hallazgo de QA:** en un navegador nuevo/automatizado, la conexión de tiempo
  real (SignalR / WebSocket) recibe `401` porque el token de acceso vence rápido
  (~3 min) y tropieza en cada renovación. Efecto: el dashboard puede quedar sin
  actualizarse solo. Es tema del backend/front de OmniOps, no del framework.

## 12. Estructura — dónde está cada cosa (post-refactor)

Tras el refactor (POM + DRY), cada responsabilidad vive en un solo lugar:

```
config.py          TODA la configuración (URLs, puertos, intervalos, tolerancias,
                   umbrales de gap). Si cambia el entorno, se toca SOLO acá.

Fuentes de datos
  auth.py          login + token (portero de la API)
  source_modbus.py ÚNICA lectura del simulador (signed16, read_sim_total_kw,
                   LectorModbus/LectorFalso). Acá se enchufa otro simulador.
  omniops_time.py  parseo de tiempo de OmniOps (parse_epoch)
  timeanchor.py    anclaje por tiempo (match_buffer, podar)

Capa CÁLCULO
  check_pcs_power.py    smoke test de la API
  compare_pcs_power.py  oráculo sim vs API (compare, report)

Capa PANTALLA (POM)
  pages/base_page.py        común (¿en login?, esperar carga)
  pages/login_page.py       selectores del login + login()
  pages/monitoring_page.py  device-card, metric-value, tabla de alarmas + parse_kw
  ui_reader.py              fachada: abre navegador, compone las pages, read()

Alarmas
  alarms_api.py      lee alarmas de la API
  alarms_oracle.py   oráculo de causa (bit/umbral) usando source_modbus
  verdict.py         el juez de 4 casos
  watch_alarms.py    monitor de alarmas
  alarms_catalog.example.py  plantilla del catálogo

Monitores / reportes
  watch_compare_anchored.py  cálculo en vivo (sim vs API)
  watch_3capas.py            3 capas en vivo (cálculo + pantalla)
  reporter.py                reportes (técnico + executive_summary)
```

Regla para ubicar algo: **¿es un selector de UI?** → la page correspondiente.
**¿un número de config?** → `config.py`. **¿leer el simulador?** → `source_modbus.py`.

## 11. Modo presentación (para mostrar a un alto cargo)

La categoría **descartada** (desfase de tiempo) te sirve *a vos* para saber que
el anclaje funciona, pero a un directivo lo confunde. Por eso:

- **Reporte ejecutivo:** los monitores (`watch_compare_anchored.py` y
  `watch_3capas.py`) generan **siempre**, además del reporte técnico, un
  `executive_summary_*.txt` **en inglés** y con **PASS / FAIL**: solo mediciones
  verificadas, passed / failed y **pass rate**. No menciona descartadas ni
  desfase. Es el que mostrás; no hay que acordarse de activar nada.

- **Terminal en vivo:** si vas a hacer una demo en vivo, corré con `--limpio`:

  ```bash
  python watch_compare_anchored.py --limpio
  python watch_3capas.py --limpio
  ```

  En limpio las líneas van en idioma humano (`OmniOps calcula correcto ✓`) y las
  mediciones descartadas por desfase se ven como `· midiendo…` (muestra que está
  trabajando, no como un error). Sin `--limpio`, ves todo el detalle como siempre.

## 10. Próximos pasos posibles

- Validar más métricas (SoC, voltaje, temperatura): mismo patrón, otro registro.
- Investigar por qué `cellVoltageDeltaMv` llega en `null`.
- Que el WebSocket de SignalR sobreviva la renovación del token (backend).
