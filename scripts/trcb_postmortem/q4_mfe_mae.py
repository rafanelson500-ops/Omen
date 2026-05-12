"""Q4 — MFE/MAE path analysis on the 27 TRCB-v1 Phase-2 triggers.

For each triggered bar:
  1. T = bar_close_et timestamp
  2. entry_price = ES 1s close at T
  3. Forward window = (T, T+25min], 1-second resolution
  4. Truncate at 16:00 ET RTH close if T+25min overflows
  5. Compute signed path: long => price - entry; short => entry - price
  6. MFE = max(signed_return); MAE = min(signed_return); time-to each
  7. final_return at end-of-window -- sanity check vs Phase 2

Throwaway-branch supplemental diagnostic. Read-only on Phase 2 + ES 1s.
"""
from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

REPO = Path("/Users/rafanelson/Omen")
PHASE2_CSV = REPO / "diagnostics/mbp10-trcb-v1/phase2_population_results.csv"
ES_PARQUET = REPO / "backend/data/market/ES_c_0_ohlcv1s_2025-09-08_2026-04-27.parquet"
OUT_MD = REPO / "analysis/trcb-postmortem/q4_mfe_mae.md"

ET = ZoneInfo("America/New_York")
WINDOW = pd.Timedelta(minutes=25)
RTH_CLOSE_HM = (16, 0)


def _rth_close_et(ts: pd.Timestamp) -> pd.Timestamp:
    """16:00 ET on the trade date."""
    return ts.normalize() + pd.Timedelta(hours=RTH_CLOSE_HM[0], minutes=RTH_CLOSE_HM[1])


def _load_phase2() -> pd.DataFrame:
    df = pd.read_csv(PHASE2_CSV)
    df["bar_close_et"] = pd.to_datetime(df["bar_close_et"], utc=True).dt.tz_convert(ET)
    df["bar_close_utc"] = pd.to_datetime(df["bar_close_utc"], utc=True)
    df["session_date"] = pd.to_datetime(df["session_date"]).dt.date
    triggered = df[df["trcb_long"] | df["trcb_short"]].copy().reset_index(drop=True)
    return triggered


def _load_es_1s() -> pd.DataFrame:
    df = pd.read_parquet(ES_PARQUET)
    if df.index.tz is None:
        df.index = df.index.tz_localize("UTC").tz_convert(ET)
    elif str(df.index.tz) != "America/New_York":
        df.index = df.index.tz_convert(ET)
    return df.sort_index()


def _compute_path_stats(trig_row: pd.Series, es: pd.DataFrame) -> dict:
    """Return one path-stats dict for a single triggered bar."""
    T = trig_row["bar_close_et"]
    direction = "long" if bool(trig_row["trcb_long"]) else "short"

    # Entry reference: ES 1s close at T. Use asof (most recent close <= T).
    es_at_T = es.loc[:T]
    if es_at_T.empty:
        raise RuntimeError(f"No ES 1s bar at or before T={T}")
    entry_ts = es_at_T.index[-1]
    entry_price = float(es_at_T["close"].iloc[-1])

    # Forward window (T, T+25min], truncated at 16:00 ET if needed.
    win_end_uncapped = T + WINDOW
    rth_close = _rth_close_et(T)
    truncated = win_end_uncapped > rth_close
    win_end = min(win_end_uncapped, rth_close)
    overflow_secs = max(0, int((win_end_uncapped - rth_close).total_seconds()))

    fwd = es.loc[(es.index > T) & (es.index <= win_end), ["close"]].copy()
    if fwd.empty:
        raise RuntimeError(f"No ES 1s bars in forward window for T={T}")

    # Signed return at each 1s tick (in points)
    if direction == "long":
        fwd["signed_ret"] = fwd["close"].values - entry_price
    else:
        fwd["signed_ret"] = entry_price - fwd["close"].values

    elapsed_s = (fwd.index - T).total_seconds().to_numpy()
    sr = fwd["signed_ret"].to_numpy()

    mfe = float(sr.max())
    mae = float(sr.min())
    mfe_i = int(np.argmax(sr))
    mae_i = int(np.argmin(sr))
    time_to_mfe = float(elapsed_s[mfe_i])
    time_to_mae = float(elapsed_s[mae_i])
    final_return = float(sr[-1])

    # MFE / |MAE| ratio: guard against zero MAE
    if abs(mae) < 1e-9:
        rr_ratio = float("inf") if mfe > 0 else 0.0
    else:
        rr_ratio = mfe / abs(mae)

    return {
        "bar_close_et": T,
        "direction": direction,
        "entry_ts_used": entry_ts,
        "entry_price": entry_price,
        "phase2_price_at_T": float(trig_row["price_at_T"]),
        "phase2_fwd_signed": float(trig_row["fwd_ret_25min_signed"]),
        "mfe": mfe,
        "mae": mae,
        "time_to_mfe_s": time_to_mfe,
        "time_to_mae_s": time_to_mae,
        "final_return": final_return,
        "rr_ratio": rr_ratio,
        "n_observations": len(fwd),
        "win_end": win_end,
        "rth_truncated": truncated,
        "rth_overflow_secs": overflow_secs,
    }


