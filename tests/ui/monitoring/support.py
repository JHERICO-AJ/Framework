"""Shared helpers/constants of the Monitoring UI tests (so no test module imports from another test module)."""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

from shared.utils.parsing import parse_first_number


SITE_NAME = "BOLIVIA"


# CA-04: the 3 global time ranges, and the exact badge/period text and
# tooltip label shape each one produces on this chart (confirmed live
# 2026-09-10). 24h's point is a complete HOUR ("HH:MM:SS" tooltip label);
# 7d/30d's point is a complete DAY ("<weekday>, D <month> YYYY" label,
# Spanish locale) -- Jira story OF-143: "sin la hora/el dia en curso" (the
# still-forming current hour/day is excluded), which is exactly why this
# needs its OWN UTC window resolved from that label, not "now" rounded down.
TIME_RANGES = ["Last 24 hours", "Last 7 days", "Last 30 days"]


EXPECTED_BADGE_BY_RANGE = {"Last 24 hours": "24H", "Last 7 days": "7D", "Last 30 days": "30D"}


EXPECTED_PERIOD_BY_RANGE = {
    "Last 24 hours": "Last 24 hours.", "Last 7 days": "Last 7 days.", "Last 30 days": "Last 30 days.",
}


TOL_ABS_MW = 0.2


def utc_window_for_tooltip_label(page, label):
    """The exact [window_start, window_end) UTC boundary a tooltip's first
    line refers to -- an "HH:MM:SS" label (24h) resolves to that complete
    HOUR; a 7d/30d date label resolves to that complete DAY. Both are
    rendered in the BROWSER's local timezone (confirmed 2026-09-10:
    "19:00:00" local in America/La_Paz, UTC-4, matched the DB's 23:00 UTC
    bucket exactly), so this reads the browser's own timezone offset via
    JS rather than assuming a fixed one -- correct regardless of what
    machine/timezone this suite runs on.

    The 7d/30d date label's own FORMAT isn't stable across deploys: it
    used to render "<weekday>, D <month> YYYY" in Spanish (e.g. "jue, 17
    sep 2026") and, confirmed live 2026-09-21 after the JF/FixMonitoring
    locale fix (the internal QA note 'MnitoringFix' section 9), now renders US English
    "<weekday>, Month D, YYYY" (e.g. "Thu, Sep 17, 2026"). This matters
    for more than cosmetics: this function's own date regex previously
    only recognized the Spanish shape, so under the new format it raised
    an AssertionError -- which, inside an xfail-marked test, was silently
    swallowed and reported as an ordinary 'XFAIL', masking the fact that
    the REAL numeric comparison never even ran. Both shapes are accepted
    here so a future locale change can't hide a genuine regression behind
    a parser crash again."""
    offset_min = page.evaluate("() => new Date().getTimezoneOffset()")

    time_match = re.match(r"^(\d{1,2}):(\d{2}):(\d{2})$", label)
    if time_match:
        hour, minute, second = (int(g) for g in time_match.groups())
        today_local = page.evaluate(
            "() => { const d = new Date(); return d.getFullYear() + '-' + "
            "String(d.getMonth() + 1).padStart(2, '0') + '-' + String(d.getDate()).padStart(2, '0'); }")
        naive_local = datetime.strptime(today_local, "%Y-%m-%d").replace(hour=hour, minute=minute, second=second)
        window_start = (naive_local + timedelta(minutes=offset_min)).replace(
            minute=0, second=0, microsecond=0, tzinfo=timezone.utc)
        return window_start, window_start + timedelta(hours=1)

    # Spanish shape: "jue, 17 sep 2026" (day before month)
    date_match = re.match(r"^\w+,\s*(\d{1,2})\s+(\w+)\.?\s+(\d{4})$", label)
    if date_match:
        day, month_abbr, year = date_match.groups()
    else:
        # English shape: "Thu, Sep 17, 2026" (month before day)
        date_match = re.match(r"^\w+,\s*(\w+)\.?\s+(\d{1,2}),\s*(\d{4})$", label)
        assert date_match, f"unrecognized tooltip time/date label: {label!r}"
        month_abbr, day, year = date_match.groups()
    month = _MONTH_ABBR.get(month_abbr.lower().rstrip("."))
    assert month, f"unrecognized month abbreviation in {label!r}: {month_abbr!r}"
    # NOTE (2026-09-13, fixed): unlike the HH:MM:SS/24h branch above, this
    # date does NOT need a local-offset shift. the internal QA note 'GraficasMonitoring':
    # 7d/30d aggregate by "Dias UTC completos" (complete UTC calendar
    # days), with the point's own backend timestamp = dayStart + 12h UTC
    # (noon) -- so formatting that noon-UTC instant in a browser several
    # hours behind/ahead of UTC still lands on the SAME calendar date in
    # the vast majority of timezones (only a same-day-crossing offset
    # near +/-12h could disagree). Confirmed live: applying the offset
    # shift here (treating the parsed Y/M/D as a LOCAL midnight) produced
    # a systematically wrong window and a false Charge/Discharge Power
    # mismatch; using the parsed date directly as a UTC calendar day
    # matched the real API exactly (2049.75 kW).
    window_start = datetime(int(year), month, int(day), tzinfo=timezone.utc)
    return window_start, window_start + timedelta(days=1)


def soc_range_value(panel):
    """Battery/BMS's "SoC range" line renders as e.g. "SoC range:
    49.1-49.1%" (min-max, equal when there's no per-rack detail -- BOLIVIA
    is Fractal, no racks) -- parse_first_number reads the first (min)
    figure, sufficient since min==max here."""
    info_lines = panel.info_lines("Battery / BMS")
    soc_line = next((line for line in info_lines if line.startswith("SoC range")), None)
    assert soc_line is not None, f"no 'SoC range' line found in: {info_lines}"
    value = parse_first_number(soc_line)
    assert value is not None, f"couldn't parse a percentage from: {soc_line!r}"
    return value
