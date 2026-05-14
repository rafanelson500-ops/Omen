"""Step 2 — day-of-week conditioning on 504 bugfixed trades."""
from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import (  # noqa: E402
    DISCLOSURE, OUT_DIR, SL_CELL, N_INSUFFICIENT,
    load_trades, group_stats, print_group_table, md_group_table,
)

OUT_MD = OUT_DIR / "02_day_of_week.md"
DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    print(DISCLOSURE)
    print("=" * 80)
    print("STEP 2 — Day-of-week conditioning (504 trades)")
    print("=" * 80)

    t = load_trades()
    counts = t["weekday_name"].value_counts().reindex(DAYS, fill_value=0)
    print(f"\nTrades: {len(t)} ({t['entry_date'].nunique()} sessions)")
    print("\nWeekday counts:")
    for d, n in counts.items():
        flag = "  ⚠ <30" if n < N_INSUFFICIENT else ""
        print(f"  {d:<10s}  n={n}{flag}")

    minus_sl = t[t["cell"] != SL_CELL]
    groups = {
        "A: All 504 trades":      t,
        "B: Monday":              t[t["weekday_name"] == "Monday"],
        "C: Tuesday":             t[t["weekday_name"] == "Tuesday"],
        "D: Wednesday":           t[t["weekday_name"] == "Wednesday"],
        "E: Thursday":            t[t["weekday_name"] == "Thursday"],
        "F: Friday":              t[t["weekday_name"] == "Friday"],
        "G: minus-SL ∩ Monday":   minus_sl[minus_sl["weekday_name"] == "Monday"],
        "H: minus-SL ∩ Friday":   minus_sl[minus_sl["weekday_name"] == "Friday"],
    }
    stats = [group_stats(g, lbl) for lbl, g in groups.items()]
    print_group_table(stats, "DAY-OF-WEEK COMPARISON")

    L = []
    L.append("# Step 2 — day-of-week conditioning (504 trades)\n")
    L.append("Branch: `analysis/calendar-conditioning-throwaway` (throwaway).")
    L.append(f"Generated: {datetime.now().isoformat(timespec='seconds')}\n")
    L.append("## Disclosure\n")
    L.append("```"); L.append(DISCLOSURE); L.append("```\n")
    L.append("## Weekday counts\n")
    L.append("| weekday | N | flag |")
    L.append("|---|---:|---|")
    for d, n in counts.items():
        flag = "⚠ N < 30" if n < N_INSUFFICIENT and n > 0 else ""
        L.append(f"| {d} | {n} | {flag} |")
    L.append("")
    L.append("## Group metrics\n")
    L.extend(md_group_table(stats))
    L.append("")
    OUT_MD.write_text("\n".join(L) + "\n")
    print(f"\nSaved: {OUT_MD}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
