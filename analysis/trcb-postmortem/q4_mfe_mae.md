# Q4 — MFE/MAE path analysis on TRCB-v1 triggers

Branch: `analysis/trcb-v1-postmortem-throwaway` (throwaway / archive only).
Generated: 2026-05-12 22:36 UTC

Scope: 27 triggered bars from `phase2_population_results.csv` (15 long, 12 short). 
For each trigger, the 25-minute forward price path is reconstructed at 1-second 
resolution from `ES_c_0_ohlcv1s_2025-09-08_2026-04-27.parquet`. Signed returns are 
in ES points (×$50/pt per contract); `long` => price − entry, `short` => entry − price.

Entry reference: ES 1s close at T (the bar_close timestamp of the triggering 5-min bar). 
This is a diagnostic anchor; it does not assert anything about realistic fills.

RTH boundary handling: 1 trigger (2025-12-01 15:40 SHORT) overflows 16:00 ET by 
5 minutes; its window is truncated at 16:00 ET so `final_return` is taken at the 
session close. All other 26 triggers fit within RTH.

## 1) Summary statistics

### ALL TRIGGERS (n=27)
```
  MFE                    mean=+7.56  median=+4.50  std=7.14  min=+1.25  max=+34.50  (pts)
  MAE                    mean=-8.16  median=-5.25  std=12.09  min=-63.25  max=-0.25  (pts)
  time_to_MFE            mean=+579.67  median=+438.00  std=505.21  min=+17.00  max=+1481.00  (seconds)
  time_to_MFE pct of win: mean=38.6%  median=29.2%
  time_to_MAE            mean=+739.26  median=+832.00  std=492.90  min=+1.00  max=+1471.00  (seconds)
  time_to_MAE pct of win: mean=49.3%  median=55.5%
  final_return           mean=-0.93  median=+1.00  std=11.85  min=-51.75  max=+14.00  (pts)
  MFE/|MAE| ratio        mean=+12.36  median=+1.00  std=22.95  min=+0.05  max=+74.00  ((dimensionless))
```

### LONG TRIGGERS ONLY (n=15)
```
  MFE                    mean=+5.83  median=+4.25  std=4.06  min=+1.50  max=+13.25  (pts)
  MAE                    mean=-6.18  median=-5.00  std=5.31  min=-20.50  max=-0.25  (pts)
  time_to_MFE            mean=+725.33  median=+805.00  std=533.89  min=+17.00  max=+1481.00  (seconds)
  time_to_MFE pct of win: mean=48.4%  median=53.7%
  time_to_MAE            mean=+724.93  median=+811.00  std=511.77  min=+1.00  max=+1471.00  (seconds)
  time_to_MAE pct of win: mean=48.3%  median=54.1%
  final_return           mean=+1.53  median=+2.50  std=5.70  min=-9.75  max=+10.25  (pts)
  MFE/|MAE| ratio        mean=+8.78  median=+1.00  std=17.03  min=+0.09  max=+53.00  ((dimensionless))
```

### SHORT TRIGGERS ONLY (n=12)
```
  MFE                    mean=+9.73  median=+5.62  std=9.25  min=+1.25  max=+34.50  (pts)
  MAE                    mean=-10.62  median=-5.75  std=16.81  min=-63.25  max=-0.25  (pts)
  time_to_MFE            mean=+397.58  median=+205.00  std=397.87  min=+42.00  max=+1185.00  (seconds)
  time_to_MFE pct of win: mean=26.5%  median=13.7%
  time_to_MAE            mean=+757.17  median=+914.50  std=467.62  min=+1.00  max=+1346.00  (seconds)
  time_to_MAE pct of win: mean=50.5%  median=61.0%
  final_return           mean=-4.00  median=-0.88  std=16.08  min=-51.75  max=+14.00  (pts)
  MFE/|MAE| ratio        mean=+16.84  median=+1.05  std=28.05  min=+0.05  max=+74.00  ((dimensionless))
```

## 2) Path-shape classification

Classification rules (applied in order; first match wins):
- **RUN_UP_THEN_FADE**: MFE ≥ 1.0 pts AND time_to_MFE < 12.5min AND final_return < 0.5·MFE
- **SLOW_BLEED**:        MFE < 1.0 pts AND final_return < -1.0 pts
- **CLEAN_WINNER**:      final_return > 1.0 pts AND |MAE| < 0.5·final_return
- **CHOPPY**:            MFE > 1.0 AND |MAE| > 1.0 AND |final_return| < 0.5
- **OTHER**:             everything else

#### ALL TRIGGERS (n=27)
| class | count | pct |
|---|---|---|
| RUN_UP_THEN_FADE | 14 | 51.9% |
| SLOW_BLEED | 0 | 0.0% |
| CLEAN_WINNER | 7 | 25.9% |
| CHOPPY | 0 | 0.0% |
| OTHER | 6 | 22.2% |

