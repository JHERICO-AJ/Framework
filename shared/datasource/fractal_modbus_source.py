"""
fractal_modbus_source.py — reads live telemetry directly from a Fractal
simulator instance over Modbus TCP, bypassing OmniOps entirely (UI, API,
and DB all sit downstream of this same source).

Built for the "Power (kW)" cross-layer gap: confirmed 2026-08-28 that
Fractal telemetry isn't persisted to any table OmniOps exposes (see
db_source.get_pcs_power_kw's docstring) -- RawBaseData, TelemetryReading,
and dataprocessing.ProcessedBessData.Power_kW are all empty for BOLIVIA even
with the simulator running. Reading the simulator directly sidesteps that
gap: whatever it emits here is the same value the UI/API should eventually
show, regardless of what's or isn't cached/persisted in between. Also the
right ground truth for Device Status Panel specifically: confirmed
2026-09-07 in docs/OF-140.txt's own "Origen en pantalla (cache vs base de
datos)" table that the panel reads live in-memory SiteState, not the DB.

Same pattern as shared/datasource/modbus_source.py (the EPC equivalent),
kept as a separate file rather than extending that one because the register
map, PCS block layout, and per-site port/unit topology are entirely
different (Fractal: one Modbus TCP instance PER SITE, auto-assigned port;
EPC: a single shared local simulator/proxy).

Register offsets below come from omniops-bess-edge's
modbus_common/fractal_addressing_map.py (EMU_FIELDS / PCS_COMMON_FIELDS) --
confirmed 2026-09-07 against that file directly, not guessed. That same
file is the source of truth used to prove Fractal's wire protocol has NO
heartbeat field anywhere in EMU/PCS/TTC/Meter blocks.

READ ONLY. pymodbus is only imported when connecting.
"""
from __future__ import annotations

from shared.config.settings import SIM_HOST, FRACTAL_SITE_MODBUS

# ---------------------------------------------------------------------------
# Register map (base + offset), all confirmed against
# omniops-bess-edge/modbus_common/fractal_addressing_map.py 2026-09-07.
# ---------------------------------------------------------------------------

EMU_BASE = 100
EMU_SYSTEM_SOC_PCT_OFFSET = 4      # UINT16, scale 0.1
EMU_SYSTEM_SOH_PCT_OFFSET = 5      # UINT16, scale 0.1
EMU_STATION_STATE_OFFSET = 21      # ENUM16, no scale
EMU_ACTIVE_POWER_KW_OFFSET = 25    # INT32, scale 0.1
EMU_DC_CURRENT_A_OFFSET = 33       # INT32, scale 0.1 -- confirmed 2026-09-10
                                   # against omniops-bess-edge's real
                                   # modbus_common/fractal_addressing_map.py
                                   # EMU_FIELDS (user-provided source), not
                                   # guessed -- ground truth for Dispatch
                                   # Limits & Tracking's "DC Bus Current".
EMU_DC_VOLTAGE_V_OFFSET = 35      # UINT32, scale 0.1 -- same source, ground
                                   # truth for "DC Bus Voltage".

EMU_STATUS_WORD_1_OFFSET = 118     # BITFIELD16, first of 10 consecutive status words
EMU_STATUS_WORD_3_RS485_OFFSET = EMU_STATUS_WORD_1_OFFSET + 2  # bit n = PCS (n+1) RS485 connected
EMU_STATUS_WORD_5_CAN_OFFSET = EMU_STATUS_WORD_1_OFFSET + 4    # bit n = PCS (n+1) CAN connected

METER_BASE = 35300
METER_TOTAL_ACTIVE_POWER_KW_OFFSET = 15  # INT32, scale 0.1

PCS_BASES = (5000, 5300, 5600)
PCS_P_AC_KW_OFFSET = 8             # INT32, scale 0.1
PCS_STATUS_WORD_1_OFFSET = 250     # BITFIELD16, first of 10 consecutive status words
PCS_ALARM_WORD_1_OFFSET = 260      # BITFIELD16, first of 30 consecutive alarm words
PCS_ALARM_WORD_COUNT = 30

PERCENT_SCALE = 0.1
KW_SCALE = 0.1
AMPS_SCALE = 0.1
VOLTS_SCALE = 0.1

