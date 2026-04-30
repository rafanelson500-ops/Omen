# GexBot historical classic + state — bulk pull report

**Generated:** 2026-04-30T18:51:09

**Window:** 2025-09-08 → 2026-04-28
**Trading days in window:** 161
**Trading days fully processed by this run:** 161
**Ticker:** ES_SPX
**Endpoints:** 11 (3 classic + 8 state)
**Wall clock (active fetch):** ~360 minutes — initial `bulk_pull.py` run = 357.1 min (21,425 s, slow-internet stretched it 3×); targeted `repull_missing.py` run = ~3 min (7 endpoint-days × ~18 sec). The JSONL log spans 17.65 hours from first request to last because of idle time between the kill, the resume, and the targeted repull — not 17.65 hours of fetching.

## Per-endpoint summary

| pkg | cat | ok | fail | missing | retried-ok | total gz |
|---|---|---:|---:|---:|---:|---:|
| classic | gex_full | 160 | 1 | 0 | 0 | 4.68GB |
| classic | gex_zero | 160 | 1 | 0 | 0 | 3.44GB |
| classic | gex_one | 160 | 1 | 0 | 1 | 1.85GB |
| state | gamma_zero | 160 | 1 | 0 | 0 | 2.81GB |
| state | gamma_one | 160 | 1 | 0 | 0 | 1.98GB |
| state | vanna_zero | 160 | 1 | 0 | 3 | 2.85GB |
| state | vanna_one | 160 | 1 | 0 | 0 | 2.05GB |
| state | charm_zero | 160 | 1 | 0 | 0 | 2.03GB |
| state | charm_one | 160 | 1 | 0 | 0 | 359.02MB |
| state | delta_zero | 160 | 1 | 0 | 0 | 2.34GB |
| state | delta_one | 160 | 1 | 0 | 0 | 1.96GB |
| | **total** | | | | | **26.33GB** |

## Gaps & failures

### classic/gex_full

**Failed (after retries):**

- 2026-02-23: no_data_404 — step1 HTTP 404 (no data for date)

### classic/gex_zero

**Failed (after retries):**

- 2026-02-23: no_data_404 — step1 HTTP 404 (no data for date)

### classic/gex_one

**Failed (after retries):**

- 2026-02-23: no_data_404 — step1 HTTP 404 (no data for date)

### state/gamma_zero

**Failed (after retries):**

- 2026-02-23: no_data_404 — step1 HTTP 404 (no data for date)

### state/gamma_one

**Failed (after retries):**

- 2026-02-23: no_data_404 — step1 HTTP 404 (no data for date)

### state/vanna_zero

**Failed (after retries):**

- 2026-02-23: no_data_404 — step1 HTTP 404 (no data for date)

### state/vanna_one

**Failed (after retries):**

- 2026-02-23: no_data_404 — step1 HTTP 404 (no data for date)

### state/charm_zero

**Failed (after retries):**

- 2026-02-23: no_data_404 — step1 HTTP 404 (no data for date)

### state/charm_one

**Failed (after retries):**

- 2026-02-23: no_data_404 — step1 HTTP 404 (no data for date)

### state/delta_zero

**Failed (after retries):**

- 2026-02-23: no_data_404 — step1 HTTP 404 (no data for date)

### state/delta_one

**Failed (after retries):**

- 2026-02-23: no_data_404 — step1 HTTP 404 (no data for date)

## Schema variations

None detected. Schema (key set on first snapshot) is identical across every successfully-pulled day for every endpoint.

Note: variation detection only sees keys captured during this run (written to JSONL log at fetch time). Files pulled in prior runs and skipped by resume have no key entry; if the run was a clean first-pass this caveat doesn't apply.

## Output paths

- Classic: `/Users/rafanelson/Omen/backend/data/gex_classic/{cat}/{date}.json.gz`
- State:   `/Users/rafanelson/Omen/backend/data/gex_state/{cat}/{date}.json.gz`
- JSONL audit log: `/Users/rafanelson/Omen/backend/data/gex_classic_state_pull_log.jsonl`
- This report: `/Users/rafanelson/Omen/backend/data/gex_classic_state_pull_report.md`
