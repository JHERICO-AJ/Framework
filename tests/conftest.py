"""Fixtures shared by ALL tests (they live at the root of tests/ so that
api/, ui/, and cross_layer/ can all see them alike)."""
import re
import socket
import urllib.error
import urllib.request

import pytest

import os

from shared.config.settings import (
    BASE_URL, SIM_HOST, SIM_PORT,
    QUOTATION_DB_HOST, QUOTATION_DB_PORT, QUOTATION_DB_NAME, QUOTATION_DB_USER, QUOTATION_DB_PASSWORD,
    CAPTURE_FAILURES, CAPTURES_DIR,
    CAPTURE_TRACES, TRACES_DIR,
    LOGIN_METHOD,
)
from shared.config.credentials import load_credentials, load_role_credentials
from shared.datasource.db_connection import db_is_configured, open_readonly_connection
from shared.auth.browser_cookie_export import write_cookie_file
from framework_api.client.api_client import ApiClient
from framework_api.services.alarms_service import AlarmsService
from framework_api.services.monitoring_service import MonitoringService
from framework_ui.browser.browser_factory import BrowserFactory
from framework_ui.pages.auth.login_page import LoginPage
from framework_ui.pages.monitoring.monitoring_page import MonitoringPage
from framework_ui.pages.alarms_events.alarms_page import AlarmsPage
from framework_ui.pages.fleet_overview.fleet_overview_page import FleetOverviewPage
from framework_ui.pages.quotation.quotation_page import QuotationPage


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


@pytest.fixture(scope="session")
def _role_browser():
    """A browser for the Quotation role tests that signs in nobody: unlike _browser_factory it does NOT log in the main OmniOps account (OMNIOPS_EMAIL, an admin) --
    the role tests only use the AM / FPM / BU / CEO test accounts."""
    factory = BrowserFactory()
    factory.__enter__()
    try:
        yield factory
    finally:
        factory.__exit__(None, None, None)


@pytest.fixture(scope="session")
def role_page(_role_browser):
    """role_page("FPM") -> a Playwright page logged in as that Quotation role, in its own browser context
    (the default logged_in_page stays on the main OmniOps account). Roles: AM, FPM, BU, CEO and the system's
    DEFAULT_FPM / DEFAULT_BU / DEFAULT_CEO approvers. Uses the app's native login whatever LOGIN_METHOD says,
    because these accounts exist only in the app. Skips (not fails) if the role's QUOTATION_<ROLE>_* isn't in
    .env. One login per role per session."""
    pages = {}

    def get(role):
        if role not in pages:
            creds = load_role_credentials(role)
            if creds is None:
                pytest.skip(f"QUOTATION_{role}_EMAIL / QUOTATION_{role}_PASSWORD not set in .env")
            page = _role_browser.new_isolated_page()
            LoginPage(page).login(creds["email"], creds["password"], method="native")
            page.wait_for_url(lambda url: "/login" not in url, timeout=20000)   # login() can return a moment before the redirect; a reload before it would reload /login
            pages[role] = page
        return pages[role]

    get.pages = pages
    return get


@pytest.fixture
def quotation_page(logged_in_page):
    return QuotationPage(logged_in_page).open()


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
    if not db_is_configured():
        pytest.skip("DB_HOST/DB_NAME/DB_USER/DB_PASSWORD not set in .env — "
                     "cross-layer DB checks need a Postgres connection")
    conn = open_readonly_connection()
    try:
        yield conn
    finally:
        conn.close()


@pytest.fixture(scope="session")
def quotation_db_conn():
    """MySQL backend for the Quotation module. Skips (not fails) if
    QUOTATION_DB_* isn't configured in .env, same pattern as db_conn.
    Read-only: no writes, ever, via this connection."""
    if not all([QUOTATION_DB_HOST, QUOTATION_DB_NAME, QUOTATION_DB_USER, QUOTATION_DB_PASSWORD]):
        pytest.skip("QUOTATION_DB_HOST/QUOTATION_DB_NAME/QUOTATION_DB_USER/QUOTATION_DB_PASSWORD "
                     "not set in .env — Quotation cross-layer DB checks need a MySQL connection")
    import pymysql
    conn = pymysql.connect(
        host=QUOTATION_DB_HOST, port=int(QUOTATION_DB_PORT), database=QUOTATION_DB_NAME,
        user=QUOTATION_DB_USER, password=QUOTATION_DB_PASSWORD,
        ssl={"ssl": {}}, cursorclass=pymysql.cursors.DictCursor,
    )
    try:
        yield conn
    finally:
        conn.close()


# ---- Quotation API sessions (one per role) and quotation factory -- shared by tests/api/quotation and tests/ui/quotation ----
@pytest.fixture(scope="session")
def api_roles():
    """{'AM'|'FPM'|'BU'|'CEO': RoleApiSession} -- skips the tests when a role account is not set in .env."""
    from framework_api.client.role_session import RoleApiSession
    sessions = {}
    for role in ("AM", "FPM", "BU", "CEO"):
        creds = load_role_credentials(role)
        if creds is None:
            pytest.skip(f"QUOTATION_{role}_EMAIL / QUOTATION_{role}_PASSWORD not set in .env")
        sessions[role] = RoleApiSession(creds["email"], creds["password"])
    return sessions


