# Validación de alarmas — módulo nuevo

Extiende el framework a las **alarmas**, con el mismo patrón de oráculo diferencial
que la potencia PCS: comparamos la **causa en el crudo** (simulador) contra la
**alarma en la API** de OmniOps, y damos un veredicto.

```
  causa en el CRUDO           alarma en la API
  (alarms_oracle.py)   vs     (alarms_api.py)
            \____________  _____________/
                    verdict.py  ->  PASA / PASA_SANO /
                                    FALLA_FALSA / FALLA_NO_DETECTADA /
                                    NO_VERIFICABLE
```

## Piezas (todas con `--self-check`, prueban sin red)

| Archivo | Rol | Depende del catálogo |
|---|---|---|
| `verdict.py` | El juez: 4 casos + no verificable. Lógica pura. | No |
| `alarms_api.py` | Lee `GET /api/events/alarms/filtered?Status=Open` y normaliza. | No |
| `alarms_oracle.py` | Oráculo de causa: lee el crudo (bit de Evt1 / umbral). | Solo los números |
| `watch_alarms.py` | Monitor en vivo: baseline (hoy) o completo (con catálogo). | Modo completo |
| `alarms_catalog.example.py` | Plantilla del catálogo. Copiar a `alarms_catalog.py`. | — |

El **motor está completo y probado**. Lo único que falta para el modo completo
son los **datos** (qué registro/bit/límite dispara cada alarma), que van en
`alarms_catalog.py` traducidos del **SPEC90 / MAPA_DE_BITS.md**.

## Cómo correr

**Hoy, sin catálogo ni hook de inyección** (baseline + correlación pasiva):

```bash
python watch_alarms.py
```

Con el simulador sano no debería haber ninguna alarma abierta; si aparece una,
la marca como **posible FALSA**. Deja reporte en `reportes/`.

**Antes que nada, fijar los nombres de campo de la API de alarmas** (no los
conocemos aún). Con OmniOps corriendo:

```bash
python alarms_api.py --dump
```

Pegame esa salida y ajusto los candidatos marcados `AJUSTAR` en `alarms_api.py`
(y el `code` de match). Son 2-3 líneas.

**Modo completo** (cuando exista `alarms_catalog.py` con datos reales):

```bash
python watch_alarms.py            # detecta el catálogo solo
python watch_alarms.py --baseline # forzar baseline aunque haya catálogo
```

## Qué falta para cerrarlo

1. **Nombres de campo reales** de la API de alarmas → `alarms_api.py --dump`.
2. **`alarms_catalog.py`** con los registros/bits/límites del SPEC90 /
   MAPA_DE_BITS.md (usar `alarms_catalog.example.py` como molde).
3. **Hook `--inject-file`** en el simulador (`inject.py`) para provocar causas
   activamente y ver FALLA_NO_DETECTADA / detección real. El baseline y la
   correlación pasiva ya corren sin esto.
