"""db_source.py — read-only queries against the OmniOps Postgres DB, used by
cross-layer Fleet Overview tests to get the real value the UI is SUPPOSED to
show (instead of hardcoding an expected number that breaks whenever the
simulator's randomized telemetry changes -- see
tests/ui/fleet_overview/test_fleet_overview_values.py).

Every function here does a plain SELECT. Nothing in this module writes to
the DB -- site data resets (DELETE) are a separate, manual, human-reviewed
step (see tools/db/cleanup_bolivia_data.sql), never something a test does
automatically.
"""
from __future__ import annotations


def count_all_sites(conn) -> int:
    """Total sites in the DB, across every team/manufacturer -- NOT just
    BOLIVIA. Read live rather than hardcoded because this fleet is shared
    (other people add sites without notice -- confirmed 2026-08-28, went
    from 9 to 13 sites between two test sessions)."""
    with conn.cursor() as cur:
        cur.execute('SELECT count(*) FROM "sites"."Site"')
        return cur.fetchone()[0]


def get_site_ids(conn, site_names: list[str]) -> dict[str, str]:
    """Returns {site_name: site_id} for the given names."""
    with conn.cursor() as cur:
        cur.execute(
            'SELECT "Name", "Id" FROM "sites"."Site" WHERE "Name" = ANY(%s)',
            (site_names,),
        )
        return {name: str(site_id) for name, site_id in cur.fetchall()}


def count_devices_by_level_code(conn, site_id: str, device_level_code: str) -> int:
    """Count of emsdevices."Device" rows for one site at a given
    DeviceLevelCode (e.g. "RACK", "PCS", "GATEWAY") -- confirmed schema
    2026-09-08. Ground truth for CA-09 (docs/OF-140.txt): "Sitio Fractal
    puede tener menos detalle de racks; no se inventan racks" -- a Fractal
    site's RACK count here should be 0, since Fractal's wire protocol has
    no rack-level telemetry to back a real rack device with."""
    with conn.cursor() as cur:
        cur.execute(
            'SELECT count(*) FROM emsdevices."Device" '
            'WHERE "SiteId" = %s AND "DeviceLevelCode" = %s',
            (site_id, device_level_code),
        )
        return cur.fetchone()[0]


def get_configured_gateway_ip(conn, site_id: str) -> str | None:
    """The site's configured (Intake) Gateway IP -- sites."SiteConfiguration".
    "GatewayIp". Ground truth for the EMS IPC & Gateway card's "Gateway IP"
    line: docs/OF-140.txt line 646-648 documents the fallback order as
    "Telemetria viva -> intake", and Fractal's emscommunication."RawBaseData"
    is confirmed empty for BOLIVIA (no live telemetry path populates
    LocalIp for Fractal -- same gap already documented for Power/SOC in
    fractal_modbus_source.py's module docstring), so this Intake value is
    the actual source for any Fractal site, not just a fallback."""
    with conn.cursor() as cur:
        cur.execute('SELECT "GatewayIp" FROM sites."SiteConfiguration" WHERE "SiteId" = %s', (site_id,))
        row = cur.fetchone()
        return row[0] if row else None


def get_recent_event_timestamps(conn, site_id: str, signal: str, limit: int = 200) -> list:
    """The `OccurredAt` timestamps of the most recent `limit` raw events for
    one signal (e.g. "PCS_COMM_LOST") -- events."Event", newest first.
    Ground truth for the RATE at which raw events are generated while a
    condition persists: confirmed 2026-09-08 that PCS_COMM_LOST events for
    BOLIVIA fire roughly every ~1.7s (2145 in the last hour alone), far
    faster than the documented 5-10s sampling interval
    (docs/OmniOps_Parameter_Mapping_V03). This is orthogonal to whatever
    "N communication warnings" the UI shows (that comes from a ~5s
    in-memory cache per docs/OF-140.txt's cache table, not this table
    directly) -- this checks the upstream event-generation rate itself,
    which IS durable/queryable."""
    with conn.cursor() as cur:
        cur.execute(
            'SELECT "OccurredAt" FROM events."Event" '
            'WHERE "SiteId" = %s AND "Signal" = %s '
            'ORDER BY "OccurredAt" DESC LIMIT %s',
            (site_id, signal, limit),
        )
        return [row[0] for row in cur.fetchall()]


def get_gateway_mac_ids(conn, site_id: str) -> list[str]:
    """Every registered MAC_ID identity for the site's GATEWAY-level
    device(s) -- emsdevices."Device" joined to emsdevices."DeviceIdentity".
    Ground truth for the EMS IPC & Gateway card's "MAC" line per
    docs/OmniOps_Parameter_Mapping_V03: MAC should come from the "Gateway /
    IPC asset registry", not live telemetry (Fractal's wire protocol has no
    MAC field at all). Returns a list, not a single value, because BOLIVIA
    is confirmed (2026-09-08) to have TWO GATEWAY-level devices both marked
    IsPrimary -- a data-quality issue in its own right, but orthogonal to
    whether the UI correctly displays whatever IS registered."""
    with conn.cursor() as cur:
        cur.execute(
            'SELECT di."IdentityValue" FROM emsdevices."Device" d '
            'JOIN emsdevices."DeviceIdentity" di ON di."DeviceId" = d."Id" '
            'WHERE d."SiteId" = %s AND d."DeviceLevelCode" = \'GATEWAY\' AND di."IdentityType" = \'MAC_ID\'',
            (site_id,),
        )
        return [row[0] for row in cur.fetchall()]