@pytest.fixture(scope="session")
def api_other(api_roles):
    """{'AM2'|'NOROLE': RoleApiSession} -- a second AM (to check that one AM cannot reach the quotations of another) and a user with no Quotation role.
    Skips the tests when the account is not set in .env."""
    from framework_api.client.role_session import RoleApiSession
    sessions = {}
    for role in ("AM2", "NOROLE"):
        creds = load_role_credentials(role)
        if creds is None:
            pytest.skip(f"QUOTATION_{role}_EMAIL / QUOTATION_{role}_PASSWORD not set in .env")
        sessions[role] = RoleApiSession(creds["email"], creds["password"])
    return sessions


@pytest.fixture(scope="session")
def quotation_api(api_roles):
    """{'AM'|'FPM'|'BU'|'CEO': QuotationService} -- the same API, called as each role."""
    from framework_api.services.quotation_service import QuotationService
    return {role: QuotationService(session) for role, session in api_roles.items()}


@pytest.fixture(scope="session")
def make_quotation(api_roles):
    """make_quotation(tag, route, arrangement=None) -> (quotation_id, quote_no): the AM creates and submits a quotation whose only signers are `route`."""
    from framework_api.services.quotation_setup import create_and_submit

    def make(tag, route, arrangement=None, title_prefix="HU22-API", extra=None):
        return create_and_submit(api_roles["AM"], api_roles, tag, route, arrangement=arrangement, title_prefix=title_prefix, extra=extra)
    return make


@pytest.fixture(scope="session")
def make_draft(api_roles):
    """make_draft(tag, arrangement=None, extra=None) -> (quotation_id, quote_no): the AM creates a quotation and leaves it as a Draft."""
    from framework_api.services.quotation_setup import create_draft

    def make(tag, arrangement=None, extra=None, title_prefix="HU15"):
        return create_draft(api_roles["AM"], api_roles, tag, arrangement=arrangement, title_prefix=title_prefix, extra=extra)
    return make


@pytest.fixture(scope="session")
def make_waiting_for_bu(api_roles):
    """make_waiting_for_bu(tag, arrangement=None, title_prefix="HU15", extra=None, route=("FPM", "BU")) -> (quotation_id, quote_no): a quotation whose route is `route`, after the FPM/FSM
    approved and the AM sent it on, so it waits for the BU. Since the QA build of 2026-10-23 an approver cannot open (HTTP 403) a quotation they do not sign, so the tests that
    open one as the BU or the CEO need them in the route."""
    from framework_api.services.quotation_service import QuotationService
    from framework_api.services.quotation_setup import create_and_submit

    def make(tag, arrangement=None, title_prefix="HU15", extra=None, route=("FPM", "BU")):
        qid, quote_no = create_and_submit(api_roles["AM"], api_roles, tag, list(route), arrangement=arrangement, title_prefix=title_prefix, extra=extra)
        assert QuotationService(api_roles["FPM"]).approve(qid, "FPM approves").status_code == 200
        assert QuotationService(api_roles["AM"]).submit(qid).status_code == 200
        return qid, quote_no
    return make


@pytest.fixture(scope="session")
def make_waiting_on_oem(api_roles):
    """make_waiting_on_oem(tag, title_prefix="OEM-API") -> (quotation_id, quote_no): a quotation signed by FPM/FSM, BU, CEO and the external OEM that went through the whole
    internal route, so it waits on the OEM. The system emails the QA test mailbox (framework_api.services.quotation_setup.OEM_TEST_EMAIL): one real email per quotation."""
    from framework_api.services.quotation_setup import create_waiting_on_oem

    def make(tag, title_prefix="OEM-API"):
        return create_waiting_on_oem(api_roles, tag, title_prefix=title_prefix)
    return make


@pytest.fixture(scope="session")
def ask_oem_link(request):
    """ask_oem_link(what) -> the OEM decision link that a person copies from the email (right click on a button, 'Copy link address').
    The link exists only in the email (the database keeps the hash), and Google does not let the framework read that mailbox, so this is the one manual step of the OEM tests.
    The Nth call takes the environment variable OEM_LINK_N (1, 2...) if it is set; otherwise it asks in the terminal. Without either, the test is skipped."""
    calls = []

    def ask(what):
        calls.append(what)
        from_env = os.environ.get(f"OEM_LINK_{len(calls)}", "").strip()
        if from_env:
            return from_env
        # the mailbox signed in once with tools/oem_mailbox_login.py: the link is read from the email (set OEM_MAILBOX_AUTO=0 to ask a person instead)
        quote = re.search(r"FSA\d+", what)
        if quote and os.environ.get("OEM_MAILBOX_AUTO", "1") != "0":
            from shared.utils import oem_mailbox
            if oem_mailbox.available():
                for _attempt in range(2):                # Gmail is sometimes slow to show the email
                    link = oem_mailbox.fetch_decision_link(quote.group(0), nth=sum(1 for c in calls if quote.group(0) in c), timeout=150)
                    if link:
                        return link
        import sys
        if not sys.stdin or not sys.stdin.isatty():
            pytest.skip(f"needs the OEM link of {what}: set OEM_LINK_{len(calls)} or run in a terminal")
        capture = request.config.pluginmanager.getplugin("capturemanager")
        with capture.global_and_fixture_disabled():
            link = input(f"\n[OEM] Copy the link of a button of {what} and paste it here: ").strip()
        if not link:
            pytest.skip(f"no link given for {what}")
        return link
    return ask
