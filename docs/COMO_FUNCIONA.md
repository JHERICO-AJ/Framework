# Cómo funciona el framework (a fondo)

Este documento explica el **porqué** de las decisiones de diseño. El README
explica cómo *usar* el framework; este explica cómo y por qué *funciona*. Es la
lectura recomendada para entender el framework antes de tocarlo.

---

## 1. La idea central: oráculo diferencial

No le preguntamos a OmniOps si está bien — eso sería confiar en el mismo sistema
que queremos verificar. En cambio, leemos el dato **crudo** del simulador por
nuestra cuenta (Modbus, independiente de OmniOps) y lo comparamos contra lo que
OmniOps produce.

```
                        ┌─────────────► API de OmniOps (lo que CALCULA)
   simulador (Modbus)   │
   [dato crudo] ────────┼─────────────► UI de OmniOps (lo que MUESTRA)
        │               │
        └──► nuestro oráculo (lo que DEBERÍA dar)  ──► comparamos
```

- **Oráculo** = nuestra cuenta independiente de "qué debería pasar" (leyendo el crudo).
- **API / UI** = lo que OmniOps realmente produce.
- Si coinciden, OmniOps está bien. Si no, encontramos un bug — y sabemos en qué
  capa (cálculo vs pantalla), porque las verificamos por separado.

El simulador **solo expone telemetría cruda** (temperaturas, tensiones, bits).
Nunca dice "alarma". Las alarmas las inventa OmniOps evaluando esa telemetría.
Por eso el sujeto probado siempre es OmniOps, no el simulador.

---

## 2. El proxy Modbus: cómo inyectamos condiciones

Para probar una alarma necesitamos provocar su causa (ej. temperatura alta). No
podemos ni queremos modificar el simulador. La solución es un **proxy** que se
mete en el medio del cable Modbus.

```
  ANTES:   edge ──────────────► simulador (5020)
  AHORA:   edge ──► proxy (5020) ──► simulador real (5021)
```

- El simulador real se corre en el **5021**.
- El proxy escucha en el **5020** (donde el edge espera encontrar al simulador).
- El edge le pide datos al proxy creyendo que es el simulador.
- El proxy le pide los datos al simulador real, **los modifica si hay una
  inyección activa**, y se los devuelve al edge.

Así, cuando inyectamos "temperatura del rack = altísima", el proxy reemplaza ese
registro en cada lectura. El edge lee el valor modificado, lo manda a OmniOps, y
OmniOps genera la alarma. El simulador nunca se enteró; nosotros modificamos el
dato **en tránsito**.

El estado de inyección vive en `inject_state.json`: qué registros prender/apagar
(bits) o fijar (valores). El proxy lo lee **fresco en cada lectura**, así que
inyectar/limpiar tiene efecto inmediato sin reiniciar nada.

Flujo completo de una prueba de alarma:

```
inyectás → proxy modifica el registro → edge lo lee (cada 5s) →
Event Hub → OmniOps evalúa → crea la alarma → la API la muestra → verificamos
```

---

## 3. Hallazgo clave: OmniOps evalúa por TELEMETRÍA, no por bits

El protocolo Modbus tiene, por un lado, **bits de evento** (Evt1) que dicen
"esta falla está activa", y por otro, los **valores de telemetría** (temperatura,
corriente, etc.) en el Model 803/103.

Descubrimos, probándolo, que **OmniOps NO mira los bits de evento**: mira los
**valores de telemetría** y aplica sus propios umbrales. Si inyectás el bit de
"Rack High Temp", nuestro oráculo dice "causa presente" pero OmniOps no crea nada.
Si inyectás una **temperatura por encima del umbral**, OmniOps sí crea la alarma.

Por eso la inyección de alarmas de telemetría **fuerza un valor extremo** en el
registro correspondiente (temperatura muy alta, corriente muy alta), no un bit.
El mapa de qué registro corresponde a cada alarma está en
`shared/domain/telemetry_map.py`, extraído del Model 803/103 del simulador.

`valor_real = raw × 10^scale_factor`. Para inyectar "por encima del umbral" sin
pelear con el scale factor, forzamos un raw extremo (muy alto o muy bajo según la
dirección); el oráculo hace la comparación exacta contra el umbral real.

---

## 4. Hallazgo: OmniOps NO cierra las alarmas

Una vez que OmniOps abre una alarma, la deja abierta (arrastra decenas de alarmas
viejas). Esto rompe la verificación ingenua de "¿existe la alarma?", porque
siempre existe.

La solución: verificar por **`lastOccurred`** (la última vez que OmniOps vio la
condición), no por `firstOccurred` ni por presencia.

- Cuando inyectás, OmniOps **actualiza `lastOccurred`** al momento actual.
- Una alarma "fresca" = su `lastOccurred` es cercano al momento en que inyectaste.
- Al limpiar, `lastOccurred` **se congela** (deja de actualizarse) → así sabemos
  que la condición terminó, aunque la alarma siga técnicamente abierta.

Por eso los veredictos (`shared/domain/verdict.py`) distinguen 4 casos:
`PASA` (causa + alarma fresca), `FALLA_FALSA` (alarma sin causa),
`FALLA_NO_DETECTADA` (causa sin alarma), `PASA_SANO` (ni causa ni alarma).

---

## 5. Detalle: los timestamps vienen en UTC

La API de OmniOps devuelve `firstOccurred` / `lastOccurred` en **UTC**, aunque la
UI los muestre en hora local. El framework **compara en UTC** (toma el momento de
inyección en UTC) y **muestra en hora local** para que sea legible. Por eso el
chequeo de "apareció a la hora correcta" (`hora✓`) funciona en cualquier zona
horaria, sin números mágicos.

---

## 6. El chequeo temporal (modo escena)

`python -m tools.probar 16 --at 10 --hasta 30 --vivo` hace, mostrándolo en vivo:

1. seg 0-10: antes de inyectar → causa ausente.
2. seg 10: inyecta → verifica que OmniOps la cree y que el timestamp ≈ seg 10.
3. seg 10-30: la muestra refrescándose (`lastOccurred` sube).
4. seg 30: limpia → verifica que la causa desaparece del crudo y que
   `lastOccurred` se congela.

Es la línea temporal completa: no solo "apareció", sino "apareció cuando lo pedí"
y "se apagó cuando lo pedí" (en la forma correcta para un sistema que no cierra
alarmas).

---

## 7. Por qué la estructura está separada así

- **La capa API no sabe de Modbus.** Si un archivo "de API" empezara a inyectar
  registros, sería señal de que en realidad es cross-layer. Esto permite testear
  la API sola, sin el simulador.
- **El oráculo (domain) no habla con el sistema.** Calcula el esperado leyendo el
  crudo; es testeable offline (por eso los `--self-check`).
- **El assert vive en el test.** El `domain` aporta el dato esperado; el test
  compara y decide verde/rojo.
- **Los monitores observan, no afirman.** La validación de un componente es su
  *test*; el monitor es una herramienta para mirar en vivo.
