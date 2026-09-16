"""OFFLINE unit test of the UI's pure logic (kW parsing). No browser."""
import pytest
from framework_ui.pages.monitoring.components.power_card import parse_kw


@pytest.mark.ui
def test_parse_kw():
    assert parse_kw("2486.5 kW") == 2486.5
    assert parse_kw("2,486.5") == 2486.5          # US format with thousands separator
    assert parse_kw("-696.5 kW") == -696.5
    assert parse_kw("") is None
    assert parse_kw("no data") is None
