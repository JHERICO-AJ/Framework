"""Unit test OFFLINE de la lógica pura de la UI (parse de kW). Sin browser."""
import pytest
from framework_ui.pages.monitoring.components.power_card import parse_kw


@pytest.mark.ui
def test_parse_kw():
    assert parse_kw("2486.5 kW") == 2486.5
    assert parse_kw("2,486.5") == 2486.5          # formato US con separador de miles
    assert parse_kw("-696.5 kW") == -696.5
    assert parse_kw("") is None
    assert parse_kw("sin dato") is None
