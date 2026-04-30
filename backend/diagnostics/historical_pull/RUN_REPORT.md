# GexBot historical classic + state — bulk pull report

**Generated:** 2026-04-30T17:53:43

**Window:** 2025-09-08 → 2026-04-28
**Trading days in window:** 161
**Trading days fully processed by this run:** 161
**Ticker:** ES_SPX
**Endpoints:** 11 (3 classic + 8 state)
**Wall clock:** 357.1 minutes (21425 s)

## Per-endpoint summary

| pkg | cat | ok | fail | missing | retried-ok | total gz |
|---|---|---:|---:|---:|---:|---:|
| classic | gex_full | 159 | 2 | 0 | 0 | 4.65GB |
| classic | gex_zero | 159 | 2 | 0 | 0 | 3.41GB |
| classic | gex_one | 159 | 2 | 0 | 1 | 1.84GB |
| state | gamma_zero | 159 | 2 | 0 | 0 | 2.79GB |
| state | gamma_one | 159 | 2 | 0 | 0 | 1.96GB |
| state | vanna_zero | 160 | 1 | 0 | 3 | 2.85GB |
| state | vanna_one | 159 | 2 | 0 | 0 | 2.04GB |
| state | charm_zero | 160 | 1 | 0 | 0 | 2.03GB |
| state | charm_one | 160 | 1 | 0 | 0 | 359.02MB |
| state | delta_zero | 159 | 2 | 0 | 0 | 2.32GB |
| state | delta_one | 160 | 1 | 0 | 0 | 1.96GB |
| | **total** | | | | | **26.20GB** |

## Gaps & failures

### classic/gex_full

**Failed (after retries):**

- 2026-02-23: no_data_404 — step1 HTTP 404 (no data for date)
- 2026-03-25: retries_exhausted — transient ConnectionError: ConnectionError(MaxRetryError('HTTPSConnectionPool(host=\'api.gex.bot\', port=443): Max retries exceeded with url: /v2/hist/ES_SPX/classic/gex_full/2026-03-25?noredirect (Caused by NameResolutionError("HTTPSConnection(host=\'api.gex.bot\', port=443): Failed to resolve \'api.gex.bot\' ([Errno 8] nodename nor servname provided, or not known)"))'))

### classic/gex_zero

**Failed (after retries):**

- 2026-02-23: no_data_404 — step1 HTTP 404 (no data for date)
- 2026-03-25: retries_exhausted — transient ConnectionError: ConnectionError(MaxRetryError('HTTPSConnectionPool(host=\'api.gex.bot\', port=443): Max retries exceeded with url: /v2/hist/ES_SPX/classic/gex_zero/2026-03-25?noredirect (Caused by NameResolutionError("HTTPSConnection(host=\'api.gex.bot\', port=443): Failed to resolve \'api.gex.bot\' ([Errno 8] nodename nor servname provided, or not known)"))'))

### classic/gex_one

**Failed (after retries):**

- 2026-02-23: no_data_404 — step1 HTTP 404 (no data for date)
- 2026-03-25: retries_exhausted — transient ConnectionError: ConnectionError(MaxRetryError('HTTPSConnectionPool(host=\'api.gex.bot\', port=443): Max retries exceeded with url: /v2/hist/ES_SPX/classic/gex_one/2026-03-25?noredirect (Caused by NameResolutionError("HTTPSConnection(host=\'api.gex.bot\', port=443): Failed to resolve \'api.gex.bot\' ([Errno 8] nodename nor servname provided, or not known)"))'))

### state/gamma_zero

**Failed (after retries):**

- 2026-02-23: no_data_404 — step1 HTTP 404 (no data for date)
- 2026-03-25: retries_exhausted — transient ConnectionError: ConnectionError(MaxRetryError('HTTPSConnectionPool(host=\'api.gex.bot\', port=443): Max retries exceeded with url: /v2/hist/ES_SPX/state/gamma_zero/2026-03-25?noredirect (Caused by NameResolutionError("HTTPSConnection(host=\'api.gex.bot\', port=443): Failed to resolve \'api.gex.bot\' ([Errno 8] nodename nor servname provided, or not known)"))'))

### state/gamma_one

**Failed (after retries):**

- 2026-02-23: no_data_404 — step1 HTTP 404 (no data for date)
- 2026-03-25: retries_exhausted — transient ConnectionError: ConnectionError(MaxRetryError('HTTPSConnectionPool(host=\'api.gex.bot\', port=443): Max retries exceeded with url: /v2/hist/ES_SPX/state/gamma_one/2026-03-25?noredirect (Caused by NameResolutionError("HTTPSConnection(host=\'api.gex.bot\', port=443): Failed to resolve \'api.gex.bot\' ([Errno 8] nodename nor servname provided, or not known)"))'))

### state/vanna_zero

**Failed (after retries):**

- 2026-02-23: no_data_404 — step1 HTTP 404 (no data for date)

### state/vanna_one

**Failed (after retries):**

- 2026-02-23: no_data_404 — step1 HTTP 404 (no data for date)
- 2026-03-24: retries_exhausted — transient ConnectionError: ConnectionError(MaxRetryError('HTTPSConnectionPool(host=\'api.gex.bot\', port=443): Max retries exceeded with url: /v2/hist/ES_SPX/state/vanna_one/2026-03-24?noredirect (Caused by NameResolutionError("HTTPSConnection(host=\'api.gex.bot\', port=443): Failed to resolve \'api.gex.bot\' ([Errno 8] nodename nor servname provided, or not known)"))'))

### state/charm_zero

**Failed (after retries):**

- 2026-02-23: no_data_404 — step1 HTTP 404 (no data for date)

### state/charm_one

**Failed (after retries):**

- 2026-02-23: no_data_404 — step1 HTTP 404 (no data for date)

### state/delta_zero

**Failed (after retries):**

- 2026-02-23: no_data_404 — step1 HTTP 404 (no data for date)
- 2026-03-24: retries_exhausted — transient ConnectionError: ConnectionError(MaxRetryError('HTTPSConnectionPool(host=\'api.gex.bot\', port=443): Max retries exceeded with url: /v2/hist/ES_SPX/state/delta_zero/2026-03-24?noredirect (Caused by NameResolutionError("HTTPSConnection(host=\'api.gex.bot\', port=443): Failed to resolve \'api.gex.bot\' ([Errno 8] nodename nor servname provided, or not known)"))'))

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