# Real bit catalog for PCS status_word_1, confirmed against
# omniops-bess-edge/modbus_common/fractal_addressing_map.py's
# PCS_STATUS_WORD_LABELS[1] -- these bits describe what a healthy PCS is
# DOING (running, standing by, charging/discharging, precharging, hitting a
# voltage/current limit), not a problem. This is a DIFFERENT catalog from
# OmniOps's generic PcsEvt1StatusHelper (bit0=Trip, bit2=Derating,
# bit4=IGBT/SCR Failure -- an EPC-oriented bit layout), which is why a
# healthy running Fractal PCS (bit1 "pcs_run" always set while running)
# falls into that helper's "any other bit != 0 -> Fault" catch-all.
PCS_STATUS_WORD_1_BENIGN_BITS = {
    0,   # run_mode
    1,   # pcs_run
    5,   # pcs_standby
    6,   # pcs_hot_standby
    7,   # pcs_charge_status
    8,   # pcs_discharge_status
    9,   # dc_voltage_limit_charge
    10,  # dc_voltage_limit_discharge
    11,  # current_limit_charge
    12,  # current_limit_discharge
    13,  # precharge_state
}

STATION_STATE_ENUM = {
    0: "INITIAL", 1: "SHUTDOWN", 2: "STANDBY", 3: "HOT_STANDBY",
    4: "CHARGING", 5: "DISCHARGING",
}


def _as_signed32(raw_value: int) -> int:
    return raw_value - 4294967296 if raw_value > 2147483647 else raw_value


def _combine32(high_word: int, low_word: int) -> int:
    return ((int(high_word) & 0xFFFF) << 16) | (int(low_word) & 0xFFFF)


def _connect(site_name: str, host: str):
    """Opens a Modbus TCP connection to site_name's simulator. Caller must
    close() it (each public read function below does this via try/finally)."""
    from pymodbus.client import ModbusTcpClient

    if site_name not in FRACTAL_SITE_MODBUS:
        raise KeyError(
            f"{site_name!r} not in FRACTAL_SITE_MODBUS -- add its (port, unit_id) "
            "to shared/config/settings.py (values come from launch_sites.py's "
            "startup log, e.g. 'puerto 5020, auto')")
    port, unit_id = FRACTAL_SITE_MODBUS[site_name]

    client = ModbusTcpClient(host, port=port)
    if not client.connect():
        raise ConnectionError(
            f"couldn't connect to the {site_name} simulator at {host}:{port} "
            "(is launch_sites.py still running?)")
    return client, unit_id


def _read_registers(client, unit_id, address, count):
    try:
        result = client.read_holding_registers(address, count=count, device_id=unit_id)
    except TypeError:
        result = client.read_holding_registers(address, count=count, slave=unit_id)
    if result.isError():
        raise IOError(f"error reading register {address} (unit {unit_id})")
    return result.registers


def _read_emu_uint16_scaled(site_name: str, offset: int, scale: float, host: str) -> float:
    """Shared implementation for any single-register, unsigned, scaled EMU
    field (system_soc_pct, system_soh_pct, ...)."""
    client, unit_id = _connect(site_name, host)
    try:
        registers = _read_registers(client, unit_id, EMU_BASE + offset, 1)
        return registers[0] * scale
    finally:
        client.close()


def _read_emu_int32_scaled(site_name: str, offset: int, scale: float, host: str) -> float:
    """Shared implementation for any two-register (32-bit), signed, scaled
    EMU field (active_power_kw, dc_current_a, ...)."""
    client, unit_id = _connect(site_name, host)
    try:
        registers = _read_registers(client, unit_id, EMU_BASE + offset, 2)
        raw_value = _as_signed32(_combine32(registers[0], registers[1]))
        return raw_value * scale
    finally:
        client.close()


def _read_emu_uint32_scaled(site_name: str, offset: int, scale: float, host: str) -> float:
    """Shared implementation for any two-register (32-bit), UNSIGNED, scaled
    EMU field (dc_voltage_v, ...) -- confirmed UINT32 (not INT32) against
    fractal_addressing_map.py's EMU_FIELDS, unlike dc_current_a/
    active_power_kw which are signed (charge/discharge sign matters for
    those; a DC bus voltage never goes negative)."""
    client, unit_id = _connect(site_name, host)
    try:
        registers = _read_registers(client, unit_id, EMU_BASE + offset, 2)
        raw_value = _combine32(registers[0], registers[1])
        return raw_value * scale
    finally:
        client.close()


def read_fractal_emu_pcs_comm_connected(site_name: str, pcs_index: int, host: str = SIM_HOST) -> bool:
    """Reads whether the EMU reports its RS485 link to one PCS as Connected
    -- EMU status_word_3, bit `pcs_index` (0-based; PCS #1 is bit 0).
    RS485 is the default PcsCommTransport (per
    docs/fractal-alarms-coverage-open-by-id 1.md's alarm #52 intake note,
    "aun no en Alarm Thresholds UI; default RS485"); CAN (status_word_5)
    isn't read here since BOLIVIA isn't configured for it. Ground truth for
    alarm #52 "EMS-PCS Comm Lost" -- the real signal behind the EMS IPC &
    Gateway card's "Data path" line."""
    client, unit_id = _connect(site_name, host)
    try:
        registers = _read_registers(client, unit_id, EMU_BASE + EMU_STATUS_WORD_3_RS485_OFFSET, 1)
        return bool(registers[0] & (1 << pcs_index))
    finally:
        client.close()


