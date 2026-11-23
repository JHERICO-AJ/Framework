"""Fixtures for the E2E-F0x Fractal alarm scenarios (the internal QA note 'Plan_Integral_Fractal'
section 7). These tests need a REAL local stack per site (simulator + our
own proxy + edge, see the internal QA note 'FRACTAL_ALARM_INJECTION_SETUP') -- they can't
run against just OmniOps like the rest of the UI suite, so they're marked
`local_fractal_sim` and SKIP (not fail) if that site's proxy isn't up.
"""
from __future__ import annotations

import socket

import pytest

from shared.config.settings import SIM_HOST, FRACTAL_SITE_MODBUS


def _port_open(host, port, timeout=1.5):
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


@pytest.fixture(scope="module")
def require_fractal_site():
    """Returns a function: require_fractal_site()('BOLIVIA 4') skips the
    test if that site's CANONICAL port (where our proxy should be
    listening, per FRACTAL_SITE_MODBUS) isn't responding. Module-scoped
    (not function): it's stateless (just returns a checker closure), and
    E2E-F11's own fixture needs to be module-scoped too (see that test
    file) -- a narrower-scoped fixture (F09/F10's function-scoped ones) can
    still depend on this fine, only the reverse direction errors."""
    def _require(site_name):
        if site_name not in FRACTAL_SITE_MODBUS:
            pytest.skip(f"{site_name!r} isn't in FRACTAL_SITE_MODBUS")
        port, _unit = FRACTAL_SITE_MODBUS[site_name]
        if not _port_open(SIM_HOST, port):
            pytest.skip(
                f"no proxy/simulator responding for {site_name!r} on "
                f"{SIM_HOST}:{port} -- see the internal QA note 'FRACTAL_ALARM_INJECTION_SETUP' "
                f"to bring up the local stack first")
    return _require