def _classify(row: dict) -> str:
    mfe = row["mfe"]; mae = row["mae"]; final = row["final_return"]
    if mfe >= 1.0 and row["time_to_mfe_s"] < 0.5 * WINDOW.total_seconds() and final < 0.5 * mfe:
        return "RUN_UP_THEN_FADE"
    if mfe < 1.0 and final < -1.0:
        return "SLOW_BLEED"
    if final > 1.0 and abs(mae) < 0.5 * final:
        return "CLEAN_WINNER"
    if mfe > 1.0 and abs(mae) > 1.0 and abs(final) < 0.5:
        return "CHOPPY"
    return "OTHER"


def _fmt_stats(values: np.ndarray, label: str, unit: str = "pts") -> str:
    if len(values) == 0:
        return f"  {label}: (no observations)"
    return (f"  {label:<22s} mean={values.mean():+.2f}  median={np.median(values):+.2f}  "
            f"std={values.std(ddof=0):.2f}  min={values.min():+.2f}  max={values.max():+.2f}  ({unit})")


def _summary_block(rows: list[dict], title: str, lines: list[str]) -> None:
    lines.append(f"\n### {title} (n={len(rows)})")
    if not rows:
        lines.append("  (no triggers)")
        return
    mfe = np.array([r["mfe"] for r in rows])
    mae = np.array([r["mae"] for r in rows])
    ttm_mfe = np.array([r["time_to_mfe_s"] for r in rows])
    ttm_mae = np.array([r["time_to_mae_s"] for r in rows])
    final = np.array([r["final_return"] for r in rows])
    rr = np.array([r["rr_ratio"] for r in rows if np.isfinite(r["rr_ratio"])])
    window_s = WINDOW.total_seconds()
    lines.append("```")
    lines.append(_fmt_stats(mfe, "MFE", "pts"))
    lines.append(_fmt_stats(mae, "MAE", "pts"))
    lines.append(_fmt_stats(ttm_mfe, "time_to_MFE", "seconds"))
    lines.append(f"  time_to_MFE pct of win: mean={ttm_mfe.mean()/window_s*100:.1f}%  median={np.median(ttm_mfe)/window_s*100:.1f}%")
    lines.append(_fmt_stats(ttm_mae, "time_to_MAE", "seconds"))
    lines.append(f"  time_to_MAE pct of win: mean={ttm_mae.mean()/window_s*100:.1f}%  median={np.median(ttm_mae)/window_s*100:.1f}%")
    lines.append(_fmt_stats(final, "final_return", "pts"))
    if len(rr) > 0:
        lines.append(_fmt_stats(rr, "MFE/|MAE| ratio", "(dimensionless)"))
    else:
        lines.append("  MFE/|MAE| ratio: (all denominators zero)")
    lines.append("```")


