"""HU-02 criterion 9 evidence, step 1: sends 10 emails (accents and symbols in the WO Title and the Cause) and moves them TOGETHER to 'Quotation'. Writes reports/hu02/slow_send.json (prefix and move time, UTC).
Step 2 is tests/ui/quotation/test_email_ingestion_slow_evidence.py (screenshots as the AM at 60 s and 120 s)."""
import datetime as dt
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import shared.config.settings  # noqa: F401,E402
from tests.cross_layer import hu02_emails as E            # noqa: E402
from shared.utils.outlook_ingest import OutlookSession    # noqa: E402

OUT = os.path.join(ROOT, "reports", "hu02")
os.environ.setdefault("OUTLOOK_SHOTS", OUT)
kind = sys.argv[1] if len(sys.argv) > 1 else "A"      # A = accents and symbols (HU02S), L = very long values without accents (HU02L)
CHANGES = {"A": {"WO Title": "{title} ñ é # &", "Cause": "Conexión floja en el rack Ñ-3"},
           "L": {"WO Title": "{title}", "Site Location": "L" * 600, "Unit Info": "U" * 600, "Device": "D" * 400, "Signal": "S" * 1200}}[kind]
prefix = os.environ.get("SLOW_PREFIX") or f"HU02{'S' if kind == 'A' else 'L'}-" + dt.datetime.now().strftime("%H%M%S")   # SLOW_PREFIX=HU02S-TEST runs the defect exactly as written
subjects = [f"{prefix}-{n:02d}" for n in range(1, 11)]
with OutlookSession() as o:
    for s in subjects:
        for attempt in (1, 2):                         # the Microsoft sign-in sometimes bounces the compose page: renew the session once and send again
            try:
                o.send_to_self(s, E.render(s, fields=E.replaced(CHANGES)))
                break
            except Exception as exc:
                print("send failed", s, attempt, type(exc).__name__, flush=True)
                if attempt == 2:
                    raise
                o._warm_up()
    moved = o.move_many(prefix, 10)
    assert moved, "the emails were not found in the Inbox"
json.dump({"prefix": prefix, "moved_utc": moved.isoformat(), "subjects": subjects}, open(os.path.join(OUT, "slow_send.json"), "w"), indent=1)
print("moved", prefix, moved.isoformat())
