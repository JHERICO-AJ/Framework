"""
fractal_sim_proxy.py — Modbus PROXY for ONE Fractal site, sitting between the
edge/OmniOps and the REAL Fractal simulator, so alarms can be INJECTED
without touching omniops-bess-edge at all.

     edge/OmniOps ──► proxy (site's usual port) ──► REAL simulator (moved port)

Exact same idea as tools/sim_proxy.py (EPC), generalized to run ONE INSTANCE
PER SITE (each of the 5 BOLIVIA sites is its own Modbus TCP process with its
own port/unit_id -- shared/config/settings.FRACTAL_SITE_MODBUS). On every
read, the proxy fetches FRESH data from the real simulator and, if that
site has anything saved by shared/domain/fractal_register_injection.py
(one JSON file per site under FRACTAL_INJECT_STATE_DIR), overwrites those
registers before returning them.

WHY A SEPARATE FILE FROM tools/sim_proxy.py: EPC has a single shared local
simulator/proxy pair (SIM_PORT/SIM_REAL_PORT constants); Fractal has 5
independent per-site instances that can all run at once, so the port/unit
have to be CLI arguments, not fixed constants, and each proxy needs its own
site-scoped injection state.

HOW TO USE IT (locally, from the project ROOT):
  1) Launch the REAL simulator on a port DIFFERENT from what
     FRACTAL_SITE_MODBUS says for that site (e.g. site "BOLIVIA 4" is
     normally 5024 -- move the real one to 6024):
       python <path-to-omniops-bess-edge>\\utils\\launch_site.py ^
           .\\sites\\fractal-BOLIVIA4.local.yaml --port 6024
  2) Proxy claims the ORIGINAL port (5024) that edge/OmniOps already expects
     for "BOLIVIA 4":
       python -m tools.fractal_sim_proxy --site "BOLIVIA 4" --real-port 6024
  3) edge/OmniOps start as usual (they keep reading 5024 = the proxy now).
  4) Trigger an alarm whenever you want, from another terminal:
       python -c "from shared.domain.fractal_register_injection import save_state; \\
                  save_state('BOLIVIA 4', [70])"
       python -c "from shared.domain.fractal_register_injection import clear_state; \\
                  clear_state('BOLIVIA 4')"

Test the proxy without a real simulator (loopback):
  python -m tools.fractal_sim_proxy --self-check
"""

from __future__ import annotations

import argparse
import sys
import threading
import time

from pymodbus.client import ModbusTcpClient
from pymodbus.datastore import ModbusServerContext, ModbusSlaveContext
from pymodbus.server import StartTcpServer

from shared.config.settings import FRACTAL_SITE_MODBUS, SIM_HOST
from tools.proxy_blocks.fractal_proxy_block import FractalProxyBlock
from tools.proxy_blocks.fractal_upstream_reader import FractalUpstreamReader


def _make_context(site_name, real_host, real_port, unit):
    upstream = FractalUpstreamReader(real_host, real_port, unit)
    block = FractalProxyBlock(upstream, site_name)
    slave = ModbusSlaveContext(hr=block, ir=block, zero_mode=True)
    return ModbusServerContext(slaves=slave, single=True)


def run(site_name, real_port, listen_port=None, real_host=SIM_HOST, listen_host=SIM_HOST):
    if site_name not in FRACTAL_SITE_MODBUS:
        raise KeyError(
            f"{site_name!r} not in FRACTAL_SITE_MODBUS -- add it to "
            "shared/config/settings.py first")
    default_port, unit = FRACTAL_SITE_MODBUS[site_name]
    listen_port = listen_port or default_port

    print(f"Fractal proxy for {site_name!r} listening on {listen_host}:{listen_port} "
          f"(unit {unit})  ->  real simulator at {real_host}:{real_port}")
    print(f"Inject with:  from shared.domain.fractal_register_injection import save_state; "
          f"save_state({site_name!r}, [<alarm_ids>])\n")
    StartTcpServer(context=_make_context(site_name, real_host, real_port, unit),
                    address=(listen_host, listen_port))