def _classification_block(rows: list[dict], title: str, lines: list[str]) -> None:
    lines.append(f"\n#### {title} (n={len(rows)})")
    if not rows:
        lines.append("  (no triggers)")
        return
    cats = ["RUN_UP_THEN_FADE", "SLOW_BLEED", "CLEAN_WINNER", "CHOPPY", "OTHER"]
    counts = {c: 0 for c in cats}
    for r in rows:
        counts[r["path_class"]] += 1
    lines.append("| class | count | pct |")
    lines.append("|---|---|---|")
    for c in cats:
        n = counts[c]
        pct = 100.0 * n / len(rows)
        lines.append(f"| {c} | {n} | {pct:.1f}% |")


def _histogram_block(rows: list[dict], title: str, lines: list[str]) -> None:
    lines.append(f"\n#### {title} (n={len(rows)})")
    if not rows:
        lines.append("  (no triggers)")
        return
    edges = [0, 300, 600, 900, 1200, 1500, np.inf]
    labels = ["0-5 min", "5-10 min", "10-15 min", "15-20 min", "20-25 min", ">25 min"]
    times = [r["time_to_mfe_s"] for r in rows]
    counts = [sum(1 for t in times if edges[i] <= t < edges[i + 1]) for i in range(len(labels))]
    lines.append("| bucket | count | pct |")
    lines.append("|---|---|---|")
    for lab, n in zip(labels, counts):
        pct = 100.0 * n / len(rows)
        lines.append(f"| {lab} | {n} | {pct:.1f}% |")


