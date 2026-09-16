# Context for Claude Code — Fleet Overview automation (OmniOps, Fractal)

> Paste this file into the `fleet-overview` branch (e.g. `docs/FLEET_OVERVIEW_CONTEXT.md`)
> and point Claude Code at it. It explains WHAT to build, HOW it must fit the existing
> framework, and the CONSTRAINTS. Read it fully before writing code.

---

## 1. Goal

Automate the **Fleet Overview** page tests for **Fractal** sites in OmniOps.
There are ~44 manual test cases in Qase (exported CSV). We want them as automated
UI tests that produce a green/red HTML report, following the existing framework's
conventions — NOT a new framework.

This is **different** from the alarm/power automation already in the repo:
- Alarms/power = *differential oracle* (inject in the Modbus simulator, compare vs API/UI).
- Fleet Overview = mostly **UI verification of fleet KPIs** whose values come from the
  **database** (Sites, Events, WorkOrders) and backend calculations, not from the simulator.

So Fleet Overview needs: new **Page Objects** under `framework_ui/pages/fleet_overview/`,
new **tests** under `tests/`, and a **deterministic dataset** so "exact value" checks
are reproducible.

---

## 2. Follow the existing architecture (do NOT invent a new one)

The repo uses a 5-layer structure. Reuse it:

- `framework_ui/browser/browser_factory.py` — reuse as-is to open the browser.
- `framework_ui/base/base_page.py` — new pages extend `BasePage` (waits by DOM, not networkidle).
- `framework_ui/pages/auth/login_page.py` — reuse to log in (selectors: `#loginUser`,
  `#loginPassword`, `button.login-submit-button`; wait until URL leaves `/login`).
- **NEW:** `framework_ui/pages/fleet_overview/` — the Page Objects for this page, with
  **locators next to each page** (`*_locators.py`), and reusable pieces under `components/`.
- Config in `shared/config/settings.py` (add `FLEET_OVERVIEW_PATH`, DB connection if needed).
- Tests under `tests/` with the existing pytest fixtures (`logged_in_page`, etc.).
- The assertion lives IN the test. Page Objects only read the screen.

**Rule of thumb:** a UI selector → `*_locators.py`; a screen reader/action → `*_page.py`;
a check (assert) → `tests/`. Never put selectors or asserts in the wrong layer.

---

## 3. The page has 5 sections (from the Fractal compatibility doc)

Build one Page Object area per section. Each Qase case maps to a section.

1. **Fleet Status Summary** (`FleetStatusGrid.tsx`) — KPI cards: Connected Sites,
   Sites Requiring Attention, Open WO, Online Rate, Critical Alarms, Sites with Alarms,
   MTTR, Fleet Availability; plus chips (Total Sites, Reporting Sites, Update Time).
2. **Fleet Map** (`FleetMap.tsx`) — markers by status, tooltips, popups (Status, Last Seen,
   SOC, Power, Active Alarms).
3. **Sites List** (`SitesList.tsx`) — table: Site, Status, Critical, SoC, Power, Last Seen…
4. **Fleet Alarms Analytics** (`FleetAlarmsAnalytics.tsx`) — time series, distribution by
   system, top sites, top 5 critical causes.
5. **Fleet Availability** bar — Normal/Warning/Critical segments + percentage.

---

## 4. CRITICAL — what applies to Fractal and what does NOT

Fractal sends **EMU + Meter + PCS**, but **NO battery BMS racks**. This changes many
expected values. From the compatibility doc:

| Component | Fractal | Expected in a healthy sim |
|-----------|---------|---------------------------|
| Connected Sites / Online Rate / Reporting Sites | ✅ works | real online count |
| Fleet Availability (Normal/Critical) | ✅ works | needs ~5 min of history |
| Power (map popup, list) | ✅ works | Σ pcs[].p_ac_kw (PCS as TransformerPcs) |
| Markers / Last Seen / Update Time | ✅ works | online, recent |
| SOC (map popup, list SoC bar) | ❌ NO | Fractal has no BMS racks → shows `-%` / empty |
| Open WO | ❌ not wired | always `—` / Not available |
| MTTR | ❌ no WOs | `0.0 h` / Response 0 min |
| Sites Requiring Attention / Critical Alarms / Sites with Alarms | ⚠️ | **0** in a healthy sim (no alarms) |
| Analytics (series, pie, top sites, top causes) | ⚠️ | **empty** in a healthy sim |

**Implication for automation:**
- ✅ items → assert real values.
- ❌ items → assert the empty/`-`/`—` placeholder (that IS the correct behavior for Fractal).
- ⚠️ items → **0 / empty is the expected result in a healthy sim.** To get non-zero values
  you must GENERATE alarms deliberately (see §6).

Do NOT write a test that expects SOC or Open WO to have a value on Fractal — that would
be a wrong test. The `-`/`—` placeholder is the pass condition there.