def read_fractal_pcs_active_power_kw(site_name: str, pcs_index: int, host: str = SIM_HOST) -> float:
    """Reads one PCS's own p_ac_kw -- ground truth for the Telemetry Data
    Table's per-device "Active Power" row (docs/OF-141.txt: PcsModule.p_ac_kw
    -> "Active Power" / "PCS / Inverter"), which shows one row per PCS
    (Device "PCS-1"/"PCS-2"/"PCS-3"), unlike the Device Status Panel's PCS
    card which sums all 3 (read_fractal_site_total_kw)."""
    client, unit_id = _connect(site_name, host)
    try:
        registers = _read_registers(client, unit_id, PCS_BASES[pcs_index] + PCS_P_AC_KW_OFFSET, 2)
        raw_value = _as_signed32(_combine32(registers[0], registers[1]))
        return raw_value * KW_SCALE
    finally:
        client.close()


def read_fractal_site_total_kw(site_name: str, host: str = SIM_HOST) -> float:
    """Sum of p_ac_kw across the site's 3 PCS instances -- the ground truth
    for the Device Status Panel's PCS/Inverter "Actual" value per
    docs/OF-140.txt's Calculo rule ("suma PCS individuales -> agregado SYS
    -> valor sitio"), NOT read_fractal_emu_active_power_kw's EMU-level
    aggregate (confirmed 2026-09-07 the two genuinely diverge by ~0.1 kW,
    rounding -- see that function's docstring)."""
    client, unit_id = _connect(site_name, host)
    try:
        total_kw = 0.0
        for pcs_base in PCS_BASES:
            registers = _read_registers(client, unit_id, pcs_base + PCS_P_AC_KW_OFFSET, 2)
            raw_value = _as_signed32(_combine32(registers[0], registers[1]))
            total_kw += raw_value * KW_SCALE
        return total_kw
    finally:
        client.close()


def read_fractal_meter_total_active_power_kw(site_name: str, host: str = SIM_HOST) -> float:
    """Reads PoiMeter.total_active_power_kw directly -- the real POI meter
    demand field Fractal DOES send (confirmed against
    omniops-bess-edge/modbus_common/fractal_addressing_map.py's METER_FIELDS,
    METER_BASE=35300). Ground truth for the Meters/CT-PT card: proves
    "Import / export tags partial" isn't "Missing" because Fractal DOES
    have real, live demand telemetry -- it's the OTHER required input
    ("carga real"/RealLoad) that's permanently absent, confirmed for BOTH
    manufacturers (docs/OF-140.txt line 322-325: "No en snapshot
    EPC/Fractal actual"), not a Fractal-only gap."""
    client, unit_id = _connect(site_name, host)
    try:
        registers = _read_registers(client, unit_id, METER_BASE + METER_TOTAL_ACTIVE_POWER_KW_OFFSET, 2)
        raw_value = _as_signed32(_combine32(registers[0], registers[1]))
        return raw_value * KW_SCALE
    finally:
        client.close()


def read_fractal_emu_active_power_kw(site_name: str, host: str = SIM_HOST) -> float:
    """Reads EmuStatus.active_power_kw directly -- the EMU's OWN reported
    site-level aggregate, as opposed to summing each PCS's p_ac_kw
    (read_fractal_site_total_kw). docs/OF-140.txt's Device Status Panel
    Calculo rule for the PCS/Inverter card says the site value must come
    from summing individual PCS values, NOT from this EMU-level field
    directly -- this function exists to let a test PROVE whether the two
    ever diverge, rather than assume the documented rule is moot (confirmed
    2026-09-07 they do, by ~0.1 kW of rounding)."""
    return _read_emu_int32_scaled(site_name, EMU_ACTIVE_POWER_KW_OFFSET, KW_SCALE, host)


