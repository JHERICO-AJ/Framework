"""verify_monitoring_stat_aggregation — deep, one-off verification that
monitoring.MonitoringStat's own 5-min bucket aggregation correctly reflects
what the Fractal simulator is actually emitting, for Site Power Telemetry
(docs/OF-143.txt).

Why this exists (separate from the fast pytest suite): a chart-vs-
MonitoringStat comparison (tests/ui/monitoring/test_site_power_telemetry.py)
only proves the CHART correctly displays whatever is in that table -- not
that the table's own aggregation is correct. RawBaseData (the would-be raw-
ingestion layer to check against) is confirmed empty for BOLIVIA, so there's
no already-persisted raw layer to check retroactively. This script instead
samples the LIVE simulator directly, in real time, over one full soon-to-
complete 5-min bucket, then compares against that exact bucket once
MonitoringStat has it -- the only way to close this specific trust gap.

Confirmed 2026-09-11 this exact approach caught a real telemetry outage
(BOLIVIA's edge/simulator process had stopped emitting -- e.g. the host
machine slept -- for ~2h; every MonitoringStat bucket during that gap was
IsInterpolated=True, holding a near-constant fallback while the simulator
itself kept swinging through a full +/-8000 kW cycle). This script checks
IsInterpolated FIRST and reports that clearly instead of printing a
misleading numeric diff -- a mismatch during a real outage says nothing
about whether the aggregation formula itself is correct.

Takes ~6-8 minutes to run (waits for the next 5-min bucket boundary, then
samples for 5 minutes, then waits ~90s for ingestion). Not meant to run on
every test suite invocation -- use tests/ui/monitoring/test_site_power_telemetry.py's
test_telemetry_has_not_been_stuck_interpolating_too_long for that (fast,
no live sampling needed).

    python -m tools.verify_monitoring_stat_aggregation
"""
from __future__ import annotations

import datetime
import time

from shared.config.settings import DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASSWORD
from shared.datasource.db_source import get_site_ids, get_monitoring_stat_is_interpolated
from shared.datasource.fractal_modbus_source import read_fractal_site_total_kw, read_fractal_emu_soc_pct

SITE_NAME = "BOLIVIA"
SAMPLE_INTERVAL_S = 10
INGESTION_LAG_WAIT_S = 90


def _next_full_bucket_window():
    now = datetime.datetime.now(datetime.timezone.utc)
    minute = (now.minute // 5) * 5
    current_bucket_start = now.replace(minute=minute, second=0, microsecond=0)
    bucket_start = current_bucket_start + datetime.timedelta(minutes=5)
    return bucket_start, bucket_start + datetime.timedelta(minutes=5)


def run():
    import psycopg2

    bucket_start, bucket_end = _next_full_bucket_window()
    now = datetime.datetime.now(datetime.timezone.utc)
    print(f"now={now.isoformat()}  target bucket=[{bucket_start.isoformat()}, {bucket_end.isoformat()})")

    wait_s = (bucket_start - datetime.datetime.now(datetime.timezone.utc)).total_seconds()
    if wait_s > 0:
        print(f"waiting {wait_s:.0f}s for the bucket to start...")
        time.sleep(wait_s)

    samples = []
    while datetime.datetime.now(datetime.timezone.utc) < bucket_end:
        t = datetime.datetime.now(datetime.timezone.utc)
        kw = read_fractal_site_total_kw(SITE_NAME)
        soc = read_fractal_emu_soc_pct(SITE_NAME)
        samples.append((t, kw, soc))
        print(f"  sample @ {t.isoformat()}: kw={kw:.1f} soc={soc:.2f}")
        time.sleep(SAMPLE_INTERVAL_S)

    avg_kw = sum(s[1] for s in samples) / len(samples)
    avg_soc = sum(s[2] for s in samples) / len(samples)
    print(f"\nMY independent average over [{bucket_start.isoformat()}, {bucket_end.isoformat()}) "
          f"from {len(samples)} samples: kw={avg_kw:.3f} soc={avg_soc:.3f}")

    print(f"\nWaiting {INGESTION_LAG_WAIT_S}s for MonitoringStat's aggregation job to persist this bucket...")
    time.sleep(INGESTION_LAG_WAIT_S)

    conn = psycopg2.connect(host=DB_HOST, port=DB_PORT, dbname=DB_NAME, user=DB_USER, password=DB_PASSWORD)
    try:
        site_id = get_site_ids(conn, [SITE_NAME])[SITE_NAME]

        is_interpolated = get_monitoring_stat_is_interpolated(conn, site_id, bucket_start, bucket_end)
        if is_interpolated is None:
            print("\nNo MonitoringStat row yet for that bucket -- ingestion lag longer than "
                  f"{INGESTION_LAG_WAIT_S}s, or the bucket wasn't written at all.")
            return
        if is_interpolated:
            print(f"\nMonitoringStat's bucket is IsInterpolated=True -- real telemetry isn't "
                  f"reaching this table right now (see "
                  f"test_telemetry_has_not_been_stuck_interpolating_too_long). A numeric "
                  f"comparison against my live simulator average would be MEANINGLESS here: "
                  f"the stored value is a stale fallback, not a real aggregation of this "
                  f"window. Fix the telemetry gap first, then re-run this script.")
            return

        cur = conn.cursor()
        cur.execute(
            'SELECT "ActivePower" FROM monitoring."MonitoringStat" '
            'WHERE "SiteId" = %s AND "SubsystemName" = \'TRANSFORMER_PCS\' '
            'AND "DeviceName" = \'00:00:00:00:00:00\' AND "BucketTimestamp" = %s',
            (site_id, bucket_start),
        )
        db_kw = float(cur.fetchone()[0])
        cur.execute(
            'SELECT "Soc" FROM monitoring."MonitoringStat" '
            'WHERE "SiteId" = %s AND "SubsystemName" = \'BATTERY_BMS\' '
            'AND "DeviceName" = \'00:00:00:00:00:00\' AND "BucketTimestamp" = %s',
            (site_id, bucket_start),
        )
        db_soc = float(cur.fetchone()[0])

        print(f"\nMonitoringStat (real, not interpolated): ActivePower={db_kw:.3f} kW, Soc={db_soc:.3f}%")
        print(f"COMPARISON: my independent average={avg_kw:.3f} kW vs DB={db_kw:.3f} kW, "
              f"diff={abs(avg_kw - db_kw):.3f} kW")
        print(f"COMPARISON: my independent average SOC={avg_soc:.3f}% vs DB={db_soc:.3f}%, "
              f"diff={abs(avg_soc - db_soc):.3f} points")
    finally:
        conn.close()


if __name__ == "__main__":
    run()