def count_monitoring_stat_rows_by_interpolated(conn, site_id: str) -> dict[bool, int]:
    """{True: N, False: M} -- how many monitoring."MonitoringStat" rows for
    this site are interpolated vs not. Ground truth for the "Browse
    snapshots" modal's historical Quality (Good = not interpolated,
    Uncertain = interpolated, per docs/ComponentesStatusMonitorign.md sec
    8 / docs/OF-140.txt): if every row is interpolated, "Good" can never
    appear for this site, regardless of how continuous its real telemetry
    actually was."""
    with conn.cursor() as cur:
        cur.execute(
            'SELECT "IsInterpolated", count(*) FROM monitoring."MonitoringStat" '
            'WHERE "SiteId" = %s GROUP BY 1',
            (site_id,),
        )
        return dict(cur.fetchall())


def get_minutes_since_last_real_monitoring_stat_sample(conn, site_id: str) -> float | None:
    """Minutes between now and the most recent NON-interpolated (real)
    monitoring."MonitoringStat" row for this site's site-level
    TRANSFORMER_PCS aggregate -- None if there has NEVER been a real
    sample. Confirmed 2026-09-11: BOLIVIA's real telemetry stopped
    arriving around 23:55 UTC (edge/simulator process presumably stopped
    emitting -- e.g. the host machine slept), and every bucket since has
    been IsInterpolated=True, silently holding a near-constant fallback
    value instead of reflecting the actual (still-running, verified live
    via direct Modbus reads) simulator. A plain "does the chart match
    MonitoringStat" check can't catch this -- both sides agree on the same
    stale interpolated value. This is the ground truth for a real
    telemetry-freshness health check instead."""
    with conn.cursor() as cur:
        cur.execute(
            'SELECT max("BucketTimestamp") FROM monitoring."MonitoringStat" '
            'WHERE "SiteId" = %s AND "SubsystemName" = \'TRANSFORMER_PCS\' '
            'AND "DeviceName" = \'00:00:00:00:00:00\' AND "IsInterpolated" = false',
            (site_id,),
        )
        last_real = cur.fetchone()[0]
        if last_real is None:
            return None
        cur.execute("SELECT now()")
        now = cur.fetchone()[0]
        return (now - last_real).total_seconds() / 60.0


def get_monitoring_stat_is_interpolated(conn, site_id: str, window_start, window_end) -> bool | None:
    """Whether the site-level TRANSFORMER_PCS bucket in [window_start,
    window_end) is IsInterpolated -- None if no row exists yet for that
    window. A live-simulator-vs-MonitoringStat value comparison is only
    meaningful when this is False: an interpolated bucket holds a fallback
    value with no real telemetry behind it for that window at all, so
    comparing it against a fresh simulator reading always "fails" for a
    reason that has nothing to do with whether the aggregation formula
    itself is correct (confirmed 2026-09-11 -- see
    get_minutes_since_last_real_monitoring_stat_sample's docstring)."""
    with conn.cursor() as cur:
        cur.execute(
            'SELECT "IsInterpolated" FROM monitoring."MonitoringStat" '
            'WHERE "SiteId" = %s AND "SubsystemName" = \'TRANSFORMER_PCS\' '
            'AND "DeviceName" = \'00:00:00:00:00:00\' '
            'AND "BucketTimestamp" >= %s AND "BucketTimestamp" < %s',
            (site_id, window_start, window_end),
        )
        row = cur.fetchone()
        return bool(row[0]) if row else None


def get_latest_monitoring_stat_soc(conn, site_id: str) -> tuple | None:
    """(BucketTimestamp, Soc) of the most recent site-level BATTERY_BMS row
    in monitoring."MonitoringStat" -- ground truth for Site Power
    Telemetry's always-visible "Site SOC (%)" line (docs/OF-143.txt: "Fuente
    main data source for the chart" is this exact table, not live memory state,
    unlike the diagnostic cards). The site-level row is DeviceName
    '00:00:00:00:00:00' (the same placeholder gateway identity already
    confirmed for BOLIVIA's registered MAC -- see get_gateway_mac_ids),
    NOT a per-rack row -- confirmed 2026-09-10 this is the only BATTERY_BMS
    row carrying a non-null Soc for BOLIVIA. None if no rows exist yet."""
    with conn.cursor() as cur:
        cur.execute(
            'SELECT "BucketTimestamp", "Soc" FROM monitoring."MonitoringStat" '
            'WHERE "SiteId" = %s AND "SubsystemName" = \'BATTERY_BMS\' AND "Soc" IS NOT NULL '
            'ORDER BY "BucketTimestamp" DESC LIMIT 1',
            (site_id,),
        )
        row = cur.fetchone()
        return (row[0], float(row[1])) if row else None


def _monitoring_stat_window_avg(conn, site_id, subsystem_name, device_name, column, window_start, window_end,
                                 hourly_samples_only=False):
    """Shared implementation: average of `column` for one subsystem/device
    over [window_start, window_end) -- the exact bucket boundary ground
    truth for one Site Power Telemetry chart point (docs/OF-143.txt: 24h
    plots ~1 point per COMPLETE HOUR, 7d/30d plot ~1 point per COMPLETE DAY
    -- "sin la hora/el dia en curso"). Confirmed 2026-09-10 this exact-window
    approach is what's actually needed: an earlier "average of the last N
    minutes from now" approximation gave false multi-MW mismatches purely
    from not aligning to the same clock boundary the chart uses, not from
    any real calculation bug (see git history on this function for the
    before/after). `device_name=None` omits that filter (site-aggregate
    subsystems like METER have no per-device split worth narrowing).

    `hourly_samples_only=True` -- confirmed 2026-09-13 via
    MonitoringStatRepository.GetStatsForPowerTrendAsync: for a 7d/30d
    ("wide") window, the backend's own SQL query restricts to
    `BucketTimestamp.Minute == 0` BEFORE averaging -- a full day's chart
    point is the average of ~24 once-per-HOUR samples, never a flat
    average of all ~288 raw 5-min buckets in that day. Confirmed exact
    match (2049.75 kW) against the real API once this restriction was
    applied; the flat-average approach was off by ~30-50% for a day with
    uneven per-hour sample density (a real, confirmed gap for BOLIVIA)."""
    with conn.cursor() as cur:
        query = (
            f'SELECT avg("{column}") FROM monitoring."MonitoringStat" '
            'WHERE "SiteId" = %s AND "SubsystemName" = %s '
            f'AND "{column}" IS NOT NULL AND "BucketTimestamp" >= %s AND "BucketTimestamp" < %s'
        )
        params = [site_id, subsystem_name, window_start, window_end]
        if device_name is not None:
            query += ' AND "DeviceName" = %s'
            params.append(device_name)
        if hourly_samples_only:
            query += ' AND EXTRACT(MINUTE FROM "BucketTimestamp") = 0'
        cur.execute(query, params)
        result = cur.fetchone()[0]
        return float(result) if result is not None else None


