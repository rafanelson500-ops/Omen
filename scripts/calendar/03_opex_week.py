"""Step 3 — OPEX-week conditioning on 504 bugfixed trades."""
from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import (  # noqa: E402
    DISCLOSURE, OUT_DIR, SL_CELL, N_INSUFFICIENT,
    load_trades, group_stats, print_group_table, md_group_table,
    third_friday, opex_week_dates, is_opex_week,
)

OUT_MD = OUT_DIR / "03_opex_week.md"


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    print(DISCLOSURE)
    print("=" * 80)
    print("STEP 3 — OPEX-week conditioning (504 trades)")
    print("=" * 80)

    t = load_trades()
    t["is_opex_week"] = t["entry_date"].apply(is_opex_week)
    n_opex = int(t["is_opex_week"].sum())
    n_non = len(t) - n_opex
    pct_opex = 100.0 * n_opex / len(t)
    print(f"\nTrades: {len(t)} ({t['entry_date'].nunique()} sessions)")
    print(f"\nOPEX-week trades : {n_opex} ({pct_opex:.1f}%)")
    print(f"Non-OPEX trades  : {n_non} ({100 - pct_opex:.1f}%)")
    print(f"  expected ~25% in OPEX weeks if uniform; observed {pct_opex:.1f}%.")

    # OPEX dates covered
    opex_sessions_in_trades = sorted(set(d for d in t["entry_date"].unique()
                                           if is_opex_week(d)))
    print(f"\nUnique OPEX trade-dates: {len(opex_sessions_in_trades)}")
    third_fridays = sorted({third_friday(d.year, d.month)
                              for d in t["entry_date"].unique()})
    print(f"Third Fridays in range: {len(third_fridays)} "
          f"(from {third_fridays[0]} to {third_fridays[-1]})")

    minus_sl = t[t["cell"] != SL_CELL]
    groups = {
        "A: All 504 trades":                t,
        "B: OPEX week trades":              t[t["is_opex_week"]],
        "C: Non-OPEX week trades":          t[~t["is_opex_week"]],
        "D: minus-SL ∩ OPEX week":          minus_sl[minus_sl["is_opex_week"]],
    }
    stats = [group_stats(g, lbl) for lbl, g in groups.items()]
    print_group_table(stats, "OPEX-WEEK COMPARISON")

    L = []
    L.append("# Step 3 — OPEX-week conditioning (504 trades)\n")
    L.append("Branch: `analysis/calendar-conditioning-throwaway` (throwaway).")
    L.append(f"Generated: {datetime.now().isoformat(timespec='seconds')}\n")
    L.append("## Disclosure\n")
    L.append("```"); L.append(DISCLOSURE); L.append("```\n")
    L.append("## OPEX-week definition\n")
    L.append("- **OPEX week** = the Monday-Friday calendar week containing the ")
    L.append("  third Friday of each calendar month.")
    L.append("- Computed programmatically: first day of month → add days to first ")
    L.append("  Friday → add 14 days = third Friday → Monday of that week is "
             "third_friday − 4 days.")
    L.append("- A trade is `is_opex_week=True` iff its session date is one of the ")
    L.append("  5 weekdays (Mon-Fri) of that OPEX week.")
    L.append("")
    L.append("## Coverage\n")
    L.append(f"- OPEX-week trades    : **{n_opex}** ({pct_opex:.1f}%)")
    L.append(f"- Non-OPEX trades     : **{n_non}** ({100 - pct_opex:.1f}%)")
    L.append(f"- Unique OPEX dates with trades: **{len(opex_sessions_in_trades)}**")
    L.append(f"- Third Fridays in trade range : **{len(third_fridays)}** "
             f"({third_fridays[0]} → {third_fridays[-1]})")
    if abs(pct_opex - 25) > 10:
        L.append("")
        L.append("⚠ Observed OPEX share deviates >10pp from the ~25% uniform expectation; "
                 "flagged for awareness (corpus may have uneven OPEX-week coverage).")
    L.append("")
    L.append("## Group metrics\n")
    L.extend(md_group_table(stats))
    L.append("")
    OUT_MD.write_text("\n".join(L) + "\n")
    print(f"\nSaved: {OUT_MD}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
