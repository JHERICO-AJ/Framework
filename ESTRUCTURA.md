# Estructura del framework — empezá por acá

Framework de QA que valida, por **testing de oráculo diferencial**, que OmniOps
calcula y muestra bien la telemetría de baterías BESS. No le cree a OmniOps: lee
el dato crudo del simulador de forma independiente y lo compara contra lo que
OmniOps produce en la **API** (cálculo) y en la **pantalla** (UI).

## Mapa de carpetas — dónde está cada cosa

```
config.py            TODA la configuración (URLs, puertos, tolerancias, tiempos).
                     Si cambia el entorno, se toca SOLO acá.
conftest.py          Hace que pytest encuentre los paquetes desde la raíz.
pytest.ini           Config de pytest.

core/                Fundaciones compartidas (las usan todas las capas)
  auth.py              Login + token de la API (el "portero").
  source_modbus.py     ÚNICA lectura del simulador (Modbus). Acá se enchufa otro simulador.
  omniops_time.py      Parseo de tiempo de OmniOps.
  timeanchor.py        Anclaje por tiempo (comparar contra el mismo instante).
  reporter.py          Reportes (técnico + resumen ejecutivo).

calc/                Capa CÁLCULO (¿OmniOps calcula bien?)
  check_pcs_power.py   Smoke test de la API.
  compare_pcs_power.py Oráculo: suma la potencia del simulador vs la API.

alarms/              Dominio ALARMAS
  catalog.py           Las 39 alarmas: qué leer del crudo, umbrales, verdict().
  oracle.py            Oráculo de causa: ¿la causa está en el crudo? (lee bits/registros)
  api.py               Lee las alarmas de la API de OmniOps.
  verdict.py           El juez de 4 casos (PASA / falsa / no detectada / sano).
  inject.py            Traduce "alarma X" -> qué registro/bit forzar (+ programación en el tiempo).

ui/                  Capa PANTALLA (Playwright + Page Object Model)
  ui_reader.py         Fachada: abre el navegador, se loguea, lee.
  pages/               Una clase por pantalla, con SUS selectores:
    base_page.py         común (¿estoy en login?, esperar carga)
    login_page.py        selectores del login + login()
    monitoring_page.py   dashboard: tarjeta de potencia, tabla de alarmas, parse_kw

monitors/            Monitores EN VIVO (corren en bucle, para mirar/demostrar)
  watch_3capas.py            3 capas de potencia en tiempo real.
  watch_compare_anchored.py  solo cálculo (sim vs API) en tiempo real.

tests/               Pruebas PYTEST (corren una vez, dan verde/rojo)
  test_3capas.py       las 3 capas de potencia como test.

tools/               Utilidades (no son parte del monitor)
  sim_launcher.py      levanta el simulador desde el framework.
  sniff_alarms_api.py  descubre la API real de alarmas (captura la red).
  diagnosticos/        scripts de investigación puntual.

docs/                Documentación
  MAPA_DE_BITS.md      qué bit/registro confirma cada alarma.
  ALARMAS.md           diseño de la validación de alarmas.
```

## La regla para ubicar algo nuevo

- ¿Es un **selector de UI**? → la página correspondiente en `ui/pages/`.
- ¿Es un **número de configuración** (URL, puerto, tolerancia, tiempo)? → `config.py`.
- ¿Es **leer el simulador**? → `core/source_modbus.py`.
- ¿Es una **alarma** (qué bit, umbral, cómo se inyecta)? → `alarms/catalog.py`.
- ¿Es una **prueba nueva** (verde/rojo)? → un archivo `test_*.py` en `tests/`.
- ¿Es un **monitor en vivo**? → `monitors/`.

## Cómo correr (desde la RAÍZ del proyecto)

Preparación (una vez):
```
pip install -r requirements.txt
playwright install chromium
```
Y crear `omniops_login.txt` con las credenciales (ver `omniops_login.example.txt`).

Pruebas pytest:
```
pytest                         # corre todo lo de tests/
pytest tests/test_3capas.py -v # una sola
```

Monitores en vivo (se corren como módulo, con -m, desde la raíz):
```
python -m monitors.watch_3capas
python -m monitors.watch_compare_anchored
```

Self-checks (prueban la lógica sin el sistema prendido):
```
python -m core.source_modbus --self-check
python -m core.timeanchor --self-check
python -m calc.compare_pcs_power --self-check
python -m alarms.oracle --self-check
python -m alarms.verdict --self-check
python -m alarms.inject --self-check
```

Herramientas:
```
python -m tools.sim_launcher
python -m tools.sniff_alarms_api
```

> Nota: ahora los scripts se corren con `python -m paquete.modulo` (no
> `python archivo.py`), porque están organizados en paquetes. Correr siempre
> parado en la raíz del proyecto.