def get_monitoring_stat_active_power_avg_kw(conn, site_id: str, window_start, window_end,
                                             hourly_samples_only=False) -> float | None:
    """Average ActivePower (kW) for the site-level TRANSFORMER_PCS row over
    an exact [window_start, window_end) boundary -- ground truth for Site
    Power Telemetry's Sigma PCS Active Power (PCS Power focus). NOT the
    right ground truth for Charge/Discharge Power (Battery/BMS focus) once
    a window spans a sign change (7d/30d's daily points) -- see
    get_monitoring_stat_charge_power_avg_kw/get_monitoring_stat_discharge_power_avg_kw
    for that. Pass hourly_samples_only=True for a 7d/30d (full-day) window
    -- see _monitoring_stat_window_avg's docstring."""
    return _monitoring_stat_window_avg(
        conn, site_id, "TRANSFORMER_PCS", "00:00:00:00:00:00", "ActivePower", window_start, window_end,
        hourly_samples_only=hourly_samples_only)


def _monitoring_stat_signed_power_avg(conn, site_id, window_start, window_end, charge_side: bool,
                                       hourly_samples_only=False) -> float | None:
    """Average of the site's ActivePower (kW) clamped to one sign and
    zero-filled on the other side, over ALL rows in the window -- e.g. for
    charge_side=True: avg(GREATEST(-ActivePower, 0)) across every row,
    including rows where the site was discharging (contributing 0, not
    excluded). Confirmed 2026-09-10 this -- not a plain average of only the
    same-sign rows -- is what Charge/Discharge Power actually compute:
    docs/OF-143.txt's Calculo rule ("negativa -> carga; positiva ->
    descarga") is applied PER-SAMPLE before aggregation, so a day where the
    site both charged and discharged correctly ends up with BOTH Charge and
    Discharge Power nonzero (each diluted by the samples where it was 0) --
    confirmed live: averaging only the negative subset overshot the chart's
    real value by ~2x, while this zero-fill version landed within ~5%.
    Also correct for a single-sign 24h hourly window (e.g. a window with
    only positive samples: GREATEST(-x, 0) is 0 for every row -> Charge
    Power correctly averages to 0, matching the plain sign-based approach
    exactly in that simpler case).

    hourly_samples_only=True (7d/30d full-day windows): confirmed
    2026-09-13 the real backend restricts to `BucketTimestamp.Minute == 0`
    samples before averaging for these wide windows (see
    _monitoring_stat_window_avg's docstring) -- confirmed EXACT match
    (2049.75 kW charge / 1776.08 kW discharge) against the real API once
    applied; a flat average over every 5-min bucket in the day does NOT
    match once the day has uneven per-hour sample density."""
    column_expr = 'GREATEST(-"ActivePower", 0)' if charge_side else 'GREATEST("ActivePower", 0)'
    with conn.cursor() as cur:
        query = (
            f'SELECT avg({column_expr}) FROM monitoring."MonitoringStat" '
            'WHERE "SiteId" = %s AND "SubsystemName" = \'TRANSFORMER_PCS\' '
            'AND "DeviceName" = \'00:00:00:00:00:00\' AND "ActivePower" IS NOT NULL '
            'AND "BucketTimestamp" >= %s AND "BucketTimestamp" < %s'
        )
        params = [site_id, window_start, window_end]
        if hourly_samples_only:
            query += ' AND EXTRACT(MINUTE FROM "BucketTimestamp") = 0'
        cur.execute(query, params)
        result = cur.fetchone()[0]
        return float(result) if result is not None else None


def get_monitoring_stat_charge_power_avg_kw(conn, site_id: str, window_start, window_end,
                                             hourly_samples_only=False) -> float | None:
    """Ground truth for Site Power Telemetry's Charge Power (Battery/BMS
    focus) over an exact [window_start, window_end) boundary -- see
    _monitoring_stat_signed_power_avg for why this is a zero-fill average,
    not a filtered one, and for the hourly_samples_only=True (7d/30d) case."""
    return _monitoring_stat_signed_power_avg(conn, site_id, window_start, window_end, charge_side=True,
                                              hourly_samples_only=hourly_samples_only)


def get_monitoring_stat_discharge_power_avg_kw(conn, site_id: str, window_start, window_end,
                                                hourly_samples_only=False) -> float | None:
    """Ground truth for Site Power Telemetry's Discharge Power (Battery/BMS
    focus) -- see get_monitoring_stat_charge_power_avg_kw's docstring."""
    return _monitoring_stat_signed_power_avg(conn, site_id, window_start, window_end, charge_side=False,
                                              hourly_samples_only=hourly_samples_only)


def get_monitoring_stat_meter_demand_avg_kw(conn, site_id: str, window_start, window_end) -> float | None:
    """Same exact-window ground truth as
    get_monitoring_stat_active_power_avg_kw, for the site meter's
    MeterDemand (kW) -- feeds Site Power Telemetry's Meter / CT-PT focus."""
    return _monitoring_stat_window_avg(
        conn, site_id, "METER", "Site Meter", "MeterDemand", window_start, window_end)