# ---------------------------------------------------------------------------
def _self_check():
    """Real loopback: fake 'real sim' on one port, the proxy in front of it
    on another, reads through the proxy -- with and without injection."""
    from pymodbus.datastore import ModbusSequentialDataBlock
    from shared.domain.fractal_register_injection import save_state, clear_state

    print("(loopback: fake fractal sim 5697 -> proxy 5696 -> client)\n")
    SITE, PROXY_P, REAL_P, UNIT, PCS1_ALARM_WORD_4 = "SELFCHECK_SITE", 5696, 5697, 1, 5263

    real_block = ModbusSequentialDataBlock(0, [0] * 20000)
    ctx_real = ModbusServerContext(
        slaves=ModbusSlaveContext(hr=real_block, ir=real_block, zero_mode=True),
        single=True)
    threading.Thread(target=StartTcpServer,
                      kwargs={"context": ctx_real, "address": ("127.0.0.1", REAL_P)},
                      daemon=True).start()

    up = FractalUpstreamReader("127.0.0.1", REAL_P, UNIT)
    blk = FractalProxyBlock(up, SITE)
    ctx_proxy = ModbusServerContext(
        slaves=ModbusSlaveContext(hr=blk, ir=blk, zero_mode=True), single=True)
    threading.Thread(target=StartTcpServer,
                      kwargs={"context": ctx_proxy, "address": ("127.0.0.1", PROXY_P)},
                      daemon=True).start()
    time.sleep(1.5)

    cli = ModbusTcpClient("127.0.0.1", port=PROXY_P)
    cli.connect()

    def read(addr, count):
        try:
            rr = cli.read_holding_registers(addr, count=count, device_id=UNIT)
        except TypeError:
            rr = cli.read_holding_registers(addr, count=count, slave=UNIT)
        return list(rr.registers)

    ok = True

    def check(desc, got, exp):
        nonlocal ok
        good = got == exp
        ok = ok and good
        print(f"  {desc:55} {'OK' if good else f'FAIL got={got!r} exp={exp!r}'}")

    clear_state(SITE)
    without = read(PCS1_ALARM_WORD_4, 1)
    check("no injection, alarm_word_4 (PCS1)", without, [0])

    # inject alarm 46 (PCS Ground Fault, bit4 on alarm_word_4, PCS1)
    save_state(SITE, [46])
    with_ = read(PCS1_ALARM_WORD_4, 1)
    check("with injection ID 46, alarm_word_4 bit4 set", with_, [0b10000])

    clear_state(SITE)
    reverted = read(PCS1_ALARM_WORD_4, 1)
    check("after clear_state, back to 0", reverted, [0])

    # inject alarm 38 (analog REPLACE: vdc=950 -> raw 9500 at reg 5015)
    save_state(SITE, [38])
    tele = read(5015, 1)
    check("with injection ID 38 (analog), vdc reg -> 9500", tele, [9500])
    clear_state(SITE)

    cli.close()
    print("\n=> " + ("PROXY OK" if ok else "FAIL"))
    return ok


if __name__ == "__main__":
    if "--self-check" in sys.argv:
        sys.exit(0 if _self_check() else 1)

    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--site", required=True, help="Site name, e.g. 'BOLIVIA 4' (must be a key in FRACTAL_SITE_MODBUS)")
    parser.add_argument("--real-port", type=int, required=True, help="Port the REAL simulator was moved to")
    parser.add_argument("--real-host", default=SIM_HOST)
    parser.add_argument("--listen-port", type=int, default=None,
                         help="Defaults to the site's own port in FRACTAL_SITE_MODBUS")
    parser.add_argument("--listen-host", default=SIM_HOST)
    args = parser.parse_args()

    run(args.site, args.real_port, listen_port=args.listen_port,
        real_host=args.real_host, listen_host=args.listen_host)
