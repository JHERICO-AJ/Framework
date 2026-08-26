# Deterministic dataset — Fleet Overview (5 Fractal sites)

Purpose: a **known, reproducible** state so "exact value" KPI cases are automatable.
Without this, values like "Connected Sites = 4/5" or "Critical Alarms = 1" can't be
verified — they'd change every run.

Principle: **fixed sites + clean transactional data.** The 5 sites are created once and
stay (the cleanup SQL does not delete Sites). Before each run we clean telemetry/events
and re-establish the scenario, so the baseline is always the same.

---

## The 5 sites

All `manufacturer = fractal_knapp`, all with lat/lng (so they render on the map),
registered via Data Intake import (BOLIVIA xlsx). Site 1 is the permanent anchor.

| # | Site (suggested)   | Role in tests                    | Intended state per run        |
|---|--------------------|----------------------------------|-------------------------------|
| 1 | FRACTAL-ANCHOR-01  | Anchor / stable reference        | **Online, healthy** (no alarms) |
| 2 | FRACTAL-SITE-02    | Second healthy site              | **Online, healthy**           |
| 3 | FRACTAL-SITE-03    | Site with ONE critical alarm     | **Online, 1 Critical alarm**  |
| 4 | FRACTAL-SITE-04    | Site with a warning alarm        | **Online, 1 Warning alarm**   |
| 5 | FRACTAL-SITE-05    | Offline site (telemetry stopped) | **Offline** (no telemetry >120s) |

> Adjust names to your convention. Keep the ROLES — they're what makes the KPIs predictable.

---

## Expected KPI values for this scenario (the "source of truth" for exact-value cases)

Derived directly from the table above. These become the asserts.

| KPI / element | Expected | Why |
|---------------|----------|-----|
| Total Sites | **5** | 5 sites in DB |
| Connected / Reporting Sites | **4 / 5** | site 5 is offline (>120s) |
| Online Rate | **80.0%** | 4 of 5 online |
| Sites Requiring Attention | **2** | sites 3 and 4 have alarms |
| Critical Alarms | **1** | only site 3 has a Critical |
| Sites with Alarms | **2** (1 Critical / 1 Warning) | sites 3 (crit) + 4 (warn) |
| Open WO | **—** / Not available | not wired for Fractal |
| MTTR | **0.0 h** | no work orders |
| Map markers | 4 online-ish + 1 offline; site 3 = critical (red), site 4 = **warning BLUE** | status logic |
| SOC (map popup / list bar) | **-%** / empty on all | Fractal has no BMS racks |
| Power (popup / list) | Σ of each site's PCS `p_ac_kw` | PCS registered as TransformerPcs |
| Fleet Availability | ~**80%** Normal after history accrues | 4/5 online, low warning |

> If you change how many sites are offline or alarmed, update this table — it IS the
> expected-values reference the tests assert against.

---

## Reset procedure (run before each test session)

1. **Clean transactional data** with the cleanup SQL (Script-1.sql): truncates
   RawBaseData, ProcessedBessData, trend snapshots, MonitoringStat, FleetKPI, SiteKPI,
   weather, **Alert + Event**, WorkOrder. Sites are preserved.
2. **Confirm the 5 sites still exist** (they should — not truncated). If a site is
   missing, re-import it via Data Intake.
3. **Configure the Fractal alarm mappings once** (Bitfield Registers, Catalog = Fractal):
   the word+bit → rule for the Critical (site 3) and the Warning (site 4). This survives
   cleanup (it's config, not events).
4. **Start telemetry:**
   - Sites 1, 2: healthy Fractal sim.
   - Site 3: Fractal sim sending the Critical bit Set.
   - Site 4: Fractal sim sending the Warning bit Set.
   - Site 5: **do not start** (or stop it) so it reads offline after 120s.
5. **Wait**: ~2 min for online/offline to settle; ~5 min if availability-history cases
   are in scope.

---

## What this enables per case group

- **Structural cases** (headers, badges, placeholders): pass regardless of exact data.
- **Exact-count cases** (Connected 4/5, Critical 1, etc.): pass because the scenario is
  fixed and the expected table above defines the numbers.
- **Fractal N/A cases** (SOC, Open WO, MTTR): pass by asserting the placeholder.
- **Availability cases**: run after the ~5 min history window.

---

## Open items to confirm before locking this in

- Exact site names / GUIDs used in the BOLIVIA import.
- Whether the offline site (5) can be reliably kept offline in the test environment.
- The precise Fractal word+bit to use for the Critical and Warning alarms (from
  `fractal-alarms-coverage-open-by-id.md`).
- Whether Power expected values can be pinned (the sim's p_ac_kw may vary per tick — if
  so, assert a range or "present and > 0" rather than an exact number).
