# Real bit map — how the oracle confirms the cause of each alarm

Addresses and bits taken from **Catalogo_Bits_BESS**. The oracle reads these
addresses from raw Modbus to confirm the cause (it doesn't trust OmniOps).

## Key registers (Holding Registers)

| Register | HR | Content |
|---|---|---|
| `Evt1` Model 802 (BMS) | **10095** | 32-bit bitfield: cell/module/rack |
| `Evt1` E001 (Site Ctrl) | **9815** | 32-bit bitfield: PCS/grid/site |
| `FireAlarm` | **9818** | smoke mask per container |
| `PcsOnline` | **9822** | PCS-online mask (bit off = down) |
| Telemetry | Model 803 | temp/voltage/current/SoC per string/PCS |

> Model 802 starts at HR 10069; Evt1 is at base+26 = **10095**.

## How a bit is read (Cell Overvoltage example)

```
Evt1_802 (HR 10095) → 32-bit integer
bit 9  →  mask 0x00000200  →  Cell Overvoltage
cause_present = (value & 0x200) != 0
```

## Per alarm: what the oracle reads

| ID | Alarm | Layer | Oracle (what to read from the raw data) | Independent |
|---|---|---|---|---|
| 1 | Cell Overvoltage | bit_802 | Evt1_802 (HR 10095) bit 9 | yes |
| 2 | Cell Undervoltage | bit_802 | Evt1_802 (HR 10095) bit 11 | yes |
| 3 | Cell High Temp | bit_802 | Evt1_802 (HR 10095) bit 1 | yes |
| 4 | Cell Low Temp | bit_802 | Evt1_802 (HR 10095) bit 3 | yes |
| 5 | Cell Temp Difference High | bit_802 | Evt1_802 (HR 10095) bit 18 | yes |
| 6 | Cell Voltage difference High | bit_802 | Evt1_802 (HR 10095) bit 17 | yes |
| 10 | Module High Temp | bit_802 | Evt1_802 (HR 10095) bit 1 | yes |
| 11 | Module Low Temp | bit_802 | Evt1_802 (HR 10095) bit 3 | yes |
| 13 | Module Temp Difference High | bit_802 | Evt1_802 (HR 10095) bit 18 | yes |
| 16 | Rack High Temp | telemetry | Model 803 telemetry (string/PCS) vs threshold | yes |
| 17 | Rack Low Temp | telemetry | Model 803 telemetry (string/PCS) vs threshold | yes |
| 18 | Rack Temp Gradient High | telemetry | Model 803 telemetry (string/PCS) vs threshold | yes |
| 19 | Rack Voltage Difference High | telemetry | Model 803 telemetry (string/PCS) vs threshold | yes |
| 21 | Rack Contactor Failure | bit_802 | Evt1_802 (HR 10095) bit 20 | yes |
| 22 | Rack Cooling Fan Failure | bit_802 | Evt1_802 (HR 10095) bit 21 | yes |
| 23 | Rack Door Open | bit_802 | Evt1_802 (HR 10095) bit 23 | yes |
| 24 | Rack Smoke Detected | bit_fire | FireAlarm (HR 9818) container mask | yes |
| 27 | Rack Ground Fault | bit_802 | Evt1_802 (HR 10095) bit 22 | yes |
| 29 | String Overcurrent | telemetry | Model 803 telemetry (string/PCS) vs threshold | yes |
| 32 | String Temp Abnormal | telemetry | Model 803 telemetry (string/PCS) vs threshold | yes |
| 33 | String SOC Imbalance | telemetry | Model 803 telemetry (string/PCS) vs threshold | yes |
| 38 | PCS DC Bus Overvoltage | bit_e001 | Evt1_E001 (HR 9815) bit 1 | yes |
| 40 | PCS AC Overvoltage | bit_e001 | Evt1_E001 (HR 9815) bit 10 | yes |
| 41 | PCS AC Undervoltage | bit_e001 | Evt1_E001 (HR 9815) bit 11 | yes |
| 42 | PCS AC Overcurrent | telemetry | Model 803 telemetry (string/PCS) vs threshold | yes |
| 43 | PCS AC Undercurrent | telemetry | Model 803 telemetry (string/PCS) vs threshold | yes |
| 44 | PCS Phase Loss | ems | N/A (cause outside Modbus) | **no** |
| 45 | PCS Phase Imbalance | ems | N/A (cause outside Modbus) | **no** |
| 46 | PCS Ground Fault | bit_e001 | Evt1_E001 (HR 9815) bit 0 | yes |
| 50 | PCS Communication Lost | bit_pcsonline | PcsOnline (HR 9822) PCS down | yes |
| 51 | EMS-BMS Comm Lost | ems | N/A (cause outside Modbus) | **no** |
| 52 | EMS-PCS Comm Lost | ems | N/A (cause outside Modbus) | **no** |
| 55 | EMS Control Logic Fault | ems | N/A (cause outside Modbus) | **no** |
| 58 | EMS Parameter Mismatch | ems | N/A (cause outside Modbus) | **no** |
| 66 | Container Smoke Detected | bit_fire | FireAlarm (HR 9818) container mask | yes |
| 71 | Critical sensor data drift/freeze | trend | N/A (cause outside Modbus) | **no** |
| 73 | PCS power factor anomalous deviation | trend | N/A (cause outside Modbus) | **no** |
| 74 | Meter data and PCS data mismatch | trend | N/A (cause outside Modbus) | **no** |
| 78 | PCS idle power drift | trend | N/A (cause outside Modbus) | **no** |

## The cases that are NOT a bit (important)

- **Smoke (24, 66):** `FireAlarm` register (HR 9818), not an Evt1 bit.
- **PCS Comm Lost (50):** `PcsOnline` register (HR 9822); the PCS's bit turns off.
- **Telemetry (16, 17, 18, 19, 29, 32, 33, 42, 43):** Model 803 value vs threshold.
- **EMS / trend (44, 45, 51, 52, 55, 58, 71, 73, 74, 78):** the cause is NOT in
  Modbus (it's calculated inside OmniOps). The oracle doesn't confirm it
  independently (`oracle_independent = false`): it only validates
  injected→appeared.

## Corrections relative to previous versions

- **ID 21 (Rack Contactor Failure):** it's a real BIT → `Evt1_802` bit **20** (previously listed as telemetry).
- **ID 22 (Rack Cooling Fan Failure):** it's a real BIT → `Evt1_802` bit **21** (previously listed as EMS).

## Live verification (first green check)

Inject bit 9 and read HR 10095 with your Modbus reader: it should give
**0x00000200 (512)**. If it does, the address, the bit, and the byte order
are correct.