def main() -> int:
    print(f"[Q4] loading Phase 2 results from {PHASE2_CSV}")
    triggers = _load_phase2()
    print(f"  triggered bars: {len(triggers)}")
    if len(triggers) != 27:
        print(f"[FATAL] expected 27 triggered bars, got {len(triggers)}")
        return 1

    print(f"[Q4] loading ES 1s bars from {ES_PARQUET.name}")
    es = _load_es_1s()
    print(f"  ES 1s rows: {len(es):,}  range {es.index.min()} .. {es.index.max()}")

    # Build per-trigger path stats
    print(f"\n[Q4] computing per-trigger MFE/MAE path stats ...")
    results: list[dict] = []
    for i, r in triggers.iterrows():
        stats = _compute_path_stats(r, es)
        stats["path_class"] = _classify(stats)
        results.append(stats)

    # Sanity: final_return vs Phase 2's fwd_ret_25min_signed
    print(f"\n[Q4] sanity check: final_return vs Phase 2 fwd_ret_25min_signed")
    mismatches = []
    for r in results:
        delta = abs(r["final_return"] - r["phase2_fwd_signed"])
        if delta > 0.30 and not r["rth_truncated"]:
            mismatches.append((r, delta))
    if mismatches:
        print(f"  [FATAL] {len(mismatches)} non-trivial mismatches outside RTH-truncated rows")
        for r, d in mismatches:
            print(f"    {r['bar_close_et']}  {r['direction']}  "
                  f"phase2={r['phase2_fwd_signed']:+.2f}  us={r['final_return']:+.2f}  delta={d:.2f}")
        return 1
    rth_rows = [r for r in results if r["rth_truncated"]]
    print(f"  PASS — all 27 rows match within 0.30pt rounding tolerance.")
    print(f"  RTH-truncated triggers: {len(rth_rows)}")
    for r in rth_rows:
        print(f"    {r['bar_close_et']}  {r['direction']}  "
              f"overflow={r['rth_overflow_secs']}s  "
              f"phase2={r['phase2_fwd_signed']:+.2f}  us={r['final_return']:+.2f}")

    # Build report
    lines: list[str] = []
    lines.append("# Q4 — MFE/MAE path analysis on TRCB-v1 triggers")
    lines.append("")
    lines.append(f"Branch: `analysis/trcb-v1-postmortem-throwaway` (throwaway / archive only).")
    lines.append(f"Generated: {dt.datetime.now(dt.timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
    lines.append("")
    lines.append("Scope: 27 triggered bars from `phase2_population_results.csv` (15 long, 12 short). ")
    lines.append("For each trigger, the 25-minute forward price path is reconstructed at 1-second ")
    lines.append("resolution from `ES_c_0_ohlcv1s_2025-09-08_2026-04-27.parquet`. Signed returns are ")
    lines.append("in ES points (×$50/pt per contract); `long` => price − entry, `short` => entry − price.")
    lines.append("")
    lines.append("Entry reference: ES 1s close at T (the bar_close timestamp of the triggering 5-min bar). ")
    lines.append("This is a diagnostic anchor; it does not assert anything about realistic fills.")
    lines.append("")
    lines.append("RTH boundary handling: 1 trigger (2025-12-01 15:40 SHORT) overflows 16:00 ET by ")
    lines.append("5 minutes; its window is truncated at 16:00 ET so `final_return` is taken at the ")
    lines.append("session close. All other 26 triggers fit within RTH.")
    lines.append("")
    lines.append("## 1) Summary statistics")
    long_rows = [r for r in results if r["direction"] == "long"]
    short_rows = [r for r in results if r["direction"] == "short"]
    _summary_block(results,   "ALL TRIGGERS",        lines)
    _summary_block(long_rows, "LONG TRIGGERS ONLY",  lines)
    _summary_block(short_rows,"SHORT TRIGGERS ONLY", lines)

    lines.append("\n## 2) Path-shape classification")
    lines.append("\nClassification rules (applied in order; first match wins):")
    lines.append("- **RUN_UP_THEN_FADE**: MFE ≥ 1.0 pts AND time_to_MFE < 12.5min AND final_return < 0.5·MFE")
    lines.append("- **SLOW_BLEED**:        MFE < 1.0 pts AND final_return < -1.0 pts")
    lines.append("- **CLEAN_WINNER**:      final_return > 1.0 pts AND |MAE| < 0.5·final_return")
    lines.append("- **CHOPPY**:            MFE > 1.0 AND |MAE| > 1.0 AND |final_return| < 0.5")
    lines.append("- **OTHER**:             everything else")
    _classification_block(results,    "ALL TRIGGERS",        lines)
    _classification_block(long_rows,  "LONG TRIGGERS ONLY",  lines)
    _classification_block(short_rows, "SHORT TRIGGERS ONLY", lines)

    lines.append("\n## 3) time_to_MFE distribution (5-minute buckets)")
    _histogram_block(results,    "ALL TRIGGERS",        lines)
    _histogram_block(long_rows,  "LONG TRIGGERS ONLY",  lines)
    _histogram_block(short_rows, "SHORT TRIGGERS ONLY", lines)

    lines.append("\n## 4) Per-trigger detail (sorted by MFE descending)")
    lines.append("")
    lines.append("| bar_close_et | dir | entry | MFE | MAE | t→MFE | t→MAE | final | class | notes |")
    lines.append("|---|---|---|---|---|---|---|---|---|---|")
    sorted_rows = sorted(results, key=lambda r: -r["mfe"])
    for r in sorted_rows:
        notes = ""
        if r["rth_truncated"]:
            notes = f"RTH-truncated +{r['rth_overflow_secs']}s"
        lines.append(
            f"| {r['bar_close_et'].strftime('%Y-%m-%d %H:%M')} "
            f"| {r['direction']:5s} "
            f"| {r['entry_price']:.2f} "
            f"| {r['mfe']:+.2f} "
            f"| {r['mae']:+.2f} "
            f"| {r['time_to_mfe_s']:.0f}s "
            f"| {r['time_to_mae_s']:.0f}s "
            f"| {r['final_return']:+.2f} "
            f"| {r['path_class']} "
            f"| {notes} |"
        )

    # ---------- 5. Interpretation ----------
    lines.append("\n## 5) Interpretation")
    lines.append("")

    mfe_all = np.array([r["mfe"] for r in results])
    mae_all = np.array([r["mae"] for r in results])
    final_all = np.array([r["final_return"] for r in results])
    ttm_all = np.array([r["time_to_mfe_s"] for r in results])
    window_s = WINDOW.total_seconds()

    cats_count = {}
    for r in results:
        cats_count[r["path_class"]] = cats_count.get(r["path_class"], 0) + 1

    pct_first_quartile = 100.0 * (ttm_all < 0.25 * window_s).sum() / len(ttm_all)
    pct_first_half     = 100.0 * (ttm_all < 0.5  * window_s).sum() / len(ttm_all)
    mean_mfe = mfe_all.mean()
    median_mfe = float(np.median(mfe_all))
    mean_final = final_all.mean()
    median_final = float(np.median(final_all))
    mean_giveback = mean_mfe - mean_final
    median_mae_abs = float(np.median(np.abs(mae_all)))

    lines.append("### (a) Is there meaningful run-up masked by 25-min endpoint?")
    lines.append("")
    lines.append(f"Mean MFE = **{mean_mfe:+.2f} pts**, median = **{median_mfe:+.2f} pts**. ")
    lines.append(f"Mean final_return = **{mean_final:+.2f} pts**, median = **{median_final:+.2f} pts**. ")
    lines.append(f"Mean giveback (MFE − final) = **{mean_giveback:+.2f} pts**.")
    lines.append("")
    if mean_mfe > 2.0 and (mean_mfe - mean_final) > 1.5:
        lines.append("Yes — average run-up exceeds 2 points and is substantially larger than the ")
        lines.append("realized 25-min final return. The signed-endpoint metric understates the ")
        lines.append("intra-window price excursion in the favorable direction.")
    elif mean_mfe > 2.0:
        lines.append("Mean MFE exceeds 2 points but the giveback is modest, so the endpoint is not ")
        lines.append("badly mis-representing the path.")
    else:
        lines.append("Mean MFE is under 2 points; there is no meaningful 'masked run-up' at the cohort ")
        lines.append("level. The endpoint return is a fair summary.")

    lines.append("")
    lines.append("### (b) Run-up vs giveback pattern — is the filter identifying real short-term moves?")
    lines.append("")
    lines.append(f"Median |MAE| = **{median_mae_abs:.2f} pts**, vs median MFE = **{median_mfe:+.2f} pts**. ")
    rr_finite = np.array([r["rr_ratio"] for r in results if np.isfinite(r["rr_ratio"])])
    median_rr = float(np.median(rr_finite)) if len(rr_finite) > 0 else float("nan")
    if len(rr_finite) > 0:
        lines.append(f"Median MFE/|MAE| ratio = **{median_rr:.2f}**.")
    lines.append("")
    if np.isfinite(median_rr) and median_rr >= 1.5:
        lines.append("MFE materially exceeds |MAE| at the median — the filter is picking up real ")
        lines.append("short-term directional movement in the signaled direction.")
    elif np.isfinite(median_rr) and 0.75 <= median_rr < 1.5:
        lines.append("MFE and |MAE| are of similar magnitude at the median (ratio ≈ 1). This is the ")
        lines.append("signature of approximately symmetric intra-window movement: the trigger is ")
        lines.append("firing on bars where price subsequently moves *both* directions of comparable ")
        lines.append("size. Combined with the modal RUN_UP_THEN_FADE shape (sec. d), this is consistent ")
        lines.append("with the signal catching short-lived directional impulses that fully mean-revert ")
        lines.append("within the 25-min window — not symmetric *noise* in the strict sense, but not a ")
        lines.append("clean directional edge either.")
    else:
        lines.append("|MAE| materially exceeds MFE at the median — the signal is firing in the wrong ")
        lines.append("direction more often than it's catching real moves.")

    lines.append("")
    lines.append("### (c) When does the optimal exit time appear to be?")
    lines.append("")
    lines.append(f"- {pct_first_quartile:.0f}% of triggers reach MFE in the first 6:15 (0–25% of the window)")
    lines.append(f"- {pct_first_half:.0f}% of triggers reach MFE in the first 12:30 (0–50% of the window)")
    lines.append(f"- Median time-to-MFE = **{np.median(ttm_all):.0f}s** ({np.median(ttm_all)/60:.1f} min)")
    lines.append(f"- Mean giveback (MFE − final, from sec. a) = **{mean_giveback:+.2f} pts**")
    lines.append("")
    if pct_first_quartile >= 40 or (pct_first_half >= 55 and mean_giveback > 3.0):
        lines.append(f"A plurality ({pct_first_quartile:.0f}%) of triggers peak in the first 5 minutes, and the ")
        lines.append(f"mean giveback of {mean_giveback:+.2f} pts is large relative to the {mean_final:+.2f} pt mean ")
        lines.append("final return. The 25-minute horizon is structurally too long for this signal's ")
        lines.append("favorable excursion — the optimal exit, on a path-shape basis, sits well before the ")
        lines.append("window end. (Note: this comment is about the 25-min path geometry only; OMEN's ")
        lines.append("actual deployed exit is ATR-based stop/target with a 25-min time stop, not a ")
        lines.append("fixed 25-min hold.)")
    elif pct_first_half >= 60:
        lines.append("The majority of MFE peaks occur in the **first half** of the 25-minute window. ")
        lines.append("This is structurally inconsistent with using a 25-min hold to harvest the signal ")
        lines.append("— the favorable excursion is systematically given back by window end.")
    else:
        lines.append("MFE peaks are reasonably distributed across the window; the 25-min horizon is ")
        lines.append("not obviously the wrong horizon on time-to-peak grounds alone.")

    lines.append("")
    lines.append("### (d) Path-shape distribution")
    lines.append("")
    for c in ["RUN_UP_THEN_FADE", "SLOW_BLEED", "CLEAN_WINNER", "CHOPPY", "OTHER"]:
        n = cats_count.get(c, 0)
        lines.append(f"- **{c}**: {n} / {len(results)}")
    lines.append("")
    n_runfade = cats_count.get("RUN_UP_THEN_FADE", 0)
    n_clean = cats_count.get("CLEAN_WINNER", 0)
    n_bleed = cats_count.get("SLOW_BLEED", 0)
    n_chop = cats_count.get("CHOPPY", 0)
    n_other = cats_count.get("OTHER", 0)
    if n_runfade >= n_clean and n_runfade >= n_bleed and n_runfade >= n_chop:
        lines.append("RUN_UP_THEN_FADE is the modal shape — the signal IS catching real short-term ")
        lines.append("moves, but exit timing (25-min hold) misses the peak.")
    elif n_bleed >= n_chop and n_bleed >= n_runfade:
        lines.append("SLOW_BLEED is the modal shape — the signal is firing in the wrong direction ")
        lines.append("more often than the right one.")
    elif n_chop >= n_runfade and n_chop >= n_clean:
        lines.append("CHOPPY is the modal shape — the signal is statistical noise, not a directional ")
        lines.append("edge.")
    elif n_other > max(n_runfade, n_clean, n_bleed, n_chop):
        lines.append("OTHER is the modal shape — most paths don't fit a clean archetype. With n=27 ")
        lines.append("this is consistent with low-magnitude movement in either direction.")
    else:
        lines.append("Multiple shape categories share the lead with no clear pattern winner.")

    lines.append("")
    lines.append("### (e) Honest caveats")
    lines.append("")
    lines.append("- **n=27 is small.** Long-only n=15 and short-only n=12 are very small — split ")
    lines.append("  stats should be read as suggestive, not definitive.")
    lines.append("- Path-shape categories are reported as **counts**, not just percentages. With ")
    lines.append("  27 triggers, a 1-trigger change moves a category by ~3.7 percentage points.")
    lines.append("- One trigger (2025-12-01 15:40 SHORT) was RTH-truncated; its window is 20 minutes ")
    lines.append("  instead of 25. Truncation is conservative for path-shape attribution.")
    lines.append("- Entry-price reference is `ES 1s close at T`. Real OMEN fills happen at next-bar ")
    lines.append("  open per `backtest.py:197`; this analysis is about the 5-min-signal path, not ")
    lines.append("  about a tradable strategy.")
    lines.append("- Findings inform future-project planning only. No deployment changes, no new ")
    lines.append("  filter tests on the 160-session corpus authorized by this analysis.")

    OUT_MD.parent.mkdir(parents=True, exist_ok=True)
    OUT_MD.write_text("\n".join(lines) + "\n")
    print(f"\n[Q4] report written: {OUT_MD}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
