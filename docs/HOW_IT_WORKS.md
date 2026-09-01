# How the framework works (in depth)

This document explains the **why** behind the design decisions. The README
explains how to *use* the framework; this one explains how and why it
*works*. It is the recommended reading to understand the framework before
touching it.

---

## 1. The core idea: differential oracle

We don't ask OmniOps whether it's correct — that would mean trusting the same
system we want to verify. Instead, we read the **raw** data from the
simulator ourselves (Modbus, independent of OmniOps) and compare it against
what OmniOps produces.

```
                        ┌─────────────► OmniOps API (what it CALCULATES)
   simulator (Modbus)   │
   [raw data] ──────────┼─────────────► OmniOps UI (what it DISPLAYS)
        │               │
        └──► our oracle (what it SHOULD give)  ──► we compare
```

- **Oracle** = our independent account of "what should happen" (reading the raw data).
- **API / UI** = what OmniOps actually produces.
- If they match, OmniOps is correct. If not, we found a bug — and we know in
  which layer (calculation vs. display), because we verify them separately.

The simulator **only exposes raw telemetry** (temperatures, voltages, bits).
It never says "alarm." Alarms are OmniOps's own invention, derived from
evaluating that telemetry. That's why the system under test is always
OmniOps, never the simulator.

---

## 2. The Modbus proxy: how we inject conditions

To test an alarm we need to trigger its cause (e.g. high temperature). We
can't and don't want to modify the simulator. The solution is a **proxy**
that sits in the middle of the Modbus wire.

```
  BEFORE:  edge ──────────────► simulator (5020)
  NOW:     edge ──► proxy (5020) ──► real simulator (5021)
```

- The real simulator runs on **5021**.
- The proxy listens on **5020** (where the edge expects to find the simulator).
- The edge asks the proxy for data, believing it's the simulator.
- The proxy asks the real simulator for the data, **modifies it if there's an
  active injection**, and returns it to the edge.

So when we inject "rack temperature = extremely high," the proxy replaces
that register on every read. The edge reads the modified value, sends it to
OmniOps, and OmniOps generates the alarm. The simulator never knew; we
modified the data **in transit**.

The injection state lives in `inject_state.json`: which registers to
turn on/off (bits) or set (values). The proxy reads it **fresh on every
read**, so injecting/clearing takes effect immediately with no restart
needed.

Full flow of an alarm test:

```
you inject → proxy modifies the register → edge reads it (every 5s) →
Event Hub → OmniOps evaluates → creates the alarm → the API shows it → we verify
```

---

## 3. Key finding: OmniOps evaluates by TELEMETRY, not by bits

The Modbus protocol has, on one hand, **event bits** (Evt1) that say "this
fault is active," and on the other, **telemetry values** (temperature,
current, etc.) in Model 803/103.

We discovered, by testing it, that **OmniOps does NOT look at the event
bits**: it looks at the **telemetry values** and applies its own thresholds.
If you inject the "Rack High Temp" bit, our oracle says "cause present" but
OmniOps creates nothing. If you inject a **temperature above the threshold**,
OmniOps does create the alarm.

That's why telemetry-alarm injection **forces an extreme value** into the
corresponding register (very high temperature, very high current), not a
bit. The map of which register corresponds to each alarm is in
`shared/domain/telemetry_map.py`, extracted from the simulator's Model
803/103.

`real_value = raw × 10^scale_factor`. To inject "above the threshold" without
fighting the scale factor, we force an extreme raw value (very high or very
low, depending on the direction); the oracle performs the exact comparison
against the real threshold.

---

## 4. Finding: OmniOps does NOT close alarms

Once OmniOps opens an alarm, it leaves it open (it drags along dozens of old
alarms). This breaks the naive "does the alarm exist?" check, because it
always exists.

The solution: check by **`lastOccurred`** (the last time OmniOps saw the
condition), not by `firstOccurred` or by presence.

- When you inject, OmniOps **updates `lastOccurred`** to the current moment.
- A "fresh" alarm = its `lastOccurred` is close to the moment you injected.
- When you clear, `lastOccurred` **freezes** (stops updating) → this is how
  we know the condition ended, even though the alarm is still technically
  open.