def _monitoring_stat_meter_import_export_avg_kw(conn, site_id, window_start, window_end, import_side: bool,
                                                 hourly_samples_only=False) -> float | None:
    """Ground truth for Site Power Telemetry's Import Power / Export Power
    (Meter / CT-PT focus). Backend formula (PowerTrendPointMapper.
    ResolveImportExport, meter branch -- confirmed live BOLIVIA always has
    MeterDemand populated, so the EgFromGrid/EgToGrid and signedPower
    fallbacks never trigger there): Import = max(MeterDemand, 0),
    Export = abs(min(MeterDemand, 0)) -- same zero-fill-the-other-side
    pattern already confirmed for Charge/Discharge Power (see
    _monitoring_stat_signed_power_avg's docstring), applied PER-SAMPLE
    before averaging, not a plain average of only same-sign rows. Pass
    hourly_samples_only=True for a 7d/30d window."""
    column_expr = 'GREATEST("MeterDemand", 0)' if import_side else 'GREATEST(-"MeterDemand", 0)'
    with conn.cursor() as cur:
        query = (
            f'SELECT avg({column_expr}) FROM monitoring."MonitoringStat" '
            'WHERE "SiteId" = %s AND "SubsystemName" = \'METER\' AND "DeviceName" = \'Site Meter\' '
            'AND "MeterDemand" IS NOT NULL AND "BucketTimestamp" >= %s AND "BucketTimestamp" < %s'
        )
        params = [site_id, window_start, window_end]
        if hourly_samples_only:
            query += ' AND EXTRACT(MINUTE FROM "BucketTimestamp") = 0'
        cur.execute(query, params)
        result = cur.fetchone()[0]
        return float(result) if result is not None else None


def get_monitoring_stat_import_power_avg_kw(conn, site_id: str, window_start, window_end,
                                             hourly_samples_only=False) -> float | None:
    """Ground truth for Site Power Telemetry's Import Power (Meter / CT-PT
    focus) -- see _monitoring_stat_meter_import_export_avg_kw's docstring."""
    return _monitoring_stat_meter_import_export_avg_kw(conn, site_id, window_start, window_end, import_side=True,
                                                        hourly_samples_only=hourly_samples_only)


def get_monitoring_stat_export_power_avg_kw(conn, site_id: str, window_start, window_end,
                                             hourly_samples_only=False) -> float | None:
    """Ground truth for Site Power Telemetry's Export Power (Meter / CT-PT
    focus) -- see _monitoring_stat_meter_import_export_avg_kw's docstring."""
    return _monitoring_stat_meter_import_export_avg_kw(conn, site_id, window_start, window_end, import_side=False,
                                                        hourly_samples_only=hourly_samples_only)


def get_monitoring_stat_pcs_sum_active_power_avg_kw(conn, site_id: str, window_start, window_end,
                                                     hourly_samples_only=False) -> float | None:
    """Ground truth for Site Power Telemetry's Sigma PCS Active Power
    (PCS Power focus) -- the TRUE sum of the individual PCS-1/PCS-2/PCS-3
    ActivePower rows for each bucket (excluding the site-level SYS
    aggregate row), then averaged over [window_start, window_end).
    Deliberately NOT the same as get_monitoring_stat_active_power_avg_kw
    (which reads the SYS row directly) -- comparing this against the real
    API's pcsTotalPower is how the double-counting defect was confirmed:
    the API's own value equals SYS + (PCS-1+PCS-2+PCS-3) summed together,
    roughly double the true per-bucket PCS sum (confirmed exact match
    2026-09-14: DB sum-of-SYS-and-PCS = 9041.39 kW = the real API value).
    Pass hourly_samples_only=True for a 7d/30d window (see
    _monitoring_stat_window_avg's docstring)."""
    with conn.cursor() as cur:
        query = (
            'SELECT avg(bucket_sum) FROM ('
            '    SELECT "BucketTimestamp", sum("ActivePower") AS bucket_sum'
            '    FROM monitoring."MonitoringStat"'
            '    WHERE "SiteId" = %s AND "SubsystemName" = \'TRANSFORMER_PCS\''
            '    AND "DeviceName" IN (\'PCS-1\', \'PCS-2\', \'PCS-3\')'
            '    AND "ActivePower" IS NOT NULL AND "BucketTimestamp" >= %s AND "BucketTimestamp" < %s'
        )
        params = [site_id, window_start, window_end]
        if hourly_samples_only:
            query += '    AND EXTRACT(MINUTE FROM "BucketTimestamp") = 0'
        query += '    GROUP BY "BucketTimestamp") t'
        cur.execute(query, params)
        result = cur.fetchone()[0]
        return float(result) if result is not None else None


def get_monitoring_stat_soc_avg(conn, site_id: str, window_start, window_end,
                                 hourly_samples_only=False) -> float | None:
    """Same exact-window ground truth as get_monitoring_stat_active_power_avg_kw,
    for Site SOC (%) -- for the 7d/30d views, where each chart point is a
    full-day AVERAGE (docs/OF-143.txt "7 d/30 d: ... Misma logica de
    agregacion [que 24h]"), not the single latest reading
    (get_latest_monitoring_stat_soc is the right ground truth for 24h's
    still-forming/most-recent point instead). Pass hourly_samples_only=True
    for a 7d/30d window -- see _monitoring_stat_window_avg's docstring
    (the real backend only samples once-per-hour buckets for these wide
    windows before averaging)."""
    return _monitoring_stat_window_avg(
        conn, site_id, "BATTERY_BMS", "00:00:00:00:00:00", "Soc", window_start, window_end,
        hourly_samples_only=hourly_samples_only)


