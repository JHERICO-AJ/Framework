"""Fixtures shared by ALL tests (they live at the root of tests/ so that
api/, ui/, and cross_layer/ can all see them alike)."""
import socket

import pytest

from shared.config.settings import BASE_URL, SIM_HOST, SIM_PORT
from shared.config.credentials import load_credentials
from framework_api.client.api_client import ApiClient
from framework_api.services.alarms_service import AlarmsService
from framework_api.services.monitoring_service import MonitoringService
from framework_ui.browser.browser_factory import BrowserFactory
from framework_ui.pages.auth.login_page import LoginPage
from framework_ui.pages.monitoring.monitoring_page import MonitoringPage
from framework_ui.pages.alarms_events.alarms_page import AlarmsPage


# ---- base ----
@pytest.fixture(scope="session")
def base_url():
    return BASE_URL


@pytest.fixture(scope="session")
def credentials():
    return load_credentials()


def _port_open(host, port, timeout=1.5):
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


@pytest.fixture(scope="session")
def require_stack():
    """Skips the test (instead of failing) if the simulator/proxy isn't on 5020."""
    if not _port_open(SIM_HOST, SIM_PORT):
        pytest.skip(f"the simulator/proxy isn't responding on {SIM_HOST}:{SIM_PORT}")


# ---- API layer (no browser, fast) ----
@pytest.fixture(scope="session")
def api_client(base_url):
    return ApiClient(base_url)


@pytest.fixture(scope="session")
def alarms_service(api_client):
    return AlarmsService(api_client)


@pytest.fixture(scope="session")
def monitoring_service(api_client):
    return MonitoringService(api_client)


# ---- UI layer (browser + login ONCE per session) ----
@pytest.fixture(scope="session")
def logged_in_page(credentials):
    factory = BrowserFactory()
    page = factory.__enter__()
    try:
        LoginPage(page).login(credentials["email"], credentials["password"])
        yield page
    finally:
        factory.__exit__(None, None, None)


@pytest.fixture
def monitoring_page(logged_in_page):
    return MonitoringPage(logged_in_page).open()


@pytest.fixture
def alarms_page(logged_in_page):
    return AlarmsPage(logged_in_page).open()
