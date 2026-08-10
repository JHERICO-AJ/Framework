# Objetivo de la automatización de alarmas — validación por oráculo

## Qué queremos probar

No alcanza con ver que "apareció una alarma". Queremos corroborar que **cada
alarma se activó por la causa correcta y no de forma falsa**.

Ejemplo: si OmniOps muestra **Cell Overvoltage**, el framework confirma —leyendo
el Modbus **crudo** por su cuenta— que el **bit 9 del `Evt1_802`** realmente está
presente. Si la alarma aparece pero el bit 9 **no** está → es una **alarma falsa**.

## El oráculo: leer la causa del crudo, independientemente

El framework NO le cree a OmniOps. Lee el simulador por Modbus (igual que hoy hace
con la potencia) y decodifica **qué causa está realmente presente**. Después
compara contra lo que muestra OmniOps.

```
   Modbus crudo (oráculo)          OmniOps API
   ¿bit 9 presente?                ¿aparece Cell Overvoltage?
          │                                │
          └──────────── correlación ───────┘
```

## Los 4 veredictos

| Causa en el crudo | Alarma en OmniOps | Veredicto |
|---|---|---|
| presente | aparece | **PASA** — activó por la causa correcta |
| ausente | aparece | **FALLA — alarma FALSA** |
| presente | no aparece | **FALLA — no detectada** |
| ausente | no aparece | **PASA** — sano (sin falsos positivos) |

Además de la presencia, se verifica que la fila tenga la **severidad** y el
**subsistema** correctos (por eso el catálogo trae `severity` y `subsystem_api`).

## Qué lee el oráculo por tipo de alarma

- **Bit** (celda/módulo, PCS DC/AC, ground fault): lee el bit exacto del `Evt1_802`
  / `Evt1_E001` en el crudo. Correlación **100% independiente**.
- **Telemetría** (temp/tensión/corriente de rack/string/PCS): lee el valor y lo
  compara con el umbral. Correlación **independiente**.
- **EMS / tendencia** (comm lost, PF, drift…): la causa **no está en el Modbus**
  (se calcula en OmniOps). Acá el oráculo no puede confirmar la causa de forma
  independiente; solo valida "inyecté → apareció / no inyecté → no apareció".
  Marcado con `oracle_independent=False` en el catálogo.

## Las tres capas (reusa tu framework actual)

```
  oráculo (Modbus crudo)  →  API de OmniOps  →  UI (#alarmTableBody)
        └──── capa CÁLCULO ────┘        └── capa PANTALLA ──┘
```

- **Cálculo:** causa del crudo vs alarma de la API (los 4 veredictos de arriba).
- **Pantalla:** la fila de la UI coincide con la API (Severity, Site, Subsystem,
  Alarm Condition, TRIGGER SIGNAL/RULE).

## Prerrequisito

Para provocar cada causa, el simulador necesita el **hook de inyección**
(`--inject-file`). Sin él solo se valida la línea base (sano → 0 alarmas). El
catálogo trae la receta de inyección por alarma en el campo `inject`.