def get_monitoring_stat_data_freshness_avg_seconds(conn, site_id: str, window_start, window_end,
                                                    hourly_samples_only=False) -> float | None:
    """Ground truth for Site Power Telemetry's Data Freshness (s) (EMS &
    Network focus). Backend formula (PowerTrendPointMapper.
    ResolveDataFreshnessSeconds + PowerTrendGatewayMerger.
    LatestSourceTimestamp): per bucket, the merged "site" row's
    SourceTimestamp is the LATEST SourceTimestamp among every "gateway
    partition" row sharing that BucketTimestamp (every row whose DeviceName
    doesn't contain PCS/RACK and isn't HVAC -- for BOLIVIA that's the
    EMS_GATEWAY/TRANSFORMER_PCS/BATTERY_BMS SYS rows plus Site Meter);
    freshness = max(BucketTimestamp - that merged SourceTimestamp, 0)
    seconds. Almost always 0 (the source reading typically lands AFTER its
    own bucket's start, near the window's end) -- confirmed live on BOLIVIA
    that a small minority of buckets (3/718 rows checked 2026-09-14) do
    have SourceTimestamp <= BucketTimestamp and genuinely register a
    nonzero delay, so this is NOT a vacuous field like IsInterpolated.
    Pass hourly_samples_only=True for a 7d/30d window."""
    with conn.cursor() as cur:
        query = (
            'SELECT avg(freshness) FROM ('
            '    SELECT "BucketTimestamp",'
            '           GREATEST(EXTRACT(EPOCH FROM ("BucketTimestamp" - max("SourceTimestamp"))), 0) AS freshness'
            '    FROM monitoring."MonitoringStat"'
            '    WHERE "SiteId" = %s'
            '    AND ("DeviceName" IS NULL OR ("DeviceName" NOT ILIKE \'%%PCS%%\' AND "DeviceName" NOT ILIKE \'%%RACK%%\'))'
            '    AND "SubsystemName" NOT IN (\'THERMAL_HVAC\')'
            '    AND "DeviceName" NOT ILIKE \'%%HVAC%%\''
            '    AND "SourceTimestamp" IS NOT NULL'
            '    AND "BucketTimestamp" >= %s AND "BucketTimestamp" < %s'
        )
        params = [site_id, window_start, window_end]
        if hourly_samples_only:
            query += '    AND EXTRACT(MINUTE FROM "BucketTimestamp") = 0'
        query += '    GROUP BY "BucketTimestamp") t'
        cur.execute(query, params)
        result = cur.fetchone()[0]
        return float(result) if result is not None else None


def get_recent_events(conn, site_id: str, limit: int = 100) -> list[dict]:
    """The most recent `limit` events."Event" rows for this site, newest
    first -- ground truth for Event Log's live table (docs/OF-293.txt:
    "Live card: last 100 events + real-time push"). Each row's
    Metadata (jsonb) carries triggerSource/cause/alarmCode/serviceName --
    the raw material for the UI's own Source/Description priority rules
    (CA-27/CA-28), not something to re-derive from other columns."""
    with conn.cursor() as cur:
        cur.execute(
            'SELECT "Subsystem", "Signal", "Description", "Severity", "Type", '
            '"OccurredAt", "Metadata" FROM events."Event" '
            'WHERE "SiteId" = %s ORDER BY "OccurredAt" DESC LIMIT %s',
            (site_id, limit),
        )
        columns = ["subsystem", "signal", "description", "severity", "type", "occurred_at", "metadata"]
        return [dict(zip(columns, row)) for row in cur.fetchall()]


def count_events_in_window(conn, site_id: str, window_start, window_end) -> int:
    """How many events."Event" rows exist for this site in
    [window_start, window_end) -- ground truth for Event Log's "Browse
    history" modal query limits (docs/OF-293.txt: 24h<=1000, 7d<=2000,
    30d<=5000 events) and its truncation warning (CA-32). Read directly
    rather than hardcoded: BOLIVIA's real PCS_COMM_LOST rate is already
    confirmed abnormally high (69,000+ total), so whether a given window
    is actually AT the query limit is a live fact, not something to
    assume."""
    with conn.cursor() as cur:
        cur.execute(
            'SELECT count(*) FROM events."Event" '
            'WHERE "SiteId" = %s AND "OccurredAt" >= %s AND "OccurredAt" < %s',
            (site_id, window_start, window_end),
        )
        return cur.fetchone()[0]


def get_recent_alarms(conn, site_id: str, limit: int = 100) -> list[dict]:
    """The most recent `limit` events."Alert" rows for this site, newest
    first by LastOccurred -- ground truth for Alarm History's live table
    (docs/OF-148.txt: "Live table: last 100 alarms for the site, no
    date filter"). Severity is an int (confirmed live against BOLIVIA:
    1=WARNING, 3=MAJOR, 5=CRITICAL); Status 0=Open (-> "WO Open")."""
    with conn.cursor() as cur:
        cur.execute(
            'SELECT "Alarm", "Subsystem", "Signal", "Severity", "Status", '
            '"DeviceName", "Source", "Cause", "Message", "LastOccurred", "Count" '
            'FROM events."Alert" WHERE "SiteId" = %s '
            'ORDER BY "LastOccurred" DESC LIMIT %s',
            (site_id, limit),
        )
        columns = ["alarm", "subsystem", "signal", "severity", "status",
                   "device_name", "source", "cause", "message", "last_occurred", "count"]
        return [dict(zip(columns, row)) for row in cur.fetchall()]


def max_open_alarm_severity_for_subsystem(conn, site_id: str, subsystem: str) -> int | None:
    """The worst (highest) Severity among currently OPEN (Status=0) events.
    "Alert" rows for one subsystem on this site -- ground truth for
    confirming a Device Status Panel card's status pill correctly rolls up
    to its worst real alarm (1=WARNING, 3=MAJOR, 5=CRITICAL). None means no
    open alarms for that subsystem right now."""
    with conn.cursor() as cur:
        cur.execute(
            'SELECT max("Severity") FROM events."Alert" '
            'WHERE "SiteId" = %s AND "Subsystem" = %s AND "Status" = 0',
            (site_id, subsystem),
        )
        result = cur.fetchone()[0]
        return int(result) if result is not None else None


