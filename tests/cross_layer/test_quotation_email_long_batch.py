"""Quotation module -- HU-02 / OP-18 criteria 3, 8 and 9: a batch of 10 emails whose fields have very long values, moved to 'Quotation' TOGETHER (cases 2234 and 2235 of Qase suite 53).
Same rules as tests/cross_layer/test_quotation_email_ingestion.py (real emails, visible Chrome window, EMAIL_INGEST_TESTS=1). The module sends the 10 emails and moves them ONCE, then reads the database for
15 minutes (or until the 10 drafts exist) and records how many seconds each draft took. About 17 minutes per run.
  * test_c_new_slow_*: the 10 drafts exist within 1 minute (AC 9). Open defect Qase #233 -> strict xfail (when it XPASSes the defect is probably fixed).
  * test_c_new_lost_*: none of the 10 emails is left without a draft (AC 3, 8). Qase #234 appears in about 1 of 4 batches, so this one is a normal test: it fails only in the batches that lose an email."""
import datetime as dt
import os
import time

import pytest

from shared.utils.outlook_ingest import OutlookSession
from tests.cross_layer import hu02_emails as E
from tests.cross_layer import hu02_support as S

pytestmark = [pytest.mark.cross_layer,
              pytest.mark.skipif(not os.environ.get("EMAIL_INGEST_TESTS"), reason="sends real emails from the AM's Outlook (visible Chrome window): set EMAIL_INGEST_TESTS=1")]
LONG = {"WO Title": "{title}", "Site Location": "L" * 600, "Unit Info": "U" * 600, "Device": "D" * 400, "Signal": "S" * 1200}
ONE_MINUTE = 65
WAIT_MINUTES = 15


@pytest.fixture(scope="module")
def batch(db_conn):
    prefix = f"HU02B-{S.new_stamp()}"
    subjects = [f"{prefix}-{n:02d}" for n in range(1, 11)]
    with OutlookSession() as o:
        for s in subjects:
            for attempt in (1, 2):            # the Microsoft sign-in sometimes bounces the compose page: renew the session once and send again
                try:
                    o.send_to_self(s, E.render(s, fields=E.replaced(LONG)))
                    break
                except Exception:
                    if attempt == 2:
                        raise
                    o._warm_up()
        moved = o.move_many(prefix, 10)       # verifies that no email of the batch stays in the Inbox
        assert moved, "the 10 emails were not found in the Inbox to move them"
    end, seconds = time.time() + WAIT_MINUTES * 60, {}
    while time.time() < end and len(seconds) < 10:
        with db_conn.cursor() as cur:
            cur.execute('SELECT "CorreoAsunto","FechaCreacion" FROM quotation."Quotation" WHERE "CorreoAsunto" LIKE %s', (prefix + "-%",))
            seconds = {r[0]: (r[1] - moved).total_seconds() for r in cur.fetchall()}
        db_conn.rollback()
        if len(seconds) < 10:
            time.sleep(15)
    S.save_state("long_batch", {"prefix": prefix, "moved_utc": moved.isoformat(), "seconds": {k[-2:]: round(v) for k, v in seconds.items()}})
    return {"subjects": subjects, "seconds": seconds}


class TestLongValuesBatch:
    @pytest.mark.xfail(strict=True, reason="Qase #233: with 10 emails with very long values moved together the drafts take about 100 seconds, not 1 minute (AC 9)")
    def test_c_new_slow_ten_emails_with_long_values_have_their_drafts_within_one_minute(self, batch):
        late = {s[-2:]: (round(batch["seconds"][s]) if s in batch["seconds"] else None) for s in batch["subjects"] if s not in batch["seconds"] or batch["seconds"][s] > ONE_MINUTE}
        assert not late, f"drafts after 1 minute (number: seconds): {late}"

    def test_c_new_lost_none_of_ten_emails_with_long_values_is_left_without_a_draft(self, batch):
        missing = [s[-2:] for s in batch["subjects"] if s not in batch["seconds"]]
        assert not missing, f"no draft after {WAIT_MINUTES} minutes for the emails number {missing}"
