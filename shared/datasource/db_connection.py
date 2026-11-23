"""One place that opens the read-only Postgres connection to the OmniOps database (omniOps_qa), for the tests and for the tools.

Read-only on purpose: the session is set read-only, nothing in shared/datasource runs anything but SELECT, and any destructive change
stays a manual, human-reviewed step (see tools/db/)."""
from __future__ import annotations

from shared.config.settings import DB_HOST, DB_NAME, DB_PASSWORD, DB_PORT, DB_USER


def db_is_configured() -> bool:
    return all([DB_HOST, DB_NAME, DB_USER, DB_PASSWORD])


def open_readonly_connection():
    """A psycopg2 connection in a read-only, autocommit session. The caller closes it."""
    import psycopg2
    connection = psycopg2.connect(host=DB_HOST, port=DB_PORT, dbname=DB_NAME, user=DB_USER, password=DB_PASSWORD)
    connection.set_session(readonly=True, autocommit=True)
    return connection