def count_alarms_in_window(conn, site_id: str, window_start, window_end) -> int:
    """How many events."Alert" rows exist for this site with LastOccurred in
    [window_start, window_end) -- ground truth for Alarm History's "Browse
    history" modal query limits (docs/OF-148.txt: 24h<=1000, 7d<=2000,
    30d<=5000) and its truncation warning (CA-26)."""
    with conn.cursor() as cur:
        cur.execute(
            'SELECT count(*) FROM events."Alert" '
            'WHERE "SiteId" = %s AND "LastOccurred" >= %s AND "LastOccurred" < %s',
            (site_id, window_start, window_end),
        )
        return cur.fetchone()[0]


def get_all_site_ids(conn) -> list[str]:
    """Every site id in the DB, across every team/manufacturer -- for the
    Fleet Status Summary alarm cards (Critical Alarms, Sites Requiring
    Attention, Sites with Alarms), which are confirmed FLEET-WIDE, not
    scoped to BOLIVIA (see FLEET_OVERVIEW_FRACTAL_COMPATIBILITY.md
    §1.2/§1.5/§1.6). Using only BOLIVIA's ids here undercounts as soon as
    another team's site has its own alarms -- confirmed 2026-09-02 when a
    colleague's site (KIRUNA) came online with real alerts."""
    with conn.cursor() as cur:
        cur.execute('SELECT "Id" FROM "sites"."Site"')
        return [str(row[0]) for row in cur.fetchall()]


def _window_overlap_clause() -> str:
    """The real backend's inclusion rule for a time-windowed alarm query,
    per docs/OF-298.txt (Technical annex, FleetAlarmKpiStore): "the alert
    overlaps: FirstOccurred <= end and LastOccurred >= start". end = now(),
    start = now() - hours. An alert opened before the window and never
    closed (OmniOps alerts never auto-close -- see docs/HOW_IT_WORKS.md
    §4) still counts as long as its LastOccurred (last time the condition
    was observed) falls inside the window; once telemetry for that alert
    stops arriving, LastOccurred freezes and it ages out of the window on
    its own, with no explicit close needed."""
    return '"FirstOccurred" <= now() AND "LastOccurred" >= now() - (%s || \' hours\')::interval'


def count_critical_alarms_windowed(conn, site_ids: list[str], hours: int = 24) -> int:
    """Windowed equivalent of count_critical_alarms, matching what
    GET /api/Events/analytics/fleet-alarm-kpis actually computes for the
    "Critical Alarms" KPI card (docs/OF-298.txt) -- unlike the flat,
    all-time count_critical_alarms, this only counts alerts whose window
    overlaps [now()-hours, now()]. Use this one for UI comparisons; the
    flat version undercounts what the UI shows whenever there ARE alerts
    outside the window, and will never explain a UI value LOWER than the
    flat DB count for the opposite reason -- a window can only shrink a
    count, never grow it (see fleet_overview_new_bug_critical_causes memory
    for why that asymmetry matters when triaging a mismatch)."""
    with conn.cursor() as cur:
        cur.execute(
            f'SELECT count(*) FROM "events"."Alert" '
            f'WHERE "SiteId" = ANY(%s::uuid[]) AND "Severity" = 5 AND {_window_overlap_clause()}',
            (site_ids, hours),
        )
        return cur.fetchone()[0]


def count_sites_with_alarms_windowed(conn, site_ids: list[str], hours: int = 24) -> int:
    """Windowed equivalent of count_sites_with_alarms, matching the "Sites
    with Alarms" KPI card's real windowed query (docs/OF-298.txt)."""
    with conn.cursor() as cur:
        cur.execute(
            f'SELECT count(DISTINCT "SiteId") FROM "events"."Alert" '
            f'WHERE "SiteId" = ANY(%s::uuid[]) AND {_window_overlap_clause()}',
            (site_ids, hours),
        )
        return cur.fetchone()[0]


def count_sites_requiring_attention_windowed(conn, site_ids: list[str], hours: int = 24) -> int:
    """Same underlying windowed query as count_sites_with_alarms_windowed --
    see count_sites_requiring_attention's docstring for why these two are
    kept as separate functions despite reading the same data today."""
    return count_sites_with_alarms_windowed(conn, site_ids, hours)


def top_critical_causes_windowed(conn, site_ids: list[str], hours: int = 24, limit: int = 5) -> dict[str, tuple[int, int]]:
    """Windowed equivalent of top_critical_causes, matching
    GET /api/events/analytics/critical-causes?hours= (docs/OF-344.txt,
    "Top 5 critical causes" panel). Same overlap window rule as the KPI
    cards -- both are Topbar-filter-driven per OF-298/OF-344, and this is
    the endpoint actually backing the panel our tests compare against."""
    with conn.cursor() as cur:
        cur.execute(
            f'''
            SELECT "Alarm", count(*), count(DISTINCT "SiteId")
            FROM "events"."Alert"
            WHERE "SiteId" = ANY(%s::uuid[]) AND "Severity" = 5 AND {_window_overlap_clause()}
            GROUP BY "Alarm"
            ORDER BY count(*) DESC
            LIMIT %s
            ''',
            (site_ids, hours, limit),
        )
        return {cause: (count, sites) for cause, count, sites in cur.fetchall()}


def count_alarms_by_subsystem_windowed(conn, site_ids: list[str], hours: int = 24) -> dict[str, int]:
    """Windowed equivalent of count_alarms_by_subsystem, matching
    GET /api/events/analytics/subsystem-distribution?hours= (docs/OF-344.txt)."""
    with conn.cursor() as cur:
        cur.execute(
            f'''
            SELECT "Subsystem", count(*) FROM "events"."Alert"
            WHERE "SiteId" = ANY(%s::uuid[]) AND {_window_overlap_clause()}
            GROUP BY "Subsystem"
            ''',
            (site_ids, hours),
        )
        return dict(cur.fetchall())