def read_fractal_emu_station_state(site_name: str, host: str = SIM_HOST) -> str:
    """Reads EMU.station_state directly from the simulator -- the field
    that drives most of the Device Status Panel's card logic per
    docs/OF-140.txt (Battery/BMS, PCS/Inverter, Network/Tunnel all read
    this, as SysStatus). Ground truth for Device Status Panel cross-layer
    checks that don't go through DB (which the panel doesn't read -- see
    docs/OF-140.txt's own "Origen en pantalla (cache vs base de datos)"
    table)."""
    client, unit_id = _connect(site_name, host)
    try:
        registers = _read_registers(client, unit_id, EMU_BASE + EMU_STATION_STATE_OFFSET, 1)
        return STATION_STATE_ENUM.get(registers[0], f"UNKNOWN({registers[0]})")
    finally:
        client.close()


def read_fractal_emu_soc_pct(site_name: str, host: str = SIM_HOST) -> float:
    """Reads EmuStatus.system_soc_pct directly -- ground truth for the
    Battery/BMS card's "SoC range" line (docs/OF-140.txt: Fractal EMU
    SystemSocPct -> "SOC del sitio")."""
    return _read_emu_uint16_scaled(site_name, EMU_SYSTEM_SOC_PCT_OFFSET, PERCENT_SCALE, host)


def read_fractal_pcs_status_word_1(site_name: str, pcs_index: int, host: str = SIM_HOST) -> int:
    """Reads one PCS's raw status_word_1 register -- the bitfield that
    drives the PCS/Inverter card's PcsEvt1 status via
    PcsEvt1StatusHelper.MapCardStatus (docs/DeviceStatusPanel.md), decoded
    with an EPC-oriented bit catalog. `pcs_index` is 0/1/2 (PCS_BASES
    index), NOT the 1-based PCS number. Ground truth for proving that
    catalog mismatches Fractal's real bits (PCS_STATUS_WORD_1_BENIGN_BITS)."""
    client, unit_id = _connect(site_name, host)
    try:
        registers = _read_registers(client, unit_id, PCS_BASES[pcs_index] + PCS_STATUS_WORD_1_OFFSET, 1)
        return registers[0]
    finally:
        client.close()


def read_fractal_pcs_alarm_words(site_name: str, pcs_index: int, host: str = SIM_HOST) -> list[int]:
    """Reads all 30 of one PCS's raw alarm_word registers. All-zero means
    zero real alarms are active for that PCS -- used to prove a Fault pill
    isn't explained by a genuine alarm, only by the status_word_1 bit
    catalog mismatch (see read_fractal_pcs_status_word_1's docstring)."""
    client, unit_id = _connect(site_name, host)
    try:
        return _read_registers(client, unit_id, PCS_BASES[pcs_index] + PCS_ALARM_WORD_1_OFFSET,
                                PCS_ALARM_WORD_COUNT)
    finally:
        client.close()


def read_fractal_emu_dc_current_a(site_name: str, host: str = SIM_HOST) -> float:
    """Reads EmuStatus.dc_current_a directly -- ground truth for Dispatch
    Limits & Tracking's "DC Bus Current" (docs/OF-145.txt Calculo rule,
    preference order #1: "Voltaje y corriente del banco/sitio (mensaje del
    gateway)" -- this EMU-level site aggregate IS that banco/sitio value).
    Offset 33, INT32, scale 0.1 -- confirmed against
    omniops-bess-edge/modbus_common/fractal_addressing_map.py's EMU_FIELDS,
    not guessed."""
    return _read_emu_int32_scaled(site_name, EMU_DC_CURRENT_A_OFFSET, AMPS_SCALE, host)


def read_fractal_emu_dc_voltage_v(site_name: str, host: str = SIM_HOST) -> float:
    """Reads EmuStatus.dc_voltage_v directly -- ground truth for Dispatch
    Limits & Tracking's "DC Bus Voltage" (docs/OF-145.txt Calculo rule,
    same preference-order-#1 banco/sitio value as DC Bus Current above).
    Offset 35, UINT32, scale 0.1 -- confirmed against
    omniops-bess-edge/modbus_common/fractal_addressing_map.py's EMU_FIELDS,
    not guessed."""
    return _read_emu_uint32_scaled(site_name, EMU_DC_VOLTAGE_V_OFFSET, VOLTS_SCALE, host)


def read_fractal_emu_soh_pct(site_name: str, host: str = SIM_HOST) -> float:
    """Reads EmuStatus.system_soh_pct directly -- ground truth for the
    Battery/BMS card's "SoH" line (docs/OF-140.txt: Fractal EMU
    SystemSohPct -> "SOH del sitio"). Confirmed 2026-09-07 this is a
    straight passthrough (no aggregation/fallback) -- e.g. raw=990 ->
    99.0%, matching the UI exactly."""
    return _read_emu_uint16_scaled(site_name, EMU_SYSTEM_SOH_PCT_OFFSET, PERCENT_SCALE, host)
