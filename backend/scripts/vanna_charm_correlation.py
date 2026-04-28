"""Vanna/charm flow predictive-power diagnostic.

Tests whether the unused GEXbot state columns `zvanna`, `ovanna`,
`zcharm`, `ocharm` carry forward-return signal at intraday horizons,
using the same rolling Z-score methodology that `cheese.features`
applies to `gexoflow_sum` / `dexoflow_sum`. Read-only.

Reference: DeLorenzo (SSRN 4669282) on charm-flow predictive power.

Operating note: vanna/charm are aggregated by `gex.resample()` as
STATE columns (last value per bar), not as FLOW columns (sum/max/min
within bar). The Z-score is therefore taken over the bar-end
*observation* rather than over a per-bar integrated quantity. This
mirrors the existing resampler's classification and keeps the
pipeline read-only.
"""
from __future__ import annotations

from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import pearsonr, spearmanr

import sys
BACKEND = Path("/Users/rafanelson/Omen/backend")
sys.path.insert(0, str(BACKEND))

from cheese import features as features_mod, gex as gex_mod, market  # noqa: E402

START = date(2025, 12, 26)
END = date(2026, 4, 22)
FREQ = "5min"
Z_WINDOW = 60
Z_MIN_PERIODS = 20            # matches features.py: FLOW_Z_WINDOW // 3
HORIZONS = [1, 3, 5, 10, 25]  # bars (5, 15, 25, 50, 125 min at 5min freq)
EXTREME_Z = 2.0
SIGNIFICANCE_P = 0.01
THRESH_SIGNAL = 0.05
THRESH_WEAK = 0.02

NEW_FEATS = ["zvanna", "ovanna", "zcharm", "ocharm"]

OUT_DIR = BACKEND / "data" / "analysis"
OUT_CSV = OUT_DIR / "vanna_charm_correlations.csv"
REPORT_MD = BACKEND / "diagnostics" / "vanna_charm" / "REPORT.md"


def load_feat() -> pd.DataFrame:
    days = gex_mod.rth_sessions(START, END)
    mkt = market.load(START, END, freq=FREQ, rth_only=True)
    raw = gex_mod.load_range(days)
    gex_bars = gex_mod.resample(raw, freq=FREQ)
    feat = features_mod.build_features(mkt, gex_bars)
    return feat


def add_new_zscores(feat: pd.DataFrame) -> pd.DataFrame:
    df = feat.copy()
    for col in NEW_FEATS:
        if col not in df.columns:
            df[f"{col}_z"] = np.nan
            continue
        mu = df[col].rolling(Z_WINDOW, min_periods=Z_MIN_PERIODS).mean()
        sd = df[col].rolling(Z_WINDOW, min_periods=Z_MIN_PERIODS).std(ddof=0)
        df[f"{col}_z"] = (df[col] - mu) / sd.replace(0, np.nan)
    return df


def add_forward_returns(feat: pd.DataFrame) -> pd.DataFrame:
    df = feat.copy()
    log_close = np.log(df["close"].astype(float))
    for h in HORIZONS:
        df[f"fwd_ret_{h}"] = log_close.shift(-h) - log_close
    return df