def top_sites_by_alarms_windowed(conn, site_ids: list[str], hours: int = 24) -> dict[str, tuple[int, int]]:
    """Windowed equivalent of top_sites_by_alarms, matching
    GET /api/events/analytics/top-sites?hours= (docs/OF-344.txt)."""
    with conn.cursor() as cur:
        cur.execute(
            f'''
            SELECT s."Name", count(*), count(*) FILTER (WHERE a."Severity" = 5)
            FROM "events"."Alert" a
            JOIN "sites"."Site" s ON s."Id" = a."SiteId"
            WHERE a."SiteId" = ANY(%s::uuid[]) AND {_window_overlap_clause().replace('"FirstOccurred"', 'a."FirstOccurred"').replace('"LastOccurred"', 'a."LastOccurred"')}
            GROUP BY s."Name"
            ''',
            (site_ids, hours),
        )
        return {name: (total, critical) for name, total, critical in cur.fetchall()}


def count_critical_alarms(conn, site_ids: list[str]) -> int:
    """Distinct open alerts with Severity=5 (Critical, per events.Alert data
    observed 2026-08-28) across the given sites. FLAT / ALL-TIME -- does NOT
    match what the UI shows, which is windowed by the Topbar's timeRange
    filter (see count_critical_alarms_windowed and docs/OF-298.txt). Kept
    for diagnostics (e.g. isolating whether a mismatch is a windowing gap
    vs. something else); use the _windowed version for UI comparisons."""
    with conn.cursor() as cur:
        cur.execute(
            'SELECT count(*) FROM "events"."Alert" '
            'WHERE "SiteId" = ANY(%s::uuid[]) AND "Severity" = 5',
            (site_ids,),
        )
        return cur.fetchone()[0]


def count_all_alarms(conn, site_ids: list[str]) -> int:
    """Every alert regardless of severity -- matches the map popup's
    "Active Alarms" field and the Alarms Analytics "Total Alarms" column
    (both confirmed 2026-08-31 to be the ALL-severity count, not just
    Critical -- e.g. BOLIVIA showed Active Alarms=11 / Critical=9)."""
    with conn.cursor() as cur:
        cur.execute(
            'SELECT count(*) FROM "events"."Alert" WHERE "SiteId" = ANY(%s::uuid[])',
            (site_ids,),
        )
        return cur.fetchone()[0]


def count_sites_with_alarms(conn, site_ids: list[str]) -> int:
    """How many distinct sites (of the given list) have at least one alert."""
    with conn.cursor() as cur:
        cur.execute(
            'SELECT count(DISTINCT "SiteId") FROM "events"."Alert" '
            'WHERE "SiteId" = ANY(%s::uuid[])',
            (site_ids,),
        )
        return cur.fetchone()[0]


def count_sites_requiring_attention(conn, site_ids: list[str]) -> int:
    """Same underlying data as count_sites_with_alarms -- kept as a separate
    function since the two Fleet Status Summary cards read the same alert
    table today, but may diverge in scope later (see
    FLEET_OVERVIEW_FRACTAL_COMPATIBILITY.md §1.2 vs §1.6)."""
    return count_sites_with_alarms(conn, site_ids)


def count_alarms_by_subsystem(conn, site_ids: list[str]) -> dict[str, int]:
    """{subsystem: count} across the given sites, ALL severities -- matches
    GET /api/events/analytics/subsystem-distribution's shape (confirmed
    2026-08-31: it includes non-Critical subsystems too, e.g. EMS_GATEWAY
    with only Severity=1 alerts still shows up with a nonzero count)."""
    with conn.cursor() as cur:
        cur.execute(
            'SELECT "Subsystem", count(*) FROM "events"."Alert" '
            'WHERE "SiteId" = ANY(%s::uuid[]) GROUP BY "Subsystem"',
            (site_ids,),
        )
        return dict(cur.fetchall())


def top_sites_by_alarms(conn, site_ids: list[str]) -> dict[str, tuple[int, int]]:
    """{site_name: (total_alarms, critical)} across the given sites -- same
    shape as FleetAlarmsAnalytics.top_sites_by_alarms() on the UI side, so
    the two dicts can be compared directly."""
    with conn.cursor() as cur:
        cur.execute(
            '''
            SELECT s."Name", count(*), count(*) FILTER (WHERE a."Severity" = 5)
            FROM "events"."Alert" a
            JOIN "sites"."Site" s ON s."Id" = a."SiteId"
            WHERE a."SiteId" = ANY(%s::uuid[])
            GROUP BY s."Name"
            ''',
            (site_ids,),
        )
        return {name: (total, critical) for name, total, critical in cur.fetchall()}


def top_critical_causes(conn, site_ids: list[str], limit: int = 5) -> dict[str, tuple[int, int]]:
    """{cause: (count, distinct_sites)} for Severity=5 alerts, top N by
    count -- same shape as FleetAlarmsAnalytics.top_critical_causes()."""
    with conn.cursor() as cur:
        cur.execute(
            '''
            SELECT "Alarm", count(*), count(DISTINCT "SiteId")
            FROM "events"."Alert"
            WHERE "SiteId" = ANY(%s::uuid[]) AND "Severity" = 5
            GROUP BY "Alarm"
            ORDER BY count(*) DESC
            LIMIT %s
            ''',
            (site_ids, limit),
        )
        return {cause: (count, sites) for cause, count, sites in cur.fetchall()}


