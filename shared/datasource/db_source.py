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


def count_critical_alarms(conn, site_ids: list[str]) -> int:
    """Distinct open alerts with Severity=5 (Critical, per events.Alert data
    observed 2026-08-28) across the given sites."""
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