**Warning gotcha (case 13):** on the map, **Warning status is BLUE**, not yellow. Don't
assume the usual color.

---

## 5. Deterministic dataset (5 sites) — the foundation

"Exact value" cases are only automatable if the DB is in a known, reproducible state.
Use a fixed set of **5 Fractal sites** (see `DATASET_FLEET_OVERVIEW.md`). Summary:

- 5 sites registered via Data Intake import (the BOLIVIA xlsx), all `manufacturer =
  fractal_knapp`, all with lat/lng (so they appear on the map).
- Site #1 is the **anchor**: always present, healthy, used as the stable reference.
- The others are put into known states (online healthy, one with a critical alarm, one
  offline by stopping its telemetry) so KPI counts are predictable.
- Expected values are derived FROM this dataset (e.g. Connected Sites = 4/5 if one is
  offline; Critical Alarms = 1 if exactly one critical was injected).

**Reset procedure** (before each run, for repeatability):
1. Run the cleanup SQL (`Script-1.sql`) — it truncates telemetry, events, alerts, work
   orders. **It does NOT delete Sites** (by design — the 5 sites stay).
2. Re-establish the known state: start the 5 Fractal sims (healthy), and inject the
   specific alarms the scenario needs.
3. Wait for the availability history to accumulate (~5 min) for availability cases.

This "fixed sites + clean transactional data" gives a predictable baseline.

---

## 6. How to generate Fractal alarms (for the ⚠️ cases)

Fractal alarms are **bit-based** (unlike EPC which is telemetry-threshold). Two intake
mechanisms exist (both configured in Data Intake UI, no SQL):
- **Bitfield Registers** (Catalog = Fractal): map a word+bit (e.g. `AlarmWord27` bit N)
  to an OmniOps alarm rule. When telemetry arrives with that bit Set, the alarm opens.
- **Alarm Thresholds** (Family = Fractal): value-based alarms (temp, V, A, PF).

To make "Critical Alarms = 1" reproducible, the scenario must: configure the bit→rule
mapping once, then have the sim send that bit Set on exactly one site. The framework's
injection mechanism (proxy) will need a Fractal-aware path — see the open questions.

References in the repo docs: `fractal-bitfield-intake-guide.md`,
`alarm-thresholds-intake-guide.md`, `fractal-alarms-coverage-open-by-id.md`.

---

## 7. Suggested build order (incremental, each step runnable)

1. **Scaffolding:** `framework_ui/pages/fleet_overview/` + a `FleetOverviewPage` that
   opens the page and confirms it loaded. One smoke test.
2. **Group A — stable/structural cases first** (fast wins, no exact DB values needed):
   - Column headers render in exact order (#18)
   - Time-badge type: Current for 4 cards, range for 4 cards (#11)
   - Marker colors match status, Warning=BLUE (#13)
   - Clicking outside the map modal closes it (#14)
   - "No active alarms" + "0 Critical" badge when a site is online (#26)
   - Default hyphen `-` in empty/null fields (#2) — perfect for the Fractal ❌ items.
3. **Group B — exact values (need the dataset):** Connected Sites value (#3),
   Online Rate (#6), Reporting Sites (#43), Total Sites (#1), Update Time (#44),
   histogram/distribution/top causes (#28–#42) — only after §5 dataset is fixed.
4. **Group C — Fractal N/A cases:** assert the placeholder (Open WO `—`, MTTR 0,
   SOC `-%`). Low value but quick; confirm they show the empty state.

Each test: `@pytest.mark.ui` (or a new `fleet` marker), uses `logged_in_page`, reads via
the Page Object, asserts in the test. Generate the HTML report with
`pytest --html=reports/report.html --self-contained-html`.

---

## 8. Open questions to resolve with the team (don't guess)

1. **Exact expected values:** confirm the dataset numbers (how many sites online, how
   many alarms) so the "exact" cases have a defined expected result.
2. **Fractal alarm injection:** is there a proxy path to set Fractal bits, like the EPC
   telemetry injection? If not, generating the ⚠️ non-zero cases needs a plan.
3. **DB access from tests:** some checks may need to read the DB (Sites, Events). Is there
   a read-only connection the tests can use? (DBeaver is manual; tests need a driver.)
4. **Availability timing:** availability cases need ~5 min of history — decide if they run
   in a separate "slow" suite.
5. **Deploy target:** confirm the URL the tests point at (the deploy link), and that it
   uses email/password login (not Microsoft SSO, which can't be automated).

---

## 9. What NOT to do

- Don't build a new framework or new folder structure — extend the existing one.
- Don't expect values for Fractal ❌ items (SOC, Open WO) — assert the placeholder.
- Don't write "exact value" tests before the dataset is fixed — they'll be flaky.
- Don't automate login via Microsoft SSO — use email/password from `.env`.
- Don't put selectors in tests or asserts in Page Objects.
