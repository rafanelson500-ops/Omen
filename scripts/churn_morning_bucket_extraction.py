"""Cross-project consultation extraction: morning + noon-transition churn IC.

Mirrors EXACTLY the Step 3 methodology in
  /Users/rafanelson/OneMinL2/scripts/signal_ic/churn_conditional.py
(read 2026-05-15). Source file:line references are given per constant.
Read-only on the OneMinL2 pre-IS corpus. Touches nothing in cheese/ and
nothing the live daemon/runner depends on.

Scope: this is +1 trial in OMEN's churn multiple-comparison search,
noted for FUTURE DSR accounting. It does NOT modify the DSR ledger, does
NOT re-open Step 3, and does NOT feed OMEN's post-verdict shortlist
ranking regardless of result.

Methodology constants (EXACT, from churn_conditional.py):
  CORPUS                = data/corpus_1min.parquet          (L25)  1-min grid
  IS_START              = 2025-12-26 ; pre-IS = date < IS_START      (L26,91)
  MIN_BARS_PER_SESSION  = 30                                         (L28,50)
  next_return = log(next_close/close), per-session shift(-1)          (L95-96)
  churn_lag1  = churn.shift(1), per-session (look-ahead-clean)        (L97)
  frame = dropna(next_return, churn_lag1)                             (L99)
  per-session IC = scipy.stats.spearmanr(x, y).statistic              (L56)
    skip session if len < 30, or x/y constant, or rho NaN             (L50-58)
  cross-session t = mean / (std_ddof1 / sqrt(n)); two-tailed
    p = 2 * stats.t.sf(|t|, df=n-1)                                   (L69-73)
  buckets: tod = ts_open.dt.time (corpus ts_open is tz-aware
    America/New_York, so .dt.time is ET); membership (tod>=lo)&(tod<hi)
    inclusive-lower / exclusive-upper                                 (L181-184)
  Step 3 reported §3 windows: open[09:30,10:30) mid_morning[10:30,12:00)
    lunch[12:00,14:00) afternoon[14:00,16:00)                         (L31-36)
"""
from __future__ import annotations

import datetime as dt
import sys
from datetime import datetime, time, timezone
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

CORPUS = Path("/Users/rafanelson/OneMinL2/data/corpus_1min.parquet")
IS_START = pd.Timestamp("2025-12-26").date()
MIN_BARS_PER_SESSION = 30
OUT = Path("/Users/rafanelson/Omen/diagnostics/churn_morning_extraction/"
           "morning_noon_churn_extraction_20260515.md")

# New slices requested (ET, inclusive-lower / exclusive-upper — same rule as §3)
SLICE_A = ("morning",         time(9, 30),  time(11, 30))   # [09:30, 11:30)
SLICE_B = ("noon_transition", time(11, 30), time(12, 0))    # [11:30, 12:00)

# Step 3 §3 buckets — re-derived here as a zero-drift fidelity gate.
STEP3_BUCKETS = [
    ("open",        time(9, 30),  time(10, 30)),
    ("mid_morning", time(10, 30), time(12, 0)),
    ("lunch",       time(12, 0),  time(14, 0)),
    ("afternoon",   time(14, 0),  time(16, 0)),
]
# Reported §3 signed-next_return t-stats (diagnostics/signal_ic/03_churn_conditional.md)
STEP3_REPORTED_T = {"open": 3.161, "mid_morning": 3.591,
                    "lunch": 5.033, "afternoon": 1.501}
STEP3_T_TOL = 0.01  # exact-reproduction gate


def per_session_ic(df: pd.DataFrame, feat: str, target: str) -> list[float]:
    """EXACT copy of churn_conditional.py:47-60."""
    rhos: list[float] = []
    for _, sess in df.groupby("date", sort=True):
        if len(sess) < MIN_BARS_PER_SESSION:
            continue
        x = sess[feat].to_numpy()
        y = sess[target].to_numpy()
        if np.all(x == x[0]) or np.all(y == y[0]):
            continue
        rho = stats.spearmanr(x, y).statistic
        if np.isnan(rho):
            continue
        rhos.append(float(rho))
    return rhos


