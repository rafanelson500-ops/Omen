# Step 3 — skew consistency filter (SKIPPED, bookmark only)

Branch: `analysis/vol-regime-conditioning-throwaway` (throwaway).
Generated: 2026-05-14T12:55:24

## Disclosure

```
This analysis is exploratory diagnostic work on a heavily consumed
corpus during an active forward test. It is NOT pre-registered.
Results CANNOT authorize any modification to locked OMEN config
or pre-reg.

The 504-trade all-bugfixes corpus has been examined many times
across multiple diagnostics. Project-wide false discovery rate is
high. Any positive finding here can only be honestly evaluated on
a future pre-registered forward window after OMEN-minus-SL verdict.

```

## Bookmark for post-verdict pre-reg

```
SKEW CONSISTENCY FILTER — POST-VERDICT PRE-REG CANDIDATE

Status: OPRA data on disk is 2-day slice only (Apr 22-23, 2026).
Insufficient for 146-session analysis. Test skipped.

Requires for future implementation:
  - Databento OPRA subscription (~$199/mo), OR
  - VIX term structure proxy (VIX vs VIX3M ratio, free)

Proposed spec for post-verdict pre-reg:
  For each OMEN signal, measure 25-delta skew direction over the
  30 minutes leading up to entry. Take trade only if skew direction
  is consistent with GEX z-sign:
    - GEX z > 0 (long signal):  put-skew falling OR call-skew rising
    - GEX z < 0 (short signal): put-skew rising OR call-skew falling

Bookmark for evaluation after OMEN-minus-SL forward verdict.

```

