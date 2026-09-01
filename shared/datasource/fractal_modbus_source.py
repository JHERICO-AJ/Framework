"""
fractal_modbus_source.py — reads live PCS power directly from a Fractal
simulator instance over Modbus TCP, bypassing OmniOps entirely (UI, API,
and DB all sit downstream of this same source).

Built for the "Power (kW)" cross-layer gap: confirmed 2026-08-28 that
Fractal telemetry isn't persisted to any table OmniOps exposes (see
db_source.get_pcs_power_kw's docstring) -- RawBaseData, TelemetryReading,
and dataprocessing.ProcessedBessData.Power_kW are all empty for BOLIVIA even
with the simulator running. Reading the simulator directly sidesteps that
gap: whatever it emits here is the same value the UI/API should eventually
show, regardless of what's or isn't cached/persisted in between.

Same pattern as shared/datasource/modbus_source.py (the EPC equivalent),
kept as a separate file rather than extending that one because the register
map, PCS block layout, and per-site port/unit topology are entirely
different (Fractal: one Modbus TCP instance PER SITE, auto-assigned port;
EPC: a single shared local simulator/proxy).

Field read: p_ac_kw, offset +8 within each PCS block (INT32, scale 0.1) --
see fractal_addressing_map.py (PCS_COMMON_FIELDS) in omniops-bess-edge.
Word order: high word first (big-endian), confirmed via
modbus_common/modbus_regcodec.py's combine32().

READ ONLY. pymodbus is only imported when connecting.
"""
from __future__ import annotations

from shared.config.settings import SIM_HOST, FRACTAL_SITE_MODBUS

PCS_BASES = (5000, 5300, 5600)
P_AC_KW_OFFSET = 8
P_AC_KW_SCALE = 0.1


def _as_signed32(val: int) -> int:
    return val - 4294967296 if val > 2147483647 else val


def _combine32(hi: int, lo: int) -> int:
    return ((int(hi) & 0xFFFF) << 16) | (int(lo) & 0xFFFF)


def _read_registers(client, unit_id, addr, count):
    try:
        rr = client.read_holding_registers(addr, count=count, device_id=unit_id)
    except TypeError:
        rr = client.read_holding_registers(addr, count=count, slave=unit_id)
    if rr.isError():
        raise IOError(f"error reading register {addr} (unit {unit_id})")
    return rr.registers


def read_fractal_site_total_kw(site_name: str, host: str = SIM_HOST) -> float:
    """Sum of p_ac_kw across the site's 3 PCS instances, read live from its
    simulator. site_name must be a key in FRACTAL_SITE_MODBUS
    (shared/config/settings.py) -- the port/unit_id topology launch_sites.py
    assigned this run."""
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
    try:
        total = 0.0
        for base in PCS_BASES:
            regs = _read_registers(client, unit_id, base + P_AC_KW_OFFSET, 2)
            raw = _as_signed32(_combine32(regs[0], regs[1]))
            total += raw * P_AC_KW_SCALE
        return total
    finally:
        client.close()