def correlation_table(df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for feat in NEW_FEATS:
        z_col = f"{feat}_z"
        if z_col not in df.columns:
            continue
        for h in HORIZONS:
            r_col = f"fwd_ret_{h}"
            sub = df[[z_col, r_col]].dropna()
            n = len(sub)
            if n < 30:
                rows.append({
                    "feature": feat, "horizon_bars": h, "n": n,
                    "pearson_r": np.nan, "pearson_p": np.nan,
                    "spearman_r": np.nan, "spearman_p": np.nan,
                })
                continue
            pr = pearsonr(sub[z_col].to_numpy(), sub[r_col].to_numpy())
            sr = spearmanr(sub[z_col].to_numpy(), sub[r_col].to_numpy())
            rows.append({
                "feature": feat, "horizon_bars": h, "n": n,
                "pearson_r": float(pr.statistic), "pearson_p": float(pr.pvalue),
                "spearman_r": float(sr.statistic), "spearman_p": float(sr.pvalue),
            })
    return pd.DataFrame(rows)


def conditional_effect_table(df: pd.DataFrame) -> pd.DataFrame:
    """For each (feature, horizon): compute mean of side·fwd_return when
    |z| > EXTREME_Z, vs unconditional mean. Express as Welch-style
    t-statistic to flag whether the conditional mean is materially above the
    grand mean.
    """
    rows = []
    for feat in NEW_FEATS:
        z_col = f"{feat}_z"
        if z_col not in df.columns:
            continue
        for h in HORIZONS:
            r_col = f"fwd_ret_{h}"
            sub = df[[z_col, r_col]].dropna()
            if len(sub) < 30:
                continue
            uncond_mean = float(sub[r_col].mean())
            uncond_std = float(sub[r_col].std(ddof=1))

            mask = sub[z_col].abs() > EXTREME_Z
            cond = sub.loc[mask].copy()
            n_cond = len(cond)
            if n_cond < 5:
                rows.append({
                    "feature": feat, "horizon_bars": h, "n_cond": n_cond,
                    "uncond_mean_ret": uncond_mean,
                    "cond_signed_mean_ret": np.nan,
                    "effect_z": np.nan,
                })
                continue
            # signed return = sign(z) * fwd_ret  (i.e. predicted direction)
            cond["signed_ret"] = np.sign(cond[z_col]) * cond[r_col]
            cond_signed_mean = float(cond["signed_ret"].mean())
            cond_se = float(cond["signed_ret"].std(ddof=1) / np.sqrt(n_cond))
            effect_z = (cond_signed_mean - 0.0) / cond_se if cond_se > 0 else np.nan
            rows.append({
                "feature": feat, "horizon_bars": h, "n_cond": n_cond,
                "uncond_mean_ret": uncond_mean,
                "cond_signed_mean_ret": cond_signed_mean,
                "effect_z": effect_z,
            })
    return pd.DataFrame(rows)


def interaction_table(df: pd.DataFrame) -> pd.DataFrame:
    """zvanna_z and zcharm_z interaction with gexoflow_z>2.0:
    compare mean forward return on combined gate vs gexoflow_z>2.0 alone.
    Both gates restrict to the gexoflow_z > 2.0 set first, then split by
    feature_z > 2.0 vs not.
    """
    if "gexoflow_z" not in df.columns:
        return pd.DataFrame()
    rows = []
    for feat in ("zvanna_z", "zcharm_z"):
        if feat not in df.columns:
            continue
        for h in HORIZONS:
            r_col = f"fwd_ret_{h}"
            sub = df[["gexoflow_z", feat, r_col]].dropna()
            base = sub[sub["gexoflow_z"] > EXTREME_Z]
            n_base = len(base)
            if n_base < 5:
                continue
            base_mean = float(base[r_col].mean())
            both = base[base[feat] > EXTREME_Z]
            only_gex = base[base[feat] <= EXTREME_Z]
            row = {
                "feature_z": feat, "horizon_bars": h,
                "n_gex_alone": int(len(only_gex)),
                "mean_ret_gex_alone": float(only_gex[r_col].mean()) if len(only_gex) else np.nan,
                "n_both_gates": int(len(both)),
                "mean_ret_both_gates": float(both[r_col].mean()) if len(both) else np.nan,
                "n_total_gex_gate": n_base,
                "mean_ret_full_gex_gate": base_mean,
            }
            if len(both) >= 3 and len(only_gex) >= 3:
                # Welch t for difference in means
                m_b = both[r_col].to_numpy()
                m_o = only_gex[r_col].to_numpy()
                diff = m_b.mean() - m_o.mean()
                se = float(np.sqrt(m_b.var(ddof=1)/len(m_b) + m_o.var(ddof=1)/len(m_o)))
                row["delta_mean_ret"] = float(diff)
                row["welch_t"] = float(diff / se) if se > 0 else np.nan
            else:
                row["delta_mean_ret"] = np.nan
                row["welch_t"] = np.nan
            rows.append(row)
    return pd.DataFrame(rows)


def verdict_for(feat: str, corr_df: pd.DataFrame) -> tuple[str, str]:
    """SIGNAL if any horizon has |Spearman| > 0.05 with p < 0.01; WEAK if
    |Spearman| > 0.02 at any horizon; else NOISE."""
    sub = corr_df[corr_df["feature"] == feat]
    if sub.empty or sub["spearman_r"].isna().all():
        return "NOISE", f"{feat}: no usable rows."
    abs_r = sub["spearman_r"].abs()
    p = sub["spearman_p"]
    strong = sub[(abs_r > THRESH_SIGNAL) & (p < SIGNIFICANCE_P)]
    if not strong.empty:
        best = strong.loc[strong["spearman_r"].abs().idxmax()]
        return "SIGNAL", (
            f"horizon={int(best['horizon_bars'])}  "
            f"Spearman={best['spearman_r']:+.4f} (p={best['spearman_p']:.2e}, "
            f"n={int(best['n'])})"
        )
    weak = sub[abs_r > THRESH_WEAK]
    if not weak.empty:
        best = weak.loc[weak["spearman_r"].abs().idxmax()]
        return "WEAK", (
            f"horizon={int(best['horizon_bars'])}  "
            f"Spearman={best['spearman_r']:+.4f} (p={best['spearman_p']:.2e}, "
            f"n={int(best['n'])})"
        )
    best = sub.loc[sub["spearman_r"].abs().idxmax()]
    return "NOISE", (
        f"max |Spearman| at horizon={int(best['horizon_bars'])} = "
        f"{best['spearman_r']:+.4f} (p={best['spearman_p']:.2e})"
    )


# --------------------------------------------------------------------------
def main() -> None:
    print("=== Vanna/charm correlation diagnostic ===\n")

    print("[1] Loading features…")
    feat = load_feat()
    print(f"  feat shape: {feat.shape}, range {feat.index.min()} → {feat.index.max()}")
    have = [c for c in NEW_FEATS if c in feat.columns]
    missing = [c for c in NEW_FEATS if c not in feat.columns]
    print(f"  state cols available: {have}")
    if missing:
        print(f"  MISSING: {missing} — will be filled NaN")

    print("\n[2] Computing rolling Z-scores (60-bar, min_periods=20)…")
    feat = add_new_zscores(feat)
    z_finite = {c: int(feat[f"{c}_z"].notna().sum()) for c in NEW_FEATS}
    print(f"  finite Z values per feature: {z_finite}")

    print("\n[3] Computing forward log returns…")
    feat = add_forward_returns(feat)

    print("\n[4] Correlation table (Pearson + Spearman, NaN-pairs dropped)…")
    corr = correlation_table(feat)
    _print_corr(corr)

    print("\n[5] Conditional-return effect when |z| > 2.0 (signed by direction)…")
    cond = conditional_effect_table(feat)
    _print_cond(cond)

    print("\n[6] Interaction with gexoflow_z > 2.0…")
    inter = interaction_table(feat)
    _print_inter(inter)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    bundle = pd.concat([
        corr.assign(table="correlation"),
        cond.assign(table="conditional"),
        inter.assign(table="interaction"),
    ], ignore_index=True)
    bundle.to_csv(OUT_CSV, index=False)
    print(f"\n[7] Saved: {OUT_CSV}")

    REPORT_MD.parent.mkdir(parents=True, exist_ok=True)
    REPORT_MD.write_text(_build_report(feat, corr, cond, inter))
    print(f"     REPORT: {REPORT_MD}")


# -------------------- printing -------------------------------------------
def _print_corr(corr: pd.DataFrame) -> None:
    if corr.empty:
        print("  (empty)"); return
    show = corr.copy()
    for c in ("pearson_r", "pearson_p", "spearman_r", "spearman_p"):
        show[c] = show[c].map(lambda v: "—" if pd.isna(v) else f"{v:+.4f}")
    print(show.to_string(index=False))


def _print_cond(cond: pd.DataFrame) -> None:
    if cond.empty:
        print("  (empty)"); return
    show = cond.copy()
    show["uncond_mean_ret"] = show["uncond_mean_ret"].map(lambda v: f"{v:+.6f}")
    show["cond_signed_mean_ret"] = show["cond_signed_mean_ret"].map(
        lambda v: "—" if pd.isna(v) else f"{v:+.6f}"
    )
    show["effect_z"] = show["effect_z"].map(lambda v: "—" if pd.isna(v) else f"{v:+.3f}")
    print(show.to_string(index=False))


def _print_inter(inter: pd.DataFrame) -> None:
    if inter.empty:
        print("  (empty)"); return
    show = inter.copy()
    for c in ("mean_ret_gex_alone", "mean_ret_both_gates",
              "mean_ret_full_gex_gate", "delta_mean_ret"):
        show[c] = show[c].map(lambda v: "—" if pd.isna(v) else f"{v:+.6f}")
    show["welch_t"] = show["welch_t"].map(lambda v: "—" if pd.isna(v) else f"{v:+.3f}")
    print(show.to_string(index=False))


# -------------------- markdown report ------------------------------------
def _md_table(df: pd.DataFrame, money_cols: set[str] | None = None) -> str:
    money_cols = money_cols or set()
    cols = list(df.columns)
    out = ["| " + " | ".join(cols) + " |",
           "|" + "|".join("---" if c in ("feature", "feature_z", "table") else "---:" for c in cols) + "|"]
    for _, r in df.iterrows():
        cells = []
        for c in cols:
            v = r[c]
            if pd.isna(v):
                cells.append("—")
            elif c.endswith("_p"):
                cells.append(f"{v:.2e}")
            elif c.endswith("_r") or c == "spearman_r" or c == "pearson_r":
                cells.append(f"{v:+.4f}")
            elif "mean_ret" in c or "delta" in c or c == "uncond_mean_ret" or c == "cond_signed_mean_ret":
                cells.append(f"{v:+.6f}")
            elif c == "effect_z" or c == "welch_t":
                cells.append(f"{v:+.3f}")
            elif isinstance(v, (int, np.integer)):
                cells.append(str(int(v)))
            elif isinstance(v, float) and float(v).is_integer():
                cells.append(str(int(v)))
            else:
                cells.append(str(v))
        out.append("| " + " | ".join(cells) + " |")
    return "\n".join(out)


def _build_report(feat, corr, cond, inter) -> str:
    parts = []
    parts.append("# Vanna / charm correlation diagnostic — Flow Burst feature discovery\n")

    # find strongest signal across all (feature, horizon) cells
    strongest = None
    if not corr.empty:
        idx = corr["spearman_r"].abs().idxmax() if not corr["spearman_r"].isna().all() else None
        if idx is not None:
            strongest = corr.loc[idx]

    parts.append("## Summary\n")
    if strongest is not None:
        parts.append(
            f"On {len(feat):,} 5-min bars over the locked window (Dec 2025 – Apr 2026), "
            f"rolling 60-bar Z-scores of the four GEXbot state columns "
            f"`zvanna`, `ovanna`, `zcharm`, `ocharm` were correlated with forward log "
            f"returns at horizons 1/3/5/10/25 bars. The strongest cell across all "
            f"40 (feature × horizon × method) combinations is "
            f"**{strongest['feature']} @ horizon={int(strongest['horizon_bars'])} bars**, "
            f"Spearman = **{strongest['spearman_r']:+.4f}** "
            f"(p={strongest['spearman_p']:.2e}, n={int(strongest['n'])}). "
            f"For intraday futures signals, |ρ| in the 0.05–0.10 range is typical for a "
            f"useful predictor; below ~0.02 is indistinguishable from noise.\n"
        )
    else:
        parts.append("No usable correlation cells produced.\n")

    parts.append("## Methodology\n")
    parts.append(
        f"- Window: 2025-12-26 → 2026-04-22, 5-min bars, RTH only.\n"
        f"- GEX resampled with `cheese.gex.resample(freq='5min')` (state cols → `last()` per bar).\n"
        f"- Z-score: `(x - x.rolling({Z_WINDOW}, min_periods={Z_MIN_PERIODS}).mean()) / "
        f"x.rolling({Z_WINDOW}, min_periods={Z_MIN_PERIODS}).std(ddof=0)` "
        f"(matches `features.py:79-85`).\n"
        f"- Forward log return: `log(close[t+h] / close[t])`.\n"
        f"- Correlations: `scipy.stats.pearsonr` / `spearmanr`, NaN pairs dropped.\n"
        f"- Conditional effect: when |z| > {EXTREME_Z}, signed mean = "
        f"`sign(z) · fwd_return`; effect_z = signed_mean / SE.\n"
    )

    parts.append("\n## Correlation table (Pearson + Spearman)\n")
    parts.append(_md_table(corr))

    parts.append("\n## Conditional return effect (|z| > 2.0)\n")
    parts.append(_md_table(cond))

    parts.append("\n## Interaction with `gexoflow_z > 2.0`\n")
    parts.append(_md_table(inter))

    parts.append("\n## Per-feature verdicts\n")
    parts.append(
        f"Thresholds: SIGNAL = |Spearman| > {THRESH_SIGNAL} with p < {SIGNIFICANCE_P} at "
        f"any horizon; WEAK = |Spearman| > {THRESH_WEAK} but not clearing SIGNAL; "
        f"otherwise NOISE.\n"
    )
    parts.append("| feature | verdict | best cell |")
    parts.append("|---|---|---|")
    for f in NEW_FEATS:
        v, detail = verdict_for(f, corr)
        parts.append(f"| {f} | **{v}** | {detail} |")

    parts.append("\n## Caveats\n")
    parts.append(
        "- Vanna/charm are aggregated by `gex.resample()` as **state** columns "
        "(last value per bar) rather than as flows. The Z-score is therefore taken "
        "over a bar-end snapshot, not over a per-bar integrated quantity. A "
        "flow-style aggregation (1s deltas summed within a bar) would require a "
        "separate resample path and is out of scope here.\n"
        "- Intraday correlations of 0.05–0.10 are typical magnitudes for useful "
        "predictors; below 0.02 is noise. Treat the verdict thresholds accordingly.\n"
        "- 80-day window. Findings are exploratory; a multi-quarter sample would be "
        "needed before any production use.\n"
        "- Descriptive analysis only. No filter recommendations.\n"
    )
    return "\n".join(parts)


if __name__ == "__main__":
    main()
