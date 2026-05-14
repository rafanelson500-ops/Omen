"""Step 4 — single LOCKED interaction: OMEN-minus-SL ∩ OPEX-week ∩ LATE."""
from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import (  # noqa: E402
    DISCLOSURE, OUT_DIR, SL_CELL, N_INSUFFICIENT,
    load_trades, group_stats, print_group_table, md_group_table,
    is_opex_week,
)

OUT_MD = OUT_DIR / "04_interaction.md"


def _is_late(hour: int, minute: int) -> bool:
    mins = hour * 60 + minute
    return 15 * 60 + 30 <= mins < 15 * 60 + 55


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    print(DISCLOSURE)
    print("=" * 80)
    print("STEP 4 — Interaction: minus-SL × OPEX × LATE")
    print("=" * 80)

    t = load_trades()
    t["is_opex_week"] = t["entry_date"].apply(is_opex_week)
    t["is_late"] = [_is_late(h, m) for h, m in zip(t["entry_hour"], t["entry_minute"])]

    minus_sl = t[t["cell"] != SL_CELL]
    minus_sl_late = minus_sl[minus_sl["is_late"]]
    groups = {
        "A: minus-SL ∩ OPEX week ∩ LATE":     minus_sl_late[minus_sl_late["is_opex_week"]],
        "B: minus-SL ∩ non-OPEX ∩ LATE":      minus_sl_late[~minus_sl_late["is_opex_week"]],
    }
    stats = [group_stats(g, lbl) for lbl, g in groups.items()]
    print_group_table(stats, "OPEX × LATE INTERACTION (minus-SL only)")

    L = []
    L.append("# Step 4 — interaction: minus-SL × OPEX × LATE (single locked test)\n")
    L.append("Branch: `analysis/calendar-conditioning-throwaway` (throwaway).")
    L.append(f"Generated: {datetime.now().isoformat(timespec='seconds')}\n")
    L.append("## Disclosure\n")
    L.append("```"); L.append(DISCLOSURE); L.append("```\n")
    L.append("## Locked spec\n")
    L.append("- Single interaction test. No other interactions explored.")
    L.append("- Cell exclusion: SHORT_long removed.")
    L.append("- LATE bucket: 15:30 ≤ entry < 15:55 (matches Step 1 definition).")
    L.append("- OPEX week: Mon-Fri containing the third Friday of the month "
             "(matches Step 3 definition).")
    L.append("")
    L.append("## Group metrics\n")
    L.extend(md_group_table(stats))
    L.append("")
    # Insufficient-sample flagging
    insufficient = [s for s in stats if 0 < s["n"] < N_INSUFFICIENT]
    if insufficient:
        L.append("## ⚠ Insufficient samples\n")
        for s in insufficient:
            L.append(f"- **{s['label']}** has N = {s['n']} (< 30). Treat as suggestive only.")
        L.append("")
    OUT_MD.write_text("\n".join(L) + "\n")
    print(f"\nSaved: {OUT_MD}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
