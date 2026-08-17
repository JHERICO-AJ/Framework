# Mapa de bits real — cómo el oráculo confirma la causa de cada alarma

Direcciones y bits tomados de **Catalogo_Bits_BESS**. El oráculo lee estas
direcciones del Modbus crudo para confirmar la causa (no le cree a OmniOps).

## Registros clave (Holding Registers)

| Registro | HR | Contenido |
|---|---|---|
| `Evt1` Model 802 (BMS) | **10095** | bitfield de 32 bits: celda/módulo/rack |
| `Evt1` E001 (Site Ctrl) | **9815** | bitfield de 32 bits: PCS/red/site |
| `FireAlarm` | **9818** | máscara de humo por contenedor |
| `PcsOnline` | **9822** | máscara de PCS en línea (bit apagado = caído) |
| Telemetría | Model 803 | temp/tensión/corriente/SoC por string/PCS |

> El Model 802 empieza en HR 10069; el Evt1 está en base+26 = **10095**.

## Cómo se lee un bit (ejemplo Cell Overvoltage)

```
Evt1_802 (HR 10095) → entero de 32 bits
bit 9  →  máscara 0x00000200  →  Cell Overvoltage
causa_presente = (valor & 0x200) != 0
```

## Por alarma: qué lee el oráculo

| ID | Alarma | Capa | Oráculo (qué leer del crudo) | Independiente |
|---|---|---|---|---|
| 1 | Cell Overvoltage | bit_802 | Evt1_802 (HR 10095) bit 9 | sí |
| 2 | Cell Undervoltage | bit_802 | Evt1_802 (HR 10095) bit 11 | sí |
| 3 | Cell High Temp | bit_802 | Evt1_802 (HR 10095) bit 1 | sí |
| 4 | Cell Low Temp | bit_802 | Evt1_802 (HR 10095) bit 3 | sí |
| 5 | Cell Temp Difference High | bit_802 | Evt1_802 (HR 10095) bit 18 | sí |
| 6 | Cell Voltage difference High | bit_802 | Evt1_802 (HR 10095) bit 17 | sí |
| 10 | Module High Temp | bit_802 | Evt1_802 (HR 10095) bit 1 | sí |
| 11 | Module Low Temp | bit_802 | Evt1_802 (HR 10095) bit 3 | sí |
| 13 | Module Temp Difference High | bit_802 | Evt1_802 (HR 10095) bit 18 | sí |
| 16 | Rack High Temp | telemetry | telemetria Model 803 (string/PCS) vs umbral | sí |
| 17 | Rack Low Temp | telemetry | telemetria Model 803 (string/PCS) vs umbral | sí |
| 18 | Rack Temp Gradient High | telemetry | telemetria Model 803 (string/PCS) vs umbral | sí |
| 19 | Rack Voltage Difference High | telemetry | telemetria Model 803 (string/PCS) vs umbral | sí |
| 21 | Rack Contactor Failure | bit_802 | Evt1_802 (HR 10095) bit 20 | sí |
| 22 | Rack Cooling Fan Failure | bit_802 | Evt1_802 (HR 10095) bit 21 | sí |
| 23 | Rack Door Open | bit_802 | Evt1_802 (HR 10095) bit 23 | sí |
| 24 | Rack Smoke Detected | bit_fire | FireAlarm (HR 9818) mask contenedor | sí |
| 27 | Rack Ground Fault | bit_802 | Evt1_802 (HR 10095) bit 22 | sí |
| 29 | String Overcurrent | telemetry | telemetria Model 803 (string/PCS) vs umbral | sí |
| 32 | String Temp Abnormal | telemetry | telemetria Model 803 (string/PCS) vs umbral | sí |
| 33 | String SOC Imbalance | telemetry | telemetria Model 803 (string/PCS) vs umbral | sí |
| 38 | PCS DC Bus Overvoltage | bit_e001 | Evt1_E001 (HR 9815) bit 1 | sí |
| 40 | PCS AC Overvoltage | bit_e001 | Evt1_E001 (HR 9815) bit 10 | sí |
| 41 | PCS AC Undervoltage | bit_e001 | Evt1_E001 (HR 9815) bit 11 | sí |
| 42 | PCS AC Overcurrent | telemetry | telemetria Model 803 (string/PCS) vs umbral | sí |
| 43 | PCS AC Undercurrent | telemetry | telemetria Model 803 (string/PCS) vs umbral | sí |
| 44 | PCS Phase Loss | ems | N/A (causa fuera del Modbus) | **no** |
| 45 | PCS Phase Imbalance | ems | N/A (causa fuera del Modbus) | **no** |
| 46 | PCS Ground Fault | bit_e001 | Evt1_E001 (HR 9815) bit 0 | sí |
| 50 | PCS Communication Lost | bit_pcsonline | PcsOnline (HR 9822) PCS caido | sí |
| 51 | EMS-BMS Comm Lost | ems | N/A (causa fuera del Modbus) | **no** |
| 52 | EMS-PCS Comm Lost | ems | N/A (causa fuera del Modbus) | **no** |
| 55 | EMS Control Logic Fault | ems | N/A (causa fuera del Modbus) | **no** |
| 58 | EMS Parameter Mismatch | ems | N/A (causa fuera del Modbus) | **no** |
| 66 | Container Smoke Detected | bit_fire | FireAlarm (HR 9818) mask contenedor | sí |
| 71 | Critical sensor data drift/freeze | trend | N/A (causa fuera del Modbus) | **no** |
| 73 | PCS power factor anomalous deviation | trend | N/A (causa fuera del Modbus) | **no** |
| 74 | Meter data and PCS data mismatch | trend | N/A (causa fuera del Modbus) | **no** |
| 78 | PCS idle power drift | trend | N/A (causa fuera del Modbus) | **no** |

## Los casos que NO son un bit (importante)

- **Humo (24, 66):** registro `FireAlarm` (HR 9818), no un bit del Evt1.
- **PCS Comm Lost (50):** registro `PcsOnline` (HR 9822); el bit del PCS se apaga.
- **Telemetría (16, 17, 18, 19, 29, 32, 33, 42, 43):** valor del Model 803 vs umbral.
- **EMS / tendencia (44, 45, 51, 52, 55, 58, 71, 73, 74, 78):** la causa NO está en
  el Modbus (se calcula en OmniOps). El oráculo no la confirma de forma independiente
  (`oracle_independent = false`): solo valida inyectado→apareció.

## Correcciones respecto a versiones previas

- **ID 21 (Rack Contactor Failure):** es BIT real → `Evt1_802` bit **20** (antes lo tenía como telemetría).
- **ID 22 (Rack Cooling Fan Failure):** es BIT real → `Evt1_802` bit **21** (antes lo tenía como EMS).

## Verificación en vivo (primer check verde)

Inyectá el bit 9 y leé HR 10095 con tu lector Modbus: debe dar **0x00000200 (512)**.
Si da eso, la dirección, el bit y el orden de bytes están bien.