That's why the verdicts (`shared/domain/verdict.py`) distinguish 4 cases:
`PASS` (cause + fresh alarm), `FAIL_FALSE_ALARM` (alarm without cause),
`FAIL_NOT_DETECTED` (cause without alarm), `PASS_HEALTHY` (neither cause nor
alarm).

---

## 5. Detail: timestamps come in UTC

The OmniOps API returns `firstOccurred` / `lastOccurred` in **UTC**, even
though the UI shows them in local time. The framework **compares in UTC**
(takes the injection moment in UTC) and **displays in local time** for
readability. That's why the "did it appear at the right time" check
(`time✓`) works in any timezone, with no magic numbers.

---

## 6. The timing check (scene mode)

`python -m tools.run_check 16 --at 10 --until 30 --live` does the following,
showing it live:

1. sec 0-10: before injecting → cause absent.
2. sec 10: injects → verifies that OmniOps creates it and that the timestamp
   ≈ sec 10.
3. sec 10-30: shows it refreshing (`lastOccurred` keeps rising).
4. sec 30: clears → verifies that the cause disappears from the raw data and
   that `lastOccurred` freezes.

It's the full timeline: not just "it appeared," but "it appeared when I
asked for it" and "it turned off when I asked for it" (in the correct way
for a system that doesn't close alarms).

---

## 7. Fleet Overview: a second verification style (read-only, no injection)

Everything above (§1-6) is the **alarm-injection oracle**: modify a register
in transit, wait for OmniOps to react, check the timing and the cause. Fleet
Overview (`tests/ui/fleet_overview/`) verifies a **different kind of
claim** — not "did OmniOps generate the right alarm for a condition I just
created," but "does OmniOps correctly calculate and display values it's
already computing from real, ongoing telemetry" (fleet-wide site counts,
per-site Power, alarm counts, availability percentages). There's nothing to
inject there — the proxy/injection mechanism doesn't apply.

The comparison is the same *differential* idea (read the ground truth
independently, compare against what OmniOps produces), just with 3 possible
"ground truths" instead of 1, picked per field based on where the real
source of truth actually lives:

- **The simulator directly** (`shared/datasource/fractal_modbus_source.py`,
  Modbus TCP, bypassing OmniOps entirely) — for Power, which OmniOps
  doesn't persist in any queryable table.
- **The database** (`shared/datasource/db_source.py`, via the `db_conn`
  fixture, read-only) — for anything OmniOps DOES persist (alarm counts,
  site identities, availability history) and that a UI-only check can't
  prove is *correct*, only that it's *consistent with itself*.
- **The API directly** (`framework_api/services/`) — as a third layer
  alongside the DB/simulator, to distinguish a backend calculation bug
  (API disagrees with the DB/simulator) from a UI rendering bug (API is
  right, the screen shows something else). See
  `test_fleet_overview_sites_list_values.py`'s 3-layer Power coverage for
  a worked example: simulator→API isolates the backend; API→UI isolates
  the screen.

A real-world case this design caught: comparing the simulator's *current*
tick straight against OmniOps' *current* displayed value looks broken
during any fast-moving period (e.g. right after the simulator restarts and
ramps up) — not because anything is wrong, but because a single
point-in-time comparison can't account for real ingestion latency (typically
1-20s, measured and reported by the tests, not assumed). The fix used
throughout this area is a **convergence window**: build a short rolling
history of simulator samples and check whether OmniOps' current value
matches ANY sample in that recent history, not just the newest one. The
non-asserting live monitor (`monitors/watch_fleet_power.py`) intentionally
does the naive instantaneous comparison instead — it's for demo/debug, not
a source of truth — which is why it can show more "FAIL" noise than the
actual pytest tests during a ramp.

---

## 8. Why the structure is separated this way

- **The API layer knows nothing about Modbus.** If an "API" file started
  injecting registers, it would be a sign that it's actually cross-layer.
  This lets us test the API alone, without the simulator.
- **The oracle (domain) doesn't talk to the system.** It calculates the
  expected value by reading the raw data; it's testable offline (that's why
  the `--self-check`s exist).
- **The assert lives in the test.** `domain` provides the expected data; the
  test compares and decides pass/fail.
- **Monitors observe, they don't assert.** A component's validation is its
  *test*; the monitor is a tool for watching live.