#### LONG TRIGGERS ONLY (n=15)
| class | count | pct |
|---|---|---|
| RUN_UP_THEN_FADE | 5 | 33.3% |
| SLOW_BLEED | 0 | 0.0% |
| CLEAN_WINNER | 4 | 26.7% |
| CHOPPY | 0 | 0.0% |
| OTHER | 6 | 40.0% |

#### SHORT TRIGGERS ONLY (n=12)
| class | count | pct |
|---|---|---|
| RUN_UP_THEN_FADE | 9 | 75.0% |
| SLOW_BLEED | 0 | 0.0% |
| CLEAN_WINNER | 3 | 25.0% |
| CHOPPY | 0 | 0.0% |
| OTHER | 0 | 0.0% |

## 3) time_to_MFE distribution (5-minute buckets)

#### ALL TRIGGERS (n=27)
| bucket | count | pct |
|---|---|---|
| 0-5 min | 12 | 44.4% |
| 5-10 min | 3 | 11.1% |
| 10-15 min | 3 | 11.1% |
| 15-20 min | 4 | 14.8% |
| 20-25 min | 5 | 18.5% |
| >25 min | 0 | 0.0% |

#### LONG TRIGGERS ONLY (n=15)
| bucket | count | pct |
|---|---|---|
| 0-5 min | 5 | 33.3% |
| 5-10 min | 1 | 6.7% |
| 10-15 min | 2 | 13.3% |
| 15-20 min | 2 | 13.3% |
| 20-25 min | 5 | 33.3% |
| >25 min | 0 | 0.0% |

#### SHORT TRIGGERS ONLY (n=12)
| bucket | count | pct |
|---|---|---|
| 0-5 min | 7 | 58.3% |
| 5-10 min | 2 | 16.7% |
| 10-15 min | 1 | 8.3% |
| 15-20 min | 2 | 16.7% |
| 20-25 min | 0 | 0.0% |
| >25 min | 0 | 0.0% |

## 4) Per-trigger detail (sorted by MFE descending)

| bar_close_et | dir | entry | MFE | MAE | t→MFE | t→MAE | final | class | notes |
|---|---|---|---|---|---|---|---|---|---|
| 2026-04-23 13:40 | short | 7114.25 | +34.50 | -21.50 | 412s | 1316s | -14.75 | RUN_UP_THEN_FADE |  |
| 2025-12-31 14:15 | short | 6931.75 | +18.50 | -0.25 | 1185s | 1s | +14.00 | CLEAN_WINNER |  |
| 2025-12-01 15:40 | short | 6835.75 | +16.25 | -0.25 | 1042s | 256s | +7.25 | CLEAN_WINNER | RTH-truncated +300s |
| 2025-12-31 14:20 | short | 6927.25 | +14.00 | -0.25 | 885s | 1s | +9.75 | CLEAN_WINNER |  |
| 2025-09-25 10:10 | long  | 6659.25 | +13.25 | -2.25 | 920s | 21s | +8.75 | CLEAN_WINNER |  |
| 2025-12-05 12:50 | long  | 6874.50 | +13.25 | -0.25 | 1195s | 1s | +9.50 | CLEAN_WINNER |  |
| 2026-01-06 12:05 | long  | 6961.50 | +12.25 | -0.25 | 1255s | 3s | +10.25 | CLEAN_WINNER |  |
| 2025-12-17 13:00 | long  | 6749.75 | +10.50 | -8.25 | 438s | 1215s | -3.00 | RUN_UP_THEN_FADE |  |
| 2025-10-30 13:05 | short | 6892.25 | +7.75 | -7.75 | 480s | 1346s | -5.00 | RUN_UP_THEN_FADE |  |
| 2026-04-20 12:15 | short | 7136.00 | +5.75 | -5.25 | 139s | 1165s | +0.50 | RUN_UP_THEN_FADE |  |
| 2026-04-21 11:50 | short | 7129.25 | +5.50 | -7.25 | 271s | 690s | +1.00 | RUN_UP_THEN_FADE |  |
| 2025-10-10 10:25 | long  | 6792.75 | +5.00 | -5.00 | 127s | 1035s | +4.00 | OTHER |  |
| 2025-11-24 14:40 | long  | 6718.75 | +4.75 | -8.75 | 1481s | 811s | +4.50 | OTHER |  |
| 2025-10-14 13:25 | long  | 6716.00 | +4.50 | -7.75 | 1383s | 666s | +2.75 | OTHER |  |
| 2026-03-24 11:25 | long  | 6639.25 | +4.25 | -10.50 | 58s | 515s | +2.50 | OTHER |  |
| 2025-10-29 12:20 | long  | 6936.75 | +4.00 | -0.25 | 805s | 1s | +3.00 | CLEAN_WINNER |  |
| 2026-04-27 10:30 | short | 7189.25 | +3.75 | -8.75 | 132s | 361s | -1.50 | RUN_UP_THEN_FADE |  |
| 2026-01-02 15:10 | long  | 6902.50 | +3.50 | -4.00 | 667s | 1471s | -3.00 | RUN_UP_THEN_FADE |  |
| 2026-02-10 12:35 | short | 6992.50 | +3.50 | -6.25 | 60s | 857s | -3.00 | RUN_UP_THEN_FADE |  |
| 2025-09-11 13:40 | long  | 6589.75 | +3.25 | -3.25 | 1201s | 688s | +2.00 | OTHER |  |
| 2025-10-27 10:55 | long  | 6883.50 | +3.25 | -2.00 | 1207s | 832s | +2.50 | OTHER |  |
| 2025-12-26 12:50 | short | 6975.00 | +3.00 | -2.25 | 66s | 972s | -0.25 | RUN_UP_THEN_FADE |  |
| 2026-03-19 14:50 | short | 6577.00 | +3.00 | -63.25 | 57s | 1026s | -51.75 | RUN_UP_THEN_FADE |  |
| 2025-12-31 14:40 | long  | 6917.75 | +2.50 | -11.50 | 58s | 1334s | -9.75 | RUN_UP_THEN_FADE |  |
| 2025-10-21 12:50 | long  | 6788.00 | +1.75 | -20.50 | 17s | 835s | -7.50 | RUN_UP_THEN_FADE |  |
| 2025-12-29 15:35 | long  | 6959.00 | +1.50 | -8.25 | 68s | 1446s | -3.50 | RUN_UP_THEN_FADE |  |
| 2025-12-23 12:50 | short | 6950.75 | +1.25 | -4.50 | 42s | 1095s | -4.25 | RUN_UP_THEN_FADE |  |

