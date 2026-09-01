"""Fixtures shared by ALL tests (they live at the root of tests/ so that
api/, ui/, and cross_layer/ can all see them alike)."""
import socket
import urllib.error
import urllib.request

import pytest

import os

from shared.config.settings import (
    BASE_URL, SIM_HOST, SIM_PORT,
    DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASSWORD,
    CAPTURE_FAILURES, CAPTURES_DIR,
    CAPTURE_TRACES, TRACES_DIR,
    LOGIN_METHOD,
)
from shared.config.credentials import load_credentials
from shared.auth.browser_cookie_export import write_cookie_file
from framework_api.client.api_client import ApiClient
from framework_api.services.alarms_service import AlarmsService
from framework_api.services.monitoring_service import MonitoringService
from framework_ui.browser.browser_factory import BrowserFactory
from framework_ui.pages.auth.login_page import LoginPage
from framework_ui.pages.monitoring.monitoring_page import MonitoringPage
from framework_ui.pages.alarms_events.alarms_page import AlarmsPage
from framework_ui.pages.fleet_overview.fleet_overview_page import FleetOverviewPage


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


@pytest.fixture(scope="session")
def require_omniops():
    """Skips the test (instead of failing) if OmniOps itself isn't reachable at
    BASE_URL. For screens like Fleet Overview that don't depend on the Modbus
    simulator (see require_stack) — they need OmniOps up, not the simulator."""
    try:
        urllib.request.urlopen(BASE_URL, timeout=5)
    except urllib.error.HTTPError:
        pass  # reachable — a non-2xx (e.g. redirect to /login) still proves it's up
    except (urllib.error.URLError, TimeoutError) as e:
        pytest.skip(f"OmniOps isn't reachable at {BASE_URL}: {e}")


# ---- API layer (no browser, fast — UNLESS LOGIN_METHOD=microsoft) ----
@pytest.fixture(scope="session")
def api_client(request, base_url):
    """In native mode, this is genuinely browser-free (TokenAuth does its
    own POST /api/ExternalUserAuth/login). In microsoft mode, the native
    endpoint can't validate an SSO password (see shared/auth/factory.py),
    so there's no way around a real browser doing the OAuth popup dance at
    least once -- this reuses the SAME session _browser_factory already
    logs in for UI tests (request.getfixturevalue, not a fixture param, so
    a pure-API test run in native mode never triggers a browser at all)."""
    if LOGIN_METHOD == "microsoft":
        factory = request.getfixturevalue("_browser_factory")
        write_cookie_file(factory.context, domain_substring=base_url.split("//")[1])
    return ApiClient(base_url)


@pytest.fixture(scope="session")
def alarms_service(api_client):
    return AlarmsService(api_client)


@pytest.fixture(scope="session")
def monitoring_service(api_client):
    return MonitoringService(api_client)


# ---- UI layer (browser + login ONCE per session) ----
@pytest.fixture(scope="session")
def _browser_factory(credentials):
    """Session-scoped so the trace-per-test fixture below can reach the
    same context logged_in_page is using (BrowserFactory only used to hand
    back `page`; the context itself is needed for tracing.start_chunk/
    stop_chunk)."""
    factory = BrowserFactory()
    page = factory.__enter__()
    try:
        LoginPage(page).login(credentials["email"], credentials["password"])
        yield factory
    finally:
        factory.__exit__(None, None, None)


@pytest.fixture(scope="session")
def logged_in_page(_browser_factory):
    return _browser_factory.page


