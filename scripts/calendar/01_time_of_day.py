"""Step 1 — time-of-day conditioning on 504 bugfixed trades."""
from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import (  # noqa: E402
    DISCLOSURE, OUT_DIR, SL_CELL, N_INSUFFICIENT,
    load_trades, group_stats, fmt, fmt_pf,
    print_group_table, md_group_table,
)

OUT_MD = OUT_DIR / "01_time_of_day.md"


def _bucket(hour: int, minute: int) -> str:
    """LOCKED time buckets per spec."""
    mins = hour * 60 + minute
    if 9 * 60 + 30 <= mins < 11 * 60:
        return "MORNING"
    if 11 * 60 <= mins < 13 * 60:
        return "MIDDAY"
    if 13 * 60 <= mins < 15 * 60 + 30:
        return "AFTERNOON"
    if 15 * 60 + 30 <= mins < 15 * 60 + 55:
        return "LATE"
    return "OUT_OF_RANGE"


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    print(DISCLOSURE)
    print("=" * 80)
    print("STEP 1 — Time-of-day conditioning (504 trades)")
    print("=" * 80)

    t = load_trades()
    t["tod"] = [
        _bucket(h, m) for h, m in zip(t["entry_hour"], t["entry_minute"])
    ]

    print(f"\nTrades: {len(t)} ({t['entry_date'].nunique()} sessions)")
    print("\nBucket counts:")
    counts = t["tod"].value_counts().reindex(
        ["MORNING", "MIDDAY", "AFTERNOON", "LATE", "OUT_OF_RANGE"], fill_value=0
    )
    for b, n in counts.items():
        flag = "  ⚠ <30" if n < N_INSUFFICIENT else ""
        print(f"  {b:<14s}  n={n}{flag}")

    groups = {
        "A: All 504 trades":              t,
        "B: MORNING (09:30-11:00)":       t[t["tod"] == "MORNING"],
        "C: MIDDAY  (11:00-13:00)":       t[t["tod"] == "MIDDAY"],
        "D: AFTERNOON (13:00-15:30)":     t[t["tod"] == "AFTERNOON"],
        "E: LATE      (15:30-15:55)":     t[t["tod"] == "LATE"],
        "F: minus-SL ∩ MORNING":          t[(t["tod"] == "MORNING") & (t["cell"] != SL_CELL)],
        "G: minus-SL ∩ AFTERNOON":        t[(t["tod"] == "AFTERNOON") & (t["cell"] != SL_CELL)],
        "H: minus-SL ∩ LATE":             t[(t["tod"] == "LATE") & (t["cell"] != SL_CELL)],
    }
    stats = [group_stats(g, lbl) for lbl, g in groups.items()]
    print_group_table(stats, "TIME-OF-DAY COMPARISON")

    # Markdown
    L = []
    L.append("# Step 1 — time-of-day conditioning (504 trades)\n")
    L.append("Branch: `analysis/calendar-conditioning-throwaway` (throwaway).")
    L.append(f"Generated: {datetime.now().isoformat(timespec='seconds')}\n")
    L.append("## Disclosure\n")
    L.append("```")
    L.append(DISCLOSURE)
    L.append("```\n")
    L.append("## LOCKED time buckets\n")
    L.append("- **MORNING**:   09:30 ≤ entry < 11:00")
    L.append("- **MIDDAY**:    11:00 ≤ entry < 13:00 "
             "(effectively 11:00-12:00; 12:00-13:00 already blacked out by OMEN's lunch filter)")
    L.append("- **AFTERNOON**: 13:00 ≤ entry < 15:30")
    L.append("- **LATE**:      15:30 ≤ entry < 15:55")
    L.append("")
    L.append("## Bucket counts\n")
    L.append("| bucket | N | flag |")
    L.append("|---|---:|---|")
    for b, n in counts.items():
        flag = "⚠ N < 30" if n < N_INSUFFICIENT and n > 0 else ""
        L.append(f"| {b} | {n} | {flag} |")
    L.append("")
    L.append("## Group metrics\n")
    L.extend(md_group_table(stats))
    L.append("")
    OUT_MD.write_text("\n".join(L) + "\n")
    print(f"\nSaved: {OUT_MD}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