## 5) Interpretation

### (a) Is there meaningful run-up masked by 25-min endpoint?

Mean MFE = **+7.56 pts**, median = **+4.50 pts**. 
Mean final_return = **-0.93 pts**, median = **+1.00 pts**. 
Mean giveback (MFE − final) = **+8.49 pts**.

Yes — average run-up exceeds 2 points and is substantially larger than the 
realized 25-min final return. The signed-endpoint metric understates the 
intra-window price excursion in the favorable direction.

### (b) Run-up vs giveback pattern — is the filter identifying real short-term moves?

Median |MAE| = **5.25 pts**, vs median MFE = **+4.50 pts**. 
Median MFE/|MAE| ratio = **1.00**.

MFE and |MAE| are of similar magnitude at the median (ratio ≈ 1). This is the 
signature of approximately symmetric intra-window movement: the trigger is 
firing on bars where price subsequently moves *both* directions of comparable 
size. Combined with the modal RUN_UP_THEN_FADE shape (sec. d), this is consistent 
with the signal catching short-lived directional impulses that fully mean-revert 
within the 25-min window — not symmetric *noise* in the strict sense, but not a 
clean directional edge either.

### (c) When does the optimal exit time appear to be?

- 44% of triggers reach MFE in the first 6:15 (0–25% of the window)
- 59% of triggers reach MFE in the first 12:30 (0–50% of the window)
- Median time-to-MFE = **438s** (7.3 min)
- Mean giveback (MFE − final, from sec. a) = **+8.49 pts**

A plurality (44%) of triggers peak in the first 5 minutes, and the 
mean giveback of +8.49 pts is large relative to the -0.93 pt mean 
final return. The 25-minute horizon is structurally too long for this signal's 
favorable excursion — the optimal exit, on a path-shape basis, sits well before the 
window end. (Note: this comment is about the 25-min path geometry only; OMEN's 
actual deployed exit is ATR-based stop/target with a 25-min time stop, not a 
fixed 25-min hold.)

### (d) Path-shape distribution

- **RUN_UP_THEN_FADE**: 14 / 27
- **SLOW_BLEED**: 0 / 27
- **CLEAN_WINNER**: 7 / 27
- **CHOPPY**: 0 / 27
- **OTHER**: 6 / 27

RUN_UP_THEN_FADE is the modal shape — the signal IS catching real short-term 
moves, but exit timing (25-min hold) misses the peak.

### (e) Honest caveats

- **n=27 is small.** Long-only n=15 and short-only n=12 are very small — split 
  stats should be read as suggestive, not definitive.
- Path-shape categories are reported as **counts**, not just percentages. With 
  27 triggers, a 1-trigger change moves a category by ~3.7 percentage points.
- One trigger (2025-12-01 15:40 SHORT) was RTH-truncated; its window is 20 minutes 
  instead of 25. Truncation is conservative for path-shape attribution.
- Entry-price reference is `ES 1s close at T`. Real OMEN fills happen at next-bar 
  open per `backtest.py:197`; this analysis is about the 5-min-signal path, not 
  about a tradable strategy.
- Findings inform future-project planning only. No deployment changes, no new 
  filter tests on the 160-session corpus authorized by this analysis.