@pytest.fixture(autouse=True)
def _trace_per_test(request):
    """Wraps every UI test in its own trace CHUNK (the session's one
    continuous context.tracing.start() from BrowserFactory, sliced per
    test) -- saved to disk only if the test's CALL phase failed, discarded
    otherwise, so a green run doesn't pile up trace files.

    autouse + tries to grab _browser_factory lazily: a pure-API test (no
    browser fixture requested) never triggers _browser_factory at all, so
    this stays a no-op for those instead of spinning up a browser they
    don't need."""
    if not CAPTURE_TRACES or "_browser_factory" not in request.fixturenames:
        yield
        return

    factory = request.getfixturevalue("_browser_factory")
    factory.context.tracing.start_chunk()
    yield
    call_report = getattr(request.node, "rep_call", None)
    if call_report is not None and call_report.failed:
        os.makedirs(TRACES_DIR, exist_ok=True)
        safe_name = request.node.nodeid.replace("::", "__").replace("/", "_").replace("\\", "_")
        path = os.path.join(TRACES_DIR, f"{safe_name}.zip")
        factory.context.tracing.stop_chunk(path=path)
        print(f"\n[trace] failure trace saved: {path} -- view with "
              f"`playwright show-trace {path}`")
    else:
        factory.context.tracing.stop_chunk()


@pytest.fixture
def monitoring_page(logged_in_page):
    return MonitoringPage(logged_in_page).open()


@pytest.fixture
def alarms_page(logged_in_page):
    return AlarmsPage(logged_in_page).open()


@pytest.fixture
def fleet_overview_page(logged_in_page):
    return FleetOverviewPage(logged_in_page).open()


# ---- failure evidence (screenshot) ----
@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    """After each test phase, check if THIS phase just turned the test red
    (report.failed) and, only then, grab one screenshot from whichever
    Playwright `page` fixture the test used. One capture per failing test,
    not per assertion -- doesn't touch anything on a PASS.

    Looks for a fixture literally named "page" among the test's own
    fixtures (logged_in_page, fleet_overview_page, etc. all pass one along
    as `.page` on their Page Object -- but the raw fixture in scope here is
    named "page" only on the few tests that request it directly; most get
    it indirectly via a Page Object fixture, so we also check those).
    """
    outcome = yield
    report = outcome.get_result()
    # Stashed so the trace-per-test fixture (below) can check the CALL
    # phase's outcome during its own teardown (fixture teardown runs AFTER
    # this hook has already recorded "call").
    setattr(item, f"rep_{report.when}", report)

    if not (CAPTURE_FAILURES and report.when == "call" and report.failed):
        return

    page = None
    for fixture_value in item.funcargs.values():
        candidate = getattr(fixture_value, "page", fixture_value)
        if hasattr(candidate, "screenshot"):
            page = candidate
            break
    if page is None:
        return

    os.makedirs(CAPTURES_DIR, exist_ok=True)
    safe_name = item.nodeid.replace("::", "__").replace("/", "_").replace("\\", "_")
    path = os.path.join(CAPTURES_DIR, f"{safe_name}.png")
    try:
        page.screenshot(path=path, full_page=True)
        print(f"\n[capture] failure screenshot saved: {path}")
    except Exception as e:
        print(f"\n[capture] couldn't save failure screenshot: {e}")


# ---- DB (read-only cross-layer checks) ----
@pytest.fixture(scope="session")
def db_conn():
    """Skips the test (instead of failing) if DB_* isn't configured in .env
    -- same pattern as require_omniops. Read-only: nothing in
    shared/datasource/db_source.py runs anything but SELECT, and this
    connection is never used for DELETE/UPDATE (that stays a manual,
    human-reviewed step -- see tools/db/cleanup_bolivia_data.sql)."""
    if not all([DB_HOST, DB_NAME, DB_USER, DB_PASSWORD]):
        pytest.skip("DB_HOST/DB_NAME/DB_USER/DB_PASSWORD not set in .env — "
                     "cross-layer DB checks need a Postgres connection")
    import psycopg2
    conn = psycopg2.connect(
        host=DB_HOST, port=DB_PORT, dbname=DB_NAME,
        user=DB_USER, password=DB_PASSWORD,
    )
    conn.set_session(readonly=True, autocommit=True)
    try:
        yield conn
    finally:
        conn.close()
