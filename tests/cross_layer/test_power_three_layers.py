"""cross_layer — the power DIFFERENTIAL: simulator vs API vs UI.

Reads like a sentence:
  expected (simulator oracle)  ==  API (what OmniOps calculates)  ==  UI (what it shows)

Needs the stack up (simulator + OmniOps). If not, it's skipped (require_stack).
The assert lives HERE, in the test (not in another layer).
"""
import time

import pytest

from shared.datasource.modbus_source import read_sim_total_kw
from shared.domain import power
from shared.config.settings import SITE_ID, UI_TOL_KW

pytestmark = pytest.mark.cross_layer

TIMEOUT_S = 30


def _stable_reading(monitoring_service, attempts=8):
    """Gathers recent simulator and API readings to compare the same moment."""
    for _ in range(attempts):
        sim_kw, _ = read_sim_total_kw()
        summary = monitoring_service.get_summary(SITE_ID)
        api_kw = summary.actual_pcs_power_kw
        if api_kw is not None and power.matches(sim_kw, float(api_kw)):
            return sim_kw, float(api_kw)
        time.sleep(2)
    # last reading even if it didn't match (for the error message)
    return sim_kw, (float(api_kw) if api_kw is not None else None)


def test_backend_calculates_correctly(require_stack, monitoring_service):
    """CALC layer: OmniOps' API matches the simulator's oracle."""
    expected_kw, api_kw = _stable_reading(monitoring_service)
    assert api_kw is not None, "the API didn't return actualPcsPower"
    assert power.matches(expected_kw, api_kw), (
        f"the BACKEND calculates it wrong: expected {expected_kw:.0f} kW, "
        f"API {api_kw:.0f} kW")


def test_front_displays_correctly(require_stack, monitoring_service, monitoring_page):
    """SCREEN layer: the UI shows the same as the API (to 1 decimal)."""
    recent = []
    for _ in range(3):
        s = monitoring_service.get_summary(SITE_ID)
        if s.actual_pcs_power_kw is not None:
            recent.append(float(s.actual_pcs_power_kw))
        time.sleep(1)
    assert recent, "the API didn't return actualPcsPower"

    ui_kw = monitoring_page.read_pcs_power_kw()
    assert ui_kw is not None, "the screen doesn't show a usable value"
    assert any(abs(round(ui_kw, 1) - round(a, 1)) <= UI_TOL_KW for a in recent), (
        f"the FRONT displays it wrong: UI {ui_kw} kW vs recent API {recent}")