def _fleet_availability_ticks(conn, days: int) -> tuple[int, int, int, int] | None:
    """(normal, warning, critical, total) tick sums for the fleet-wide
    availability window -- FLEET-WIDE, not per-site (see docs/fleet-
    availability.md §2): days=1 sums the last 24h of raw 5-min ticks from
    sites.FleetAvailabilitySample; days=7/30 sums that many COMPLETE days
    from sites.FleetAvailabilityDailySummary (the daily rollup), matching
    exactly which table each window reads server-side. None if no rows."""
    with conn.cursor() as cur:
        if days == 1:
            cur.execute(
                '''
                SELECT coalesce(sum(normal_sites), 0), coalesce(sum(warning_sites), 0),
                       coalesce(sum(critical_sites), 0), coalesce(sum(total_sites), 0)
                FROM "sites"."FleetAvailabilitySample"
                WHERE timestamp > now() - interval '24 hours'
                '''
            )
        else:
            cur.execute(
                '''
                SELECT coalesce(sum(normal_site_ticks), 0), coalesce(sum(warning_site_ticks), 0),
                       coalesce(sum(critical_site_ticks), 0), coalesce(sum(total_site_ticks), 0)
                FROM "sites"."FleetAvailabilityDailySummary"
                WHERE day >= current_date - %s AND day < current_date
                ''',
                (days,),
            )
        normal, warning, critical, total = cur.fetchone()
        return None if total == 0 else (normal, warning, critical, total)


def fleet_availability_card_pct(conn, days: int = 1) -> float | None:
    """Replicates FleetAvailabilityService.GetFleetAvailabilityHistoryAsync's
    exact formula (docs/fleet-availability.md §4.1): Math.Round(normal /
    total * 100, 2) -- plain rounding, NO mask-guard. This is the "Fleet
    Availability" KPI CARD's value, not the bar's (see
    fleet_availability_bar_pcts for that -- they use different rounding
    and can legitimately differ by ~0.1-0.2%, per the doc's own worked
    example). None if there's no data for the window yet."""
    ticks = _fleet_availability_ticks(conn, days)
    if ticks is None:
        return None
    normal, _, _, total = ticks
    return round(normal / total * 100, 2)


def fleet_availability_bar_pcts(conn, days: int = 1) -> tuple[float, float, float] | None:
    """Replicates FleetStatePercentages.Calculate exactly
    (docs/fleet-availability.md §4.2.1): round each to 1 decimal, mask-
    guard (a nonzero raw count never displays as 0.0%), then reconcile any
    rounding drift against whichever of the three is currently largest so
    the three always sum to exactly 100.0. Returns (normal, warning,
    critical) or None if there's no data for the window yet."""
    ticks = _fleet_availability_ticks(conn, days)
    if ticks is None:
        return None
    normal, warning, critical, total = ticks

    normal_pct = round(normal / total * 100, 1)
    warning_pct = round(warning / total * 100, 1)
    critical_pct = round(critical / total * 100, 1)

    if normal_pct == 0 and normal > 0:
        normal_pct = 0.1
    if warning_pct == 0 and warning > 0:
        warning_pct = 0.1
    if critical_pct == 0 and critical > 0:
        critical_pct = 0.1

    drift = round(100 - (normal_pct + warning_pct + critical_pct), 1)
    if drift != 0:
        if normal_pct >= warning_pct and normal_pct >= critical_pct:
            normal_pct = round(normal_pct + drift, 1)
        elif warning_pct >= critical_pct:
            warning_pct = round(warning_pct + drift, 1)
        else:
            critical_pct = round(critical_pct + drift, 1)

    return (normal_pct, warning_pct, critical_pct)


def get_pcs_power_kw(conn, site_id: str) -> float | None:
    """Sum of PcsPower across the site's TRANSFORMER_PCS devices, from the
    most recent RawBaseData row per MacId (mirrors the UI's aggregation --
    see FLEET_OVERVIEW_FRACTAL_COMPATIBILITY.md §2.6/§3.5). None if no rows.

    NOT CURRENTLY USABLE FOR FRACTAL SITES: confirmed 2026-08-28 that
    RawBaseData is EPC-shaped and stays empty for BOLIVIA even with the
    simulator running -- Fractal's live power isn't persisted anywhere
    queryable (RawBaseData, monitoring.TelemetryReading, and
    dataprocessing.ProcessedBessData.Power_kW are all empty). Kept here in
    case it's ever useful for an EPC site, or if Fractal telemetry starts
    getting persisted -- see
    tests/ui/fleet_overview/test_fleet_overview_sites_list_values.py for
    the range-check fallback actually in use today."""
    with conn.cursor() as cur:
        cur.execute(
            '''
            SELECT sum(latest."PcsPower")
            FROM (
                SELECT DISTINCT ON ("MacId") "PcsPower"
                FROM "emscommunication"."RawBaseData"
                WHERE "SiteId" = %s::uuid
                ORDER BY "MacId", "Timestamp" DESC
            ) latest
            ''',
            (site_id,),
        )
        row = cur.fetchone()
        return float(row[0]) if row and row[0] is not None else None


def get_current_weather(conn, site_id: str) -> dict | None:
    """The site's real, live external weather reading (weather.WeatherData,
    IsCurrent=True) -- populated by the backend's own WeatherService/
    AzureMapsWeatherClient integration (real per-site lat/lon calls to
    Azure Maps, refreshed hourly). This is the genuine "external feed"
    ground truth for Environmental Monitoring's Ambient Temp/Humidity
    (API) fallback -- used to confirm whether that fallback actually
    reflects this real live weather data, or a disconnected static
    default (see tests/ui/monitoring/test_environmental_monitoring.py).
    None if the site has no current weather row yet."""
    with conn.cursor() as cur:
        cur.execute(
            '''
            SELECT "Temperature", "Humidity", "Timestamp"
            FROM "weather"."WeatherData"
            WHERE "SiteId" = %s::uuid AND "IsCurrent" = true
            ''',
            (site_id,),
        )
        row = cur.fetchone()
        if row is None:
            return None
        temperature, humidity, timestamp = row
        return {
            "temperature_c": float(temperature) if temperature is not None else None,
            "humidity_pct": float(humidity) if humidity is not None else None,
            "timestamp": timestamp,
        }
