"""Step 3 — OPRA skew skip. Bookmark spec for post-verdict pre-reg."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

DISCLOSURE = """\
This analysis is exploratory diagnostic work on a heavily consumed
corpus during an active forward test. It is NOT pre-registered.
Results CANNOT authorize any modification to locked OMEN config
or pre-reg.

The 504-trade all-bugfixes corpus has been examined many times
across multiple diagnostics. Project-wide false discovery rate is
high. Any positive finding here can only be honestly evaluated on
a future pre-registered forward window after OMEN-minus-SL verdict.
"""

BOOKMARK = """\
SKEW CONSISTENCY FILTER — POST-VERDICT PRE-REG CANDIDATE

Status: OPRA data on disk is 2-day slice only (Apr 22-23, 2026).
Insufficient for 146-session analysis. Test skipped.

Requires for future implementation:
  - Databento OPRA subscription (~$199/mo), OR
  - VIX term structure proxy (VIX vs VIX3M ratio, free)

Proposed spec for post-verdict pre-reg:
  For each OMEN signal, measure 25-delta skew direction over the
  30 minutes leading up to entry. Take trade only if skew direction
  is consistent with GEX z-sign:
    - GEX z > 0 (long signal):  put-skew falling OR call-skew rising
    - GEX z < 0 (short signal): put-skew rising OR call-skew falling

Bookmark for evaluation after OMEN-minus-SL forward verdict.
"""

OUT_MD = Path("/Users/rafanelson/Omen/diagnostics/vol-regime/03_skew_status.md")


def main() -> int:
    OUT_MD.parent.mkdir(parents=True, exist_ok=True)
    print("=" * 78)
    print("STEP 3 — Skew filter (SKIPPED — bookmark only)")
    print("=" * 78)
    print()
    print(BOOKMARK)

    L = []
    L.append("# Step 3 — skew consistency filter (SKIPPED, bookmark only)\n")
    L.append("Branch: `analysis/vol-regime-conditioning-throwaway` (throwaway).")
    L.append(f"Generated: {datetime.now().isoformat(timespec='seconds')}\n")
    L.append("## Disclosure\n")
    L.append("```")
    L.append(DISCLOSURE)
    L.append("```\n")
    L.append("## Bookmark for post-verdict pre-reg\n")
    L.append("```")
    L.append(BOOKMARK)
    L.append("```\n")
    OUT_MD.write_text("\n".join(L) + "\n")
    print(f"\nSaved: {OUT_MD}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
