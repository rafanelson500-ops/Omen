"""Deflated Sharpe Ratio (DSR) for the locked Flow Burst baseline.

Reference: Bailey & Lopez de Prado (2014) "The Deflated Sharpe Ratio:
Correcting for Selection Bias, Backtest Overfitting and Non-Normality",
SSRN 2460551.

Reads:
    backend/data/analysis/locked_baseline_trades_blackout_lunch.csv
Writes:
    backend/diagnostics/dsr/REPORT.md

Per-trade returns are taken from `net_dollars` (P&L net of commission;
slippage already baked into entry_px / exit_px by backtest.py).
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import kurtosis, norm, skew

BACKEND = Path("/Users/rafanelson/Omen/backend")
INPUT_CSV = BACKEND / "data" / "analysis" / "locked_baseline_trades_blackout_lunch.csv"
OUTPUT_DIR = BACKEND / "diagnostics" / "dsr"
OUTPUT_MD = OUTPUT_DIR / "REPORT.md"

T_TRADES = 174
N_SESSIONS = 80
TRIALS_DEFAULT = 20
TRIALS_SENSITIVITY = (10, 15, 20, 30, 50)

GAMMA_EM = 0.5772156649015329
E = math.e


# ============================================================================
#                          STATISTICS — building blocks
# ============================================================================

def per_trade_sharpe(net: np.ndarray) -> float:
    """SR_hat = mean(x) / std(x), sample std with ddof=1 (unbiased).

    Per-trade (NOT annualized). Used directly in PSR / DSR formulas.
    """
    return float(np.mean(net) / np.std(net, ddof=1))


def annualization_factor(n_trades: int, n_sessions: int, days_per_year: int = 252) -> float:
    """sqrt(days_per_year * trades_per_day) — used only for the headline number."""
    trades_per_day = n_trades / n_sessions
    return math.sqrt(days_per_year * trades_per_day)


# ============================================================================
#                                    PSR
# ============================================================================
# Bailey & Lopez de Prado, canonical form (Mertens 2002 / B&LdP 2014):
#
#     PSR(SR*) = Φ[ (SR_hat - SR*) · sqrt(T-1)
#                  / sqrt(1 - γ_3·SR_hat + ((γ_4_pearson - 1)/4)·SR_hat²) ]
#
# γ_3 is sample skewness; γ_4_pearson is Pearson (non-excess) kurtosis = 3
# for a normal distribution. Substituting γ_4_pearson = γ_4_excess + 3 in
# the kurtosis term gives ((γ_4_excess + 2)/4) — what we use below, since
# scipy.stats.kurtosis(fisher=True) returns the excess form.
#
# Sanity check: for a normal sample (skew=0, excess_kurt=0), the kurtosis
# coefficient is (0+2)/4 = 0.5 ⇒ Var_SR = (1 + 0.5·SR²)/(T-1), the
# well-known asymptotic SR variance under normality.

def psr(sr_hat: float, sr_star: float, T: int, skew_hat: float, kurt_hat: float) -> float:
    """PSR — canonical B&LdP. `kurt_hat` is excess kurtosis (Fisher)."""
    denom_sq = 1.0 - skew_hat * sr_hat + ((kurt_hat + 2.0) / 4.0) * (sr_hat ** 2)
    if denom_sq <= 0:
        raise ValueError(
            f"PSR denominator non-positive: 1 - skew*SR + (kurt_excess+2)/4 * SR^2 = "
            f"{denom_sq:.6f}; formula domain error"
        )
    z = (sr_hat - sr_star) * math.sqrt(T - 1) / math.sqrt(denom_sq)
    return float(norm.cdf(z))


# ============================================================================
#                            DSR — SR_0 + DSR
# ============================================================================

def var_sr(sr_hat: float, T: int, skew_hat: float, kurt_hat: float) -> float:
    """Variance of the SR estimator under the null — canonical B&LdP:

        Var_SR = (1 - skew·SR_hat + ((kurt_excess + 2)/4)·SR_hat²) / (T - 1)

    Same kurtosis term as the PSR denominator (PSR ≡ Φ((SR−SR*)/√Var_SR)).
    """
    numer = 1.0 - skew_hat * sr_hat + ((kurt_hat + 2.0) / 4.0) * (sr_hat ** 2)
    if numer <= 0:
        raise ValueError(
            f"Var_SR numerator non-positive: 1 - skew*SR + (kurt_excess+2)/4 * SR^2 = "
            f"{numer:.6f}; formula domain error"
        )
    return numer / (T - 1)


def expected_max_sr(var_sr_value: float, N: int) -> float:
    """E[max SR_n] under N independent iid trials, B&LdP eq. (4):

        SR_0 = sqrt(Var_SR) * [(1 - γ_em) * Φ⁻¹(1 - 1/N)
                                + γ_em * Φ⁻¹(1 - 1/(N·e))]
    """
    if N < 2:
        raise ValueError(f"N must be >= 2 (got {N}) — Φ⁻¹(1 - 1/N) undefined for N=1")
    sigma = math.sqrt(var_sr_value)
    z1 = norm.ppf(1.0 - 1.0 / N)
    z2 = norm.ppf(1.0 - 1.0 / (N * E))
    return float(sigma * ((1.0 - GAMMA_EM) * z1 + GAMMA_EM * z2))


def dsr(sr_hat: float, T: int, skew_hat: float, kurt_hat: float, N: int) -> tuple[float, float]:
    """Returns (SR_0, DSR). DSR = PSR(SR_0)."""
    v = var_sr(sr_hat, T, skew_hat, kurt_hat)
    sr0 = expected_max_sr(v, N)
    return sr0, psr(sr_hat, sr0, T, skew_hat, kurt_hat)


# ============================================================================
#                              Reporting helpers
# ============================================================================

def verdict(dsr_value: float) -> str:
    if dsr_value > 0.95:
        return "REAL EDGE"
    if dsr_value < 0.50:
        return "LIKELY OVERFIT"
    return "INCONCLUSIVE"


def format_pct(p: float) -> str:
    return f"{p * 100:.2f}%"


# ============================================================================
#                                   main
# ============================================================================

def main() -> None:
    df = pd.read_csv(INPUT_CSV)
    if len(df) != T_TRADES:
        print(f"WARNING: expected {T_TRADES} rows, got {len(df)}")
    net = df["net_dollars"].to_numpy(dtype=float)

    # --- statistics
    mean_pnl = float(np.mean(net))
    std_pnl = float(np.std(net, ddof=1))
    skew_hat = float(skew(net, bias=False))                 # unbiased
    kurt_hat = float(kurtosis(net, fisher=True, bias=False))  # excess, unbiased
    sr_hat = mean_pnl / std_pnl                             # per-trade
    ann_factor = annualization_factor(T_TRADES, N_SESSIONS)
    sr_ann = sr_hat * ann_factor

    # --- PSR vs zero
    psr_zero = psr(sr_hat, sr_star=0.0, T=T_TRADES,
                   skew_hat=skew_hat, kurt_hat=kurt_hat)

    # --- DSR sensitivity
    dsr_table: list[tuple[int, float, float, str]] = []
    for N in TRIALS_SENSITIVITY:
        sr0, dsr_val = dsr(sr_hat, T_TRADES, skew_hat, kurt_hat, N)
        dsr_table.append((N, sr0, dsr_val, verdict(dsr_val)))
    sr0_default, dsr_default, verdict_default = next(
        (sr0, d, v) for n, sr0, d, v in dsr_table if n == TRIALS_DEFAULT
    )

    # --- terminal
    print("=== DEFLATED SHARPE RATIO ANALYSIS ===")
    print(f"Input: {T_TRADES} trades, {N_SESSIONS} sessions, Dec 2025 - Apr 2026\n")
    print("Return Statistics:")
    print(f"  Mean trade P&L:        ${mean_pnl:,.2f}")
    print(f"  Std trade P&L:         ${std_pnl:,.2f}")
    print(f"  Skewness:              {skew_hat:+.4f} (positive = right skew = good)")
    print(f"  Excess kurtosis:       {kurt_hat:+.4f} (positive = fat tails)\n")
    print("Sharpe Ratios:")
    print(f"  Per-trade Sharpe:      {sr_hat:.4f}")
    print(f"  Annualized Sharpe:     {sr_ann:.4f} "
          f"(annualization factor = sqrt(252 * {T_TRADES/N_SESSIONS:.4f}) = {ann_factor:.4f})\n")
    print(f"PSR vs zero (T={T_TRADES}):     {format_pct(psr_zero)} confidence SR > 0\n")
    print(f"DSR Analysis (N={TRIALS_DEFAULT} trials):")
    print(f"  SR_0 (null threshold): {sr0_default:.4f}")
    print(f"  DSR:                   {format_pct(dsr_default)} confidence SR > SR_0")
    print(f"  Verdict:               {verdict_default}")
    print("  (REAL EDGE if DSR > 95%, INCONCLUSIVE if 50-95%, LIKELY OVERFIT if <50%)\n")
    print("Sensitivity to N assumption:")
    for n, sr0, d, v in dsr_table:
        print(f"  N={n:>3d}: SR_0={sr0:.4f}  DSR = {format_pct(d)}  Verdict: {v}")

    # --- markdown report
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    md = _build_report(
        mean_pnl=mean_pnl, std_pnl=std_pnl, skew_hat=skew_hat, kurt_hat=kurt_hat,
        sr_hat=sr_hat, sr_ann=sr_ann, ann_factor=ann_factor,
        psr_zero=psr_zero, dsr_table=dsr_table,
    )
    OUTPUT_MD.write_text(md)
    print(f"\nReport: {OUTPUT_MD}")


def _build_report(*, mean_pnl, std_pnl, skew_hat, kurt_hat,
                  sr_hat, sr_ann, ann_factor, psr_zero, dsr_table) -> str:
    lines = []
    lines.append("# Deflated Sharpe Ratio — Flow Burst locked baseline\n")

    # Plain-English summary (filled in numerically below in code, not template)
    default_row = next(r for r in dsr_table if r[0] == TRIALS_DEFAULT)
    _, sr0_d, dsr_d, verdict_d = default_row
    lines.append("## Summary\n")
    lines.append(
        f"On 174 trades over 80 sessions (Dec 2025 – Apr 2026), the locked "
        f"Flow Burst baseline produces a per-trade Sharpe of {sr_hat:.4f} "
        f"(annualized {sr_ann:.4f} at a factor of √(252 × 174/80) = {ann_factor:.4f}). "
        f"The Probabilistic Sharpe Ratio against a zero benchmark is {format_pct(psr_zero)}. "
        f"After deflation for selection bias under N={TRIALS_DEFAULT} trials and "
        f"non-normality of returns, the Deflated Sharpe Ratio is "
        f"{format_pct(dsr_d)} (verdict: **{verdict_d}**). The N-sensitivity table "
        f"below shows how the verdict moves as the trial count assumption changes.\n"
    )

    lines.append("## Inputs\n")
    lines.append(f"- Source: `data/analysis/locked_baseline_trades_blackout_lunch.csv`")
    lines.append(f"- Trades: {T_TRADES}")
    lines.append(f"- Sessions: {N_SESSIONS}")
    lines.append(f"- Trades/day: {T_TRADES/N_SESSIONS:.4f}")
    lines.append(f"- Mean per-trade P&L: ${mean_pnl:,.4f}")
    lines.append(f"- Std per-trade P&L (ddof=1): ${std_pnl:,.4f}")
    lines.append(f"- Skewness (`scipy.stats.skew`, bias=False): {skew_hat:+.6f}")
    lines.append(f"- Excess kurtosis (`scipy.stats.kurtosis(fisher=True, bias=False)`): {kurt_hat:+.6f}\n")

    lines.append("## Sharpe ratios\n")
    lines.append(f"- Per-trade SR (used in PSR/DSR): **{sr_hat:.6f}**")
    lines.append(f"- Annualization factor √(252 · {T_TRADES/N_SESSIONS:.4f}) = **{ann_factor:.6f}**")
    lines.append(f"- Annualized SR (headline only): **{sr_ann:.6f}**\n")

    lines.append("## PSR vs zero\n")
    lines.append(f"- PSR(SR* = 0, T = {T_TRADES}) = **{format_pct(psr_zero)}**\n")

    lines.append("## DSR sensitivity to N (independent trials)\n")
    lines.append("| N | SR_0 | DSR | Verdict |")
    lines.append("|---:|---:|---:|---|")
    for n, sr0, d, v in dsr_table:
        lines.append(f"| {n} | {sr0:.6f} | {format_pct(d)} | {v} |")
    lines.append("")

    lines.append("## Formulas\n")
    lines.append("Canonical Bailey & Lopez de Prado (2014). All sample stats use "
                 "`scipy.stats.skew(bias=False)` and "
                 "`scipy.stats.kurtosis(fisher=True, bias=False)` (excess kurtosis).\n")
    lines.append(
        "**Probabilistic Sharpe Ratio:**  \n"
        "$$\\mathrm{PSR}(SR^\\*) = \\Phi\\!\\left[\\frac{(\\hat{SR} - SR^\\*)\\sqrt{T-1}}"
        "{\\sqrt{1 - \\hat{\\gamma}_3\\,\\hat{SR} + \\frac{\\hat{\\gamma}_4 + 2}{4}\\,\\hat{SR}^2}}\\right]$$\n"
    )
    lines.append(
        "**Variance of SR estimator:**  \n"
        "$$\\widehat{\\mathrm{Var}}(\\hat{SR}) = \\frac{1 - \\hat{\\gamma}_3\\,\\hat{SR} + "
        "\\frac{\\hat{\\gamma}_4 + 2}{4}\\,\\hat{SR}^2}{T - 1}$$\n"
    )
    lines.append(
        "**Expected max SR under N i.i.d. trials (Gumbel approximation):**  \n"
        "$$SR_0 = \\sqrt{\\widehat{\\mathrm{Var}}(\\hat{SR})}\\cdot\\left[(1-\\gamma_{em})\\Phi^{-1}\\!\\left(1-\\tfrac{1}{N}\\right) + "
        "\\gamma_{em}\\Phi^{-1}\\!\\left(1-\\tfrac{1}{N\\,e}\\right)\\right]$$\n"
    )
    lines.append("**Deflated Sharpe Ratio:** $\\mathrm{DSR} = \\mathrm{PSR}(SR_0)$.\n")
    lines.append("Note: $\\hat{\\gamma}_4$ is *excess* kurtosis (Fisher). The canonical B&LdP "
                 "form is written with Pearson kurtosis γ₄ via "
                 "`((γ₄ - 1)/4)`; substituting γ₄ = excess + 3 yields `((excess + 2)/4)`. "
                 "For a normal sample (skew=0, excess=0) this evaluates to 0.5, matching "
                 "Mertens (2002).\n")

    lines.append("## Verdict bands\n")
    lines.append("- DSR > 95%: REAL EDGE")
    lines.append("- 50% ≤ DSR ≤ 95%: INCONCLUSIVE")
    lines.append("- DSR < 50%: LIKELY OVERFIT\n")

    return "\n".join(lines)


if __name__ == "__main__":
    main()
