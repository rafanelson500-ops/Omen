"""Build the SYNTHESIS.md report from the permutation-test outputs."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path("/Users/rafanelson/Omen")
ANALYSIS = REPO / "analysis/gex-permutation-bugfixed"

REAL_CSV = ANALYSIS / "perm_real.csv"
SIMPLE_CSV = ANALYSIS / "perm_dist_simple.csv"
BLOCK_CSV = ANALYSIS / "perm_dist_block.csv"
OUT_MD = ANALYSIS / "SYNTHESIS.md"

DISCLOSURE = """\
## DISCLOSURE — methodology re-run on consumed corpus

This re-runs the existing Tier 5.3 GEX permutation test on the 160-session
corpus using the bugfixed features.py and backtest.py (session-boundary
fix, time-stop off-by-one fix, trade overlap fix). The original Tier 5.3
result was p=0.14 on buggy code.

This is a methodology correction, not a new hypothesis. The corpus has
been used for multiple prior analyses. A p-value below 0.05 here would
indicate the GEX mechanism question becomes more answerable under correct
math, but cannot serve as standalone validation given the consumed-data
status.
"""


def main() -> int:
    real = pd.read_csv(REAL_CSV).iloc[0]
    simple = pd.read_csv(SIMPLE_CSV)
    block = pd.read_csv(BLOCK_CSV)

    real_sh = float(real["sharpe"])
    real_pf = float(real["profit_factor"])
    real_pnl = float(real["total_pnl"])
    real_n = int(real["n_trades"])

    def _block(perms: pd.DataFrame, real_sh, real_pf, real_pnl) -> dict:
        n = len(perms)
        sh = perms["sharpe"].values
        pf = perms["profit_factor"].values
        pnl = perms["total_pnl"].values
        return {
            "n": n,
            "p_sharpe": float(np.mean(sh >= real_sh)),
            "p_pf": float(np.mean(pf >= real_pf)),
            "p_pnl": float(np.mean(pnl >= real_pnl)),
            "sh_mean": float(sh.mean()), "sh_median": float(np.median(sh)),
            "sh_std": float(sh.std(ddof=1)),
            "sh_q05": float(np.percentile(sh, 5)),
            "sh_q25": float(np.percentile(sh, 25)),
            "sh_q75": float(np.percentile(sh, 75)),
            "sh_q95": float(np.percentile(sh, 95)),
            "sh_min": float(sh.min()), "sh_max": float(sh.max()),
            "pf_mean": float(pf.mean()), "pf_median": float(np.median(pf)),
            "pf_q95": float(np.percentile(pf, 95)),
            "pnl_mean": float(pnl.mean()), "pnl_median": float(np.median(pnl)),
            "n_above_real_sh": int(np.sum(sh >= real_sh)),
        }

    s = _block(simple, real_sh, real_pf, real_pnl)
    b = _block(block, real_sh, real_pf, real_pnl)

    L: list[str] = []
    L.append("# Tier 5.3 GEX permutation test — bugfixed re-run (THROWAWAY)\n")
    L.append("Branch: `analysis/gex-permutation-bugfixed-throwaway` "
             "(throwaway / archive only; never merges to main).")
    L.append(f"Generated: {datetime.now().isoformat(timespec='seconds')}\n")

    L.append("## 1. Disclosure\n")
    L.append(DISCLOSURE)
    L.append("")

    L.append("## 2. Original Tier 5.3 result (reference)\n")
    L.append("- Methodology: within-session row shuffle of GEX raw data, "
             "200 permutations, locked-baseline OMEN on Sep 8 → Dec 23 2025 OOS window.")
    L.append("- Original p-value (Sharpe): **p = 0.14** (cannot reject null at α=0.05).")
    L.append("- Code at the time contained the session-boundary bug, time-stop off-by-one, "
             "and exit/entry overlap bug. All three are now fixed on main.")
    L.append("")

    # Real
    L.append("## 3. Real bugfixed baseline (target)\n")
    L.append(f"- Window: 2025-09-08 → 2025-12-23 (same OOS window as the original test).")
    L.append(f"- Real trade count: **{real_n}** (bugfixed; previously 158).")
    L.append(f"- Real Sharpe (`sharpe_daily` from metrics.summarize): **{real_sh:+.4f}**")
    L.append(f"- Real profit factor: **{real_pf:+.4f}**")
    L.append(f"- Real total PnL: **${real_pnl:+,.2f}**")
    L.append("")
    L.append(f"Note: `sharpe_daily` is the daily-scale Sharpe produced by ")
    L.append(f"`metrics.summarize` (the same metric the original test used). It is ")
    L.append(f"NOT the same number as the annualized Sharpe (+0.51) cited elsewhere for the ")
    L.append(f"same OOS window. The annualized scaling differs; the p-value computation is ")
    L.append(f"valid because real and permuted distributions both use the same scale.")
    L.append("")

    L.append("## 4. Bugfixed simple-shuffle result\n")
    L.append("Methodology: shuffle GEX row order WITHIN each trading session "
             "(preserves daily totals, destroys within-session temporal structure). ")
    L.append("Same as the original Tier 5.3 method; only the underlying features.py + ")
    L.append("backtest.py code is now bugfixed.")
    L.append("")
    L.append(f"- N permutations: **{s['n']}**, seed = 42")
    L.append(f"- Permuted Sharpe distribution:")
    L.append(f"  - mean: {s['sh_mean']:+.4f}")
    L.append(f"  - median: {s['sh_median']:+.4f}")
    L.append(f"  - std: {s['sh_std']:+.4f}")
    L.append(f"  - quantiles: q05={s['sh_q05']:+.4f}  q25={s['sh_q25']:+.4f}  "
             f"q75={s['sh_q75']:+.4f}  q95={s['sh_q95']:+.4f}")
    L.append(f"  - range: [{s['sh_min']:+.4f}, {s['sh_max']:+.4f}]")
    L.append(f"- **Real Sharpe** ({real_sh:+.4f}) was beaten by **{s['n_above_real_sh']} / "
             f"{s['n']}** permuted Sharpes.")
    L.append(f"- **p-value (Sharpe): {s['p_sharpe']:.4f}**")
    L.append(f"- p-value (profit factor): {s['p_pf']:.4f}")
    L.append(f"- p-value (total PnL): {s['p_pnl']:.4f}")
    L.append("")

    L.append("## 5. Bugfixed block-permutation result\n")
    L.append("Methodology: divide the 76 trading sessions into non-overlapping blocks of 5 ")
    L.append("sessions; permute the block order; concatenate. Preserves within-session ")
    L.append("temporal order AND short-range (5-session) autocorrelation. More rigorous for ")
    L.append("financial time series.")
    L.append("")
    L.append(f"- N permutations: **{b['n']}**, block size = 5 sessions, seed = 42")
    L.append(f"- Permuted Sharpe distribution:")
    L.append(f"  - mean: {b['sh_mean']:+.4f}")
    L.append(f"  - median: {b['sh_median']:+.4f}")
    L.append(f"  - std: {b['sh_std']:+.4f}")
    L.append(f"  - quantiles: q05={b['sh_q05']:+.4f}  q25={b['sh_q25']:+.4f}  "
             f"q75={b['sh_q75']:+.4f}  q95={b['sh_q95']:+.4f}")
    L.append(f"  - range: [{b['sh_min']:+.4f}, {b['sh_max']:+.4f}]")
    L.append(f"- **Real Sharpe** ({real_sh:+.4f}) was beaten by **{b['n_above_real_sh']} / "
             f"{b['n']}** permuted Sharpes.")
    L.append(f"- **p-value (Sharpe): {b['p_sharpe']:.4f}**")
    L.append(f"- p-value (profit factor): {b['p_pf']:.4f}")
    L.append(f"- p-value (total PnL): {b['p_pnl']:.4f}")
    L.append("")

    L.append("## 6. Comparison table\n")
    L.append("| methodology | N perms | p (Sharpe) | p (PF) | p (PnL) | reading |")
    L.append("|---|---:|---:|---:|---:|---|")
    L.append(f"| Original Tier 5.3 (buggy code) | 200 | 0.14 | — | — | cannot reject null |")

    def _verdict(p):
        if p < 0.05:
            return "REJECT null at α=0.05 — GEX timing is informative"
        if p < 0.10:
            return "weak evidence against null (0.05 ≤ p < 0.10)"
        if p < 0.20:
            return "cannot reject null"
        return "no evidence against null"

    L.append(f"| Bugfixed simple shuffle | {s['n']} | **{s['p_sharpe']:.4f}** | "
             f"{s['p_pf']:.4f} | {s['p_pnl']:.4f} | {_verdict(s['p_sharpe'])} |")
    L.append(f"| Bugfixed block permutation (5-session) | {b['n']} | "
             f"**{b['p_sharpe']:.4f}** | {b['p_pf']:.4f} | "
             f"{b['p_pnl']:.4f} | {_verdict(b['p_sharpe'])} |")
    L.append("")

    L.append("## 7. Honest interpretation\n")
    # Diff vs original
    orig_p = 0.14
    s_diff = s['p_sharpe'] - orig_p
    b_diff = b['p_sharpe'] - orig_p
    L.append(f"- **Simple-shuffle p-value moved from 0.14 (buggy) to {s['p_sharpe']:.4f} "
             f"(bugfixed)** — change of {s_diff:+.4f}.")
    L.append(f"- **Block-permutation p-value: {b['p_sharpe']:.4f}** "
             f"(no prior comparison; this methodology not run on buggy code).")
    L.append("")
    if s['p_sharpe'] < 0.05:
        L.append("Under the bugfixed simple-shuffle methodology, the test now **rejects the "
                 "null** that GEX temporal structure is uninformative. The original p=0.14 ")
        L.append("appears to have been an artifact of the session-boundary feature bug "
                 "suppressing the test's ability to detect signal: when features.py was ")
        L.append("blending overnight tails into intraday z-scores, the permuted distribution ")
        L.append("had artificially-similar properties to the real distribution.")
    elif s['p_sharpe'] < 0.10:
        L.append("Under the bugfixed simple-shuffle methodology, the test shows **weak ")
        L.append("evidence against the null** (0.05 ≤ p < 0.10). Suggestive but not "
                 "definitive at the conventional α=0.05 level.")
    elif s['p_sharpe'] < 0.20:
        L.append("Under the bugfixed simple-shuffle methodology, the test still **cannot ")
        L.append("reject the null** at α=0.05. The bug fix did not materially change the ")
        L.append("interpretation of the original Tier 5.3 result.")
    else:
        L.append("Under the bugfixed simple-shuffle methodology, the test shows **even less ")
        L.append("evidence against the null** than the buggy version. The original p=0.14 was ")
        L.append("if anything understating the difficulty of detecting GEX signal.")
    L.append("")
    if abs(s['p_sharpe'] - b['p_sharpe']) > 0.10:
        if b['p_sharpe'] > s['p_sharpe']:
            L.append("The block-permutation p-value is **substantially higher** than simple-shuffle. ")
            L.append("This is the expected direction: block permutation preserves short-range ")
            L.append("autocorrelation, so the null distribution captures more of the natural ")
            L.append("variation in market state. Real performance has to clear a higher bar to ")
            L.append("look exceptional. The simple-shuffle result over-rejects by destroying ")
            L.append("structure the GEX-removed null shouldn't have.")
        else:
            L.append("The block-permutation p-value is substantially LOWER than simple-shuffle. ")
            L.append("Unusual direction — preserving local structure made the test more powerful. ")
            L.append("Investigate before drawing conclusions.")
    else:
        L.append("Simple-shuffle and block-permutation p-values are close (Δ = "
                 f"{abs(s['p_sharpe']-b['p_sharpe']):.3f}). Time-series autocorrelation is not ")
        L.append("doing meaningful work in the test on this data. Both methodologies tell the ")
        L.append("same story.")
    L.append("")

    L.append("## 8. Implications for the OMEN-minus-SL forward test (pre-reg `9c1c22f`)\n")
    L.append("**Pre-reg is unchanged regardless of this result.** The pre-registered forward ")
    L.append("test is about trading edge, not mechanism interpretation. Both arms remain locked:")
    L.append("")
    L.append("- Hypothesis 1 (OMEN-minus-SL): PASS gate Sharpe ≥ 1.20 + minus-SL ≥ full + 0.50")
    L.append("- Hypothesis 2 (LS-only): PASS gate Sharpe ≥ 1.00 on minimum 30 LS trades")
    L.append("")
    L.append("This Q-suffix diagnostic affects only the interpretive frame around the forward ")
    L.append("test:")
    if s['p_sharpe'] < 0.05 or b['p_sharpe'] < 0.05:
        L.append("- The mechanism story for the forward test is **stronger** under bugfixed math. ")
        L.append("  GEX appears informative; a positive forward-test result would be consistent ")
        L.append("  with the stated mechanism.")
    else:
        L.append("- The mechanism question remains uncertain even under bugfixed math. ")
        L.append("  Forward test still informs trading edge regardless — the deployment-")
        L.append("  relevant quantity does not require the mechanism question to be resolved.")
    L.append("")

    L.append("## 9. Caveats\n")
    L.append("- Consumed-corpus analysis. The 76-session OOS window has been used for many ")
    L.append("  prior analyses.")
    L.append("- p-values from a single permutation test can vary modestly with the random ")
    L.append("  seed (small Monte Carlo error). N=500 keeps the standard error on p around ")
    L.append("  ±0.022.")
    L.append("- This does not constitute new validation; only a methodological correction of ")
    L.append("  an existing test.")
    L.append("- Block size = 5 sessions is the default per the prompt. A different block size ")
    L.append("  could give a different p-value; this is not a knob to be tuned post-hoc.")
    L.append("- The bugfixed real Sharpe is computed on the same 247-trade bugfixed OOS log ")
    L.append("  used as the locked baseline elsewhere. Permuted runs use the same Sharpe ")
    L.append("  metric (`sharpe_daily`), so the p-value comparison is internally consistent.")
    return OUT_MD.write_text("\n".join(L) + "\n") or 0


if __name__ == "__main__":
    raise SystemExit(main())
