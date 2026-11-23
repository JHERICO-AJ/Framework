"""Quotation module -- HU-02 / OP-18 criterion 9 (draft within 1 minute): evidence for the defect about batches of emails with accents. Sends 10 emails (accents and symbols in the WO Title and the Cause),
moves them TOGETHER to 'Quotation', and as the AM takes a screenshot of Quotes in Progress 60 s and 120 s after the move. Result: reports/hu02/ev_slow_60s.png, ev_slow_120s.png and reports/hu02/slow_evidence.json.
Needs EMAIL_INGEST_TESTS=1 (real emails, visible Chrome window)."""
import datetime as dt
import json
import os
import re
import time

import pytest

from tests.ui.quotation.am_page import quotation_page  # noqa: F401  (the AM)

pytestmark = [pytest.mark.ui, pytest.mark.skipif(not os.environ.get("EMAIL_INGEST_TESTS"), reason="sends real emails: set EMAIL_INGEST_TESTS=1")]
SHOTS = os.path.join("reports", "hu02")


def wait_until(moment):
    while dt.datetime.utcnow() < moment:
        time.sleep(1)


def show_list(quotation_page, prefix, name):
    quotation_page.open(refresh=True)
    quotes = quotation_page.historical_quotes()
    quotes.open_in_progress()
    quotes.type_in_search(prefix)
    quotes.search_with_enter(prefix)
    quotation_page.page.wait_for_timeout(2500)
    quotation_page.page.screenshot(path=os.path.join(SHOTS, name + ".png"))
    return quotation_page.page.get_by_text(prefix).count()


def test_ev_slow_batch_of_10_emails_with_accents(quotation_page, db_conn):
    sent = json.load(open(os.path.join(SHOTS, "slow_send.json")))      # written by tools/hu02_slow_send.py right before this test
    prefix, moved = sent["prefix"], dt.datetime.fromisoformat(sent["moved_utc"])
    wait_until(moved + dt.timedelta(seconds=58))
    at60 = show_list(quotation_page, prefix, "ev_slow_60s")
    seen60 = dt.datetime.utcnow()
    wait_until(moved + dt.timedelta(seconds=118))
    at120 = show_list(quotation_page, prefix, "ev_slow_120s")
    with db_conn.cursor() as cur:
        cur.execute('SELECT "CorreoAsunto","QuoteNo","FechaCreacion" FROM quotation."Quotation" WHERE "CorreoAsunto" LIKE %s ORDER BY "FechaCreacion"', (prefix + "%",))
        rows = cur.fetchall()
    db_conn.rollback()
    secs = [round((r[2] - moved).total_seconds()) for r in rows]
    json.dump({"prefix": prefix, "moved_utc": moved.isoformat(), "rows_on_screen_at_60s": at60, "rows_on_screen_at_120s": at120, "seconds": secs, "quotes": [r[1] for r in rows]},
              open(os.path.join(SHOTS, "slow_evidence.json"), "w"), indent=1)
    assert len(rows) == 10, f"only {len(rows)} drafts exist"