def summarise(rhos: list[float]) -> dict:
    """EXACT copy of churn_conditional.py:63-75."""
    arr = np.asarray(rhos, dtype=float)
    n = len(arr)
    if n < 2:
        nan = float("nan")
        return {"n": n, "mean": nan, "median": nan, "std": nan,
                "tstat": nan, "pval": nan, "pct_gt_0": nan}
    mean = float(arr.mean())
    median = float(np.median(arr))
    std = float(arr.std(ddof=1))
    tstat = mean / (std / np.sqrt(n)) if std > 0 else float("nan")
    pval = float(2 * stats.t.sf(abs(tstat), df=n - 1)) if not np.isnan(tstat) else float("nan")
    pct_gt_0 = float((arr > 0).mean() * 100)
    return {"n": n, "mean": mean, "median": median, "std": std,
            "tstat": tstat, "pval": pval, "pct_gt_0": pct_gt_0}


def _per_session_obs(df: pd.DataFrame) -> pd.Series:
    return df.groupby("date").size()


def main() -> int:
    # ---- frame: EXACT Step 3 construction ----
    df = pd.read_parquet(CORPUS)
    df["date"] = pd.to_datetime(df["date"]).dt.date
    df = df[df["date"] < IS_START].copy()
    df = df.sort_values(["date", "ts_open"]).reset_index(drop=True)
    g = df.groupby("date", sort=False)
    df["next_close"] = g["close"].shift(-1)
    df["next_return"] = np.log(df["next_close"] / df["close"])
    df["churn_lag1"] = g["churn"].shift(1)
    work = df.dropna(subset=["next_return", "churn_lag1"]).copy()
    work["abs_return"] = work["next_return"].abs()
    tod = work["ts_open"].dt.time

    n_sessions = work["date"].nunique()
    d0, d1 = work["date"].min(), work["date"].max()
    n_bars = len(work)

    # ---- zero-drift gate: reproduce Step 3 §3 signed t-stats ----
    gate_lines, gate_ok = [], True
    for name, lo, hi in STEP3_BUCKETS:
        sub = work[(tod >= lo) & (tod < hi)]
        s = summarise(per_session_ic(sub, "churn_lag1", "next_return"))
        rep = STEP3_REPORTED_T[name]
        ok = abs(s["tstat"] - rep) <= STEP3_T_TOL
        gate_ok &= ok
        gate_lines.append(
            f"| {name} [{lo.strftime('%H:%M')},{hi.strftime('%H:%M')}) "
            f"| {len(sub):,} | {s['mean']:+.5f} | {s['tstat']:+.3f} "
            f"| {rep:+.3f} | {'OK' if ok else 'DRIFT'} | {s['n']} |")
    if not gate_ok:
        OUT.parent.mkdir(parents=True, exist_ok=True)
        OUT.write_text("# STOP — methodology fidelity gate FAILED\n\n"
                        "Re-derived Step 3 §3 t-stats do not match the "
                        "reported 3.161/3.591/5.033/1.501. Extraction "
                        "aborted (methodology drift = uninterpretable).\n\n"
                        + "\n".join(gate_lines) + "\n")
        print("STOP: Step 3 fidelity gate failed", file=sys.stderr)
        return 2

    # ---- new slices: both targets ----
    def slice_block(nm, lo, hi):
        sub = work[(tod >= lo) & (tod < hi)]
        obs = _per_session_obs(sub)
        low_obs = sorted(str(d) for d, c in obs.items()
                         if c < MIN_BARS_PER_SESSION)
        out = {"name": nm, "lo": lo, "hi": hi, "n_bars": len(sub),
               "obs_min": int(obs.min()) if len(obs) else 0,
               "obs_med": float(obs.median()) if len(obs) else 0.0,
               "n_sess_in_slice": int(sub["date"].nunique()),
               "low_obs_sessions": low_obs}
        for tgt_label, tgt in (("signed", "next_return"),
                               ("absret", "abs_return")):
            g_ = stats.spearmanr(sub["churn_lag1"].to_numpy(),
                                 sub[tgt].to_numpy())
            s = summarise(per_session_ic(sub, "churn_lag1", tgt))
            out[tgt_label] = {
                "global_rho": float(g_.statistic),
                "global_p": float(g_.pvalue),
                "mean_ic": s["mean"], "median_ic": s["median"],
                "tstat": s["tstat"], "pval": s["pval"],
                "pct_gt_0": s["pct_gt_0"], "n_sess": s["n"]}
        return out

    A = slice_block(*SLICE_A)
    B = slice_block(*SLICE_B)

    # whole-corpus magnitude anchor (Step 3 §5 'magnitude' row equivalent)
    mag_all = summarise(per_session_ic(work, "churn_lag1", "abs_return"))
    sgn_all = summarise(per_session_ic(work, "churn_lag1", "next_return"))

    # ---- report ----
    L = []
    L.append("# Morning & Noon-Transition Churn-IC Extraction")
    L.append(f"_generated: {datetime.now(timezone.utc).astimezone().isoformat(timespec='seconds')}_")
    L.append("")
    L.append("> **HEADER NOTE.** The task mandated a verbatim header whose "
             "text was truncated in the request and never supplied. The "
             "block below is reconstructed from the task's explicit scope "
             "guards; replace with the verbatim text when provided "
             "(one-line edit, numbers unaffected).")
    L.append("")
    L.append("## Header")
    L.append("")
    L.append("- **Purpose:** cross-project consultation extraction for the "
             "OMEN+V4.1 synthesis project; resolves a conditional bookmark "
             "on their side. Exploratory.")
    L.append("- **DSR accounting:** counts as **one additional trial** in "
             "OMEN's multiple-comparison search on the churn signal. "
             "Recorded here for FUTURE DSR accounting; the DSR ledger is "
             "**not** modified by this extraction.")
    L.append("- **Scope guard:** NOT a re-opening of Step 3; NOT a "
             "re-ranking input for OMEN's post-verdict pre-reg shortlist "
             "(churn currently #2 — unchanged regardless of this result); "
             "NOT a modification of any locked baseline parameter.")
    L.append("- **Branch:** `analysis/churn-morning-bucket-throwaway` "
             "(archive-only; never merges to main; cheese/ untouched).")
    L.append("- **Methodology source:** "
             "`OneMinL2/scripts/signal_ic/churn_conditional.py` "
             "(mirrored exactly; constants cite file:line in the script "
             "header).")
    L.append("")
    L.append("## Step 1 — methodology (mirrored exactly)")
    L.append("")
    L.append("1-min corpus; feature `churn_lag1`=churn.shift(1) per "
             "session; target `next_return`=log(next_close/close) per "
             "session (signed) and `abs_return`=|next_return| (magnitude); "
             "frame drops null next_return/churn_lag1; per-session "
             "**Spearman** IC (skip <30 bars/session or constant series); "
             "cross-session one-sample t = mean/(std_ddof1/√n), "
             "two-tailed p. Buckets from `ts_open.dt.time` "
             "(corpus tz = America/New_York → ET), inclusive-lower / "
             "exclusive-upper.")
    L.append("")
    L.append("## Step 2 — corpus")
    L.append("")
    L.append(f"- pre-IS = `date < {IS_START}`")
    L.append(f"- **sessions: {n_sessions}** ({d0} → {d1}); bars: "
             f"**{n_bars:,}**")
    L.append(f"- expected 75 sessions Sep 8 2025 – Dec 24 2025 — "
             f"{'**matches, no change**' if (n_sessions==75 and str(d0)=='2025-09-08' and str(d1)=='2025-12-24') else '**CHANGED — see numbers above**'}")
    L.append("")
    L.append("## Methodology-fidelity gate (re-derived Step 3 §3, signed)")
    L.append("")
    L.append("| bucket (ET) | n bars | mean PS IC | t (mine) | t (reported) | match | n sess |")
    L.append("|---|---:|---:|---:|---:|:--:|---:|")
    L.extend(gate_lines)
    L.append("")
    L.append("> Gate **PASSED** — re-derivation reproduces the reported "
             "§3 signed t-stats within ±0.01, so the slices below are "
             "directly comparable to the published lunch +5.033 / "
             "afternoon +1.501 (signed) numbers.")
    L.append("")
    L.append("## Step 3 — new slices (both targets, side by side)")
    L.append("")
    L.append("**Signed `next_return`** (directly comparable to §3 "
             "lunch +5.033, afternoon +1.501, mid_morning +3.591, "
             "open +3.161):")
    L.append("")
    L.append("| slice (ET) | n bars | global ρ | global p | mean PS IC | "
             "median | t-stat | t p | % sess>0 | n sess |")
    L.append("|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|")
    for X in (A, B):
        s = X["signed"]
        L.append(
            f"| {X['name']} "
            f"[{X['lo'].strftime('%H:%M')},{X['hi'].strftime('%H:%M')}) "
            f"| {X['n_bars']:,} | {s['global_rho']:+.5f} "
            f"| {s['global_p']:.3e} | {s['mean_ic']:+.5f} "
            f"| {s['median_ic']:+.5f} | {s['tstat']:+.3f} "
            f"| {s['pval']:.3e} | {s['pct_gt_0']:.1f}% | {s['n_sess']} |")
    L.append(f"| _whole-corpus (signed, §5 anchor)_ | {n_bars:,} | — | — "
             f"| {sgn_all['mean']:+.5f} | {sgn_all['median']:+.5f} "
             f"| {sgn_all['tstat']:+.3f} | {sgn_all['pval']:.3e} "
             f"| {sgn_all['pct_gt_0']:.1f}% | {sgn_all['n']} |")
    L.append("")
    L.append("**Magnitude `|next_return|`** (comparable to the §5 "
             "whole-corpus magnitude row only — Step 3 published **no** "
             "per-time-of-day |return| baseline):")
    L.append("")
    L.append("| slice (ET) | n bars | global ρ | global p | mean PS IC | "
             "median | t-stat | t p | % sess>0 | n sess |")
    L.append("|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|")
    for X in (A, B):
        s = X["absret"]
        L.append(
            f"| {X['name']} "
            f"[{X['lo'].strftime('%H:%M')},{X['hi'].strftime('%H:%M')}) "
            f"| {X['n_bars']:,} | {s['global_rho']:+.5f} "
            f"| {s['global_p']:.3e} | {s['mean_ic']:+.5f} "
            f"| {s['median_ic']:+.5f} | {s['tstat']:+.3f} "
            f"| {s['pval']:.3e} | {s['pct_gt_0']:.1f}% | {s['n_sess']} |")
    L.append(f"| _whole-corpus (\\|return\\|, §5 anchor)_ | {n_bars:,} | — "
             f"| — | {mag_all['mean']:+.5f} | {mag_all['median']:+.5f} "
             f"| {mag_all['tstat']:+.3f} | {mag_all['pval']:.3e} "
             f"| {mag_all['pct_gt_0']:.1f}% | {mag_all['n']} |")
    L.append("")
    L.append("### Per-slice observation sanity")
    L.append("")
    for X in (A, B):
        flag = (", ".join(X["low_obs_sessions"])
                if X["low_obs_sessions"] else "none")
        L.append(f"- **{X['name']}** "
                 f"[{X['lo'].strftime('%H:%M')},{X['hi'].strftime('%H:%M')}): "
                 f"sessions in slice {X['n_sess_in_slice']}, "
                 f"min obs/session **{X['obs_min']}**, "
                 f"median **{X['obs_med']:.0f}**; sessions with <30 obs: "
                 f"{flag}")
    L.append("")
    L.append("## Step 4 — reconciliation of reported lunch/afternoon")
    L.append("")
    L.append("From `churn_conditional.py:31-36` and "
             "`diagnostics/signal_ic/03_churn_conditional.md §3`:")
    L.append("")
    L.append("- Reported **lunch t=5.033** covers **[12:00, 14:00) ET** "
             "(mean PS IC +0.04894, 75 sess) — *not* 12:00-13:00, *not* "
             "11:30-13:00.")
    L.append("- Reported **afternoon t=1.501** = **[14:00, 16:00) ET** "
             "(73 sess).")
    L.append("- Step 3 buckets tile **[09:30, 16:00) with no gap** "
             "(open/mid_morning/lunch/afternoon; script asserts 0 "
             "unbucketed).")
    L.append("- **Noon-transition [11:30, 12:00) is a strict sub-slice of "
             "Step 3's `mid_morning` [10:30, 12:00)** (reported "
             "t=+3.591). It was **never uncategorized** and **never in "
             "lunch** — the suspected gap does not exist.")
    L.append("- **Morning [09:30, 11:30)** = all of Step 3 `open` "
             "[09:30,10:30) (t=+3.161) **plus** the first hour of "
             "`mid_morning` [10:30,11:30); it is a recombination across "
             "two existing §3 buckets, not new uncategorized data.")
    L.append("")
    L.append("_End of report. Numbers + reconciliation only — no "
             "interpretation, no ranking input, no parameter change._")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("\n".join(L) + "\n")
    print(f"gate {'PASSED' if gate_ok else 'FAILED'}; wrote {OUT}")
    print(f"A signed t={A['signed']['tstat']:+.3f} | "
          f"A absret t={A['absret']['tstat']:+.3f} | "
          f"B signed t={B['signed']['tstat']:+.3f} | "
          f"B absret t={B['absret']['tstat']:+.3f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
