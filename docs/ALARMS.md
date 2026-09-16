# Alarm validation — new module

Extends the framework to **alarms**, with the same differential-oracle
pattern used for PCS power: we compare the **cause in the raw data**
(simulator) against the **alarm in the OmniOps API**, and give a verdict.

```
  cause in the RAW DATA        alarm in the API
  (alarms_oracle.py)   vs     (alarms_api.py)
            \____________  _____________/
                    verdict.py  ->  PASS / PASS_HEALTHY /
                                    FAIL_FALSE_ALARM / FAIL_NOT_DETECTED /
                                    NOT_VERIFIABLE
```

## Pieces (all with `--self-check`, tested without network)

| File | Role | Depends on the catalog |
|---|---|---|
| `verdict.py` | The judge: 4 cases + not verifiable. Pure logic. | No |
| `alarms_api.py` | Reads `GET /api/events/alarms/filtered?Status=Open` and normalizes. | No |
| `alarms_oracle.py` | Cause oracle: reads the raw data (Evt1 bit / threshold). | Only the numbers |
| `watch_alarms.py` | Live monitor: baseline (today) or full (with catalog). | Full mode |
| `alarms_catalog.example.py` | Catalog template. Copy to `alarms_catalog.py`. | — |

The **engine is complete and tested**. All that's missing for full mode is
the **data** (which register/bit/limit triggers each alarm), which goes in
`alarms_catalog.py`, translated from **SPEC90 / MAPA_DE_BITS.md**.

## How to run

**Today, without a catalog or an injection hook** (baseline + passive
correlation):

```bash
python watch_alarms.py
```

With a healthy simulator there shouldn't be any open alarms; if one appears,
it's flagged as a possible **FALSE ALARM**. Leaves a report in `reportes/`.

**First, pin down the field names of the alarms API** (we don't know them
yet). With OmniOps running:

```bash
python alarms_api.py --dump
```

Send me that output and I'll adjust the candidates flagged `ADJUST` in
`alarms_api.py` (and the matching `code`). It's 2-3 lines.

**Full mode** (once `alarms_catalog.py` exists with real data):

```bash
python watch_alarms.py            # detects the catalog on its own
python watch_alarms.py --baseline # force baseline even if a catalog exists
```

## What's left to close this out

1. **Real field names** from the alarms API → `alarms_api.py --dump`.
2. **`alarms_catalog.py`** with the registers/bits/limits from SPEC90 /
   MAPA_DE_BITS.md (use `alarms_catalog.example.py` as a template).
3. **`--inject-file` hook** in the simulator (`inject.py`) to actively
   trigger causes and see FAIL_NOT_DETECTED / real detection. The baseline
   and passive correlation already run without this.
