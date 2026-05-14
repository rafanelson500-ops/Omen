# Step 0.5 — VIX data verification

Branch: `analysis/vol-regime-conditioning-throwaway` (throwaway / never merges).
Generated: 2026-05-14T12:47:09

## Disclosure

```
This analysis is exploratory diagnostic work on a consumed corpus
during an active forward test. It is NOT pre-registered. Results
CANNOT authorize any modification to locked OMEN config or pre-reg.

The OMEN trade outcomes on this 146-session corpus have been examined
many times across TRCB-v1, TRCB-v2 Q1-Q9 post-mortems, microprice
continuation, cell exclusion analysis, churn analysis (Steps 5/7),
and other diagnostics. The corpus is heavily consumed and the
project-wide false discovery rate is high.

Any positive finding here can only be honestly evaluated on a future
pre-registered forward window. This diagnostic adds candidate
filters to the post-verdict pre-reg bookmarks, nothing more.

```

## Reference

- All-bugfixes IS+OOS trade log: **504 trades, 146 sessions** (2025-09-08 → 2026-04-21).

## 1. vix_daily.csv

- path: `/Users/rafanelson/Omen/backend/data/analysis/vix_daily.csv`
- rows: 80
- columns: `['date', 'vix_close', '_date']`

Dtypes:

```
  date                  str
  vix_close             float64
  _date                 object
```

First 5 rows:

```
      date  vix_close      _date
2025-12-26      13.60 2025-12-26
2025-12-29      14.20 2025-12-29
2025-12-30      14.33 2025-12-30
2025-12-31      14.95 2025-12-31
2026-01-02      14.51 2026-01-02
```

Inferred date column: **`date`**.
- VIX coverage of trade-sessions: **74 / 146**
- VIX file range: **2025-12-26 → 2026-04-22**
- Trade-sessions missing from vix_daily: **72**
  - first 10: ['2025-09-08', '2025-09-09', '2025-09-10', '2025-09-11', '2025-09-12', '2025-09-15', '2025-09-16', '2025-09-17', '2025-09-18', '2025-09-22']

## 2. trades_with_vix.csv

- path: `/Users/rafanelson/Omen/backend/data/analysis/trades_with_vix.csv`
- rows: 174
- columns: `['_orig_idx', 'strategy', 'side', 'contracts', 'entry_time', 'entry_px', 'exit_time', 'exit_px', 'exit_reason', 'bars_held', 'stop_px', 'target_px', 'atr_at_entry', 'gamma_regime', 'gross_points', 'gross_dollars', 'cost_dollars', 'net_dollars', 'hour_min', 'entry_date', 'vix_close', 'vix_date']`

First 5 rows:

```
 _orig_idx   strategy  side  contracts                entry_time  entry_px                 exit_time  exit_px exit_reason  bars_held  stop_px  target_px  atr_at_entry gamma_regime  gross_points  gross_dollars  cost_dollars  net_dollars  hour_min entry_date  vix_close   vix_date
         0 flow_burst     1          1 2025-12-30 12:35:00-05:00  6951.375 2025-12-30 13:05:00-05:00 6949.875        time          6  6945.50    6964.50      2.910714        short         -1.50          -75.0          17.5        -80.0       755 2025-12-30       14.2 2025-12-29
         1 flow_burst    -1          1 2025-12-30 13:05:00-05:00  6949.875 2025-12-30 13:35:00-05:00 6953.375        time          6  6955.50    6937.25      2.785714         long         -3.50         -175.0          17.5       -180.0       785 2025-12-30       14.2 2025-12-29
         2 flow_burst    -1          1 2025-12-30 13:40:00-05:00  6950.875 2025-12-30 14:10:00-05:00 6951.125        time          6  6956.00    6939.50      2.535714         long         -0.25          -12.5          17.5        -17.5       820 2025-12-30       14.2 2025-12-29
         3 flow_burst     1          1 2025-12-30 14:15:00-05:00  6953.875 2025-12-30 14:45:00-05:00 6952.625        time          6  6949.00    6965.25      2.500000        short         -1.25          -62.5          17.5        -67.5       855 2025-12-30       14.2 2025-12-29
         4 flow_burst     1          1 2025-12-30 15:00:00-05:00  6949.875 2025-12-30 15:10:00-05:00 6945.125        stop          2  6945.25    6960.50      2.375000        short         -4.75         -237.5          17.5       -242.5       900 2025-12-30       14.2 2025-12-29
```

Inferred join columns: `entry_time` = `entry_time`, `side` = `side`.

**Key-match against all-bugfixes ref (entry_time, side)**:
- matches    : 153
- only in TWV: 21
- only in ref: 351

## 3. Verdict

**`trades_with_vix.csv` is FILTERED or partial** (174 rows; 153 match the 504-trade reference). **Per spec, DO NOT use it as a shortcut.** Step 2 will perform a fresh join from `vix_daily.csv` to the full 504-trade log on session date.

## 4. Stop gate

Per spec, **STOP HERE**. Step 1 (ATR) runs only after you confirm this verification.

