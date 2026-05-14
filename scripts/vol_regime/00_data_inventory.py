"""Step 0 — data inventory for vol-regime conditioning analysis.

Read-only. No data pulls. Reports what's on disk and identifies the
target trade log. Stops here per spec; Step 1 only runs after user
confirms based on this inventory.

LOCKED CONSTRAINTS observed:
  - Read-only on cheese/, strategy.py, backtest.py, market.py, gex.py,
    features.py, and all pre-reg files.
  - Disclosure block at top of stdout AND in the markdown output.
"""
from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path

import pandas as pd

DISCLOSURE = """\
This analysis is exploratory diagnostic work on a consumed corpus
during an active forward test. It is NOT pre-registered. Results
CANNOT authorize any modification to locked OMEN config or pre-reg.

The OMEN trade outcomes on this 146-session corpus have been examined
many times across TRCB-v1, TRCB-v2 Q1-Q9 post-mortems, microprice
continuation, cell exclusion analysis, churn analysis (Steps 5/7),
and other diagnostics. The corpus is heavily consumed and the
project-wide false discovery rate is high.

Any positive finding here can only be honestly evaluated on a future
pre-registered forward window. This diagnostic adds candidate
filters to the post-verdict pre-reg bookmarks, nothing more.
"""

REPO = Path("/Users/rafanelson/Omen")
OUT_DIR = REPO / "diagnostics/vol-regime"
OUT_MD = OUT_DIR / "00_data_inventory.md"

# Locations to search for VIX / OPRA / regime data
VIX_SEARCH_GLOBS = [
    "backend/data/**/*vix*",
    "backend/data/**/*VIX*",
    "backend/data/regime/**",
    "backend/data/market/*vix*",
    "data/**/*vix*",
]
OPRA_SEARCH_GLOBS = [
    "backend/data/**/*opra*",
    "backend/data/**/*OPRA*",
    "backend/data/options/**",
    "backend/data/skew/**",
    "data/**/*opra*",
]
TRADE_LOG_CANDIDATES = [
    REPO / "diagnostics/all-bugfixes-baseline/is_all_bugfixes.csv",
    REPO / "diagnostics/all-bugfixes-baseline/oos_all_bugfixes.csv",
    REPO / "backend/data/analysis/locked_baseline_trades_blackout_lunch.csv",
    REPO / "backend/data/analysis/oos_baseline_trades_2025-09-08_2025-12-23.csv",
]
HOME_CACHES = [
    Path.home() / "Library/Caches/omen-pipeline-synthesis",
    Path.home() / "Library/Caches",
]


def _search(globs: list[str]) -> list[Path]:
    hits = []
    for g in globs:
        for p in REPO.glob(g):
            if p.is_file() and p.stat().st_size > 0:
                hits.append(p)
            elif p.is_dir():
                hits.append(p)
    # Also search home caches
    for cache_root in HOME_CACHES:
        if not cache_root.exists():
            continue
        for sub in cache_root.iterdir():
            name = sub.name.lower()
            for keyword in ("vix", "opra", "skew", "options"):
                if keyword in name:
                    hits.append(sub)
    return sorted(set(hits))


def _es_bars_inventory() -> dict:
    es_files = sorted((REPO / "backend/data/market").glob("ES_c_0_ohlcv1s_*.parquet"))
    es_info = []
    total_mb = 0.0
    for p in es_files:
        if p.is_symlink():
            es_info.append({"name": p.name, "symlink_to": os.readlink(p),
                             "size_mb": 0.0})
            continue
        size_mb = p.stat().st_size / (1024 * 1024)
        total_mb += size_mb
        es_info.append({"name": p.name, "symlink_to": None,
                         "size_mb": round(size_mb, 1)})
    return {"files": es_info, "total_mb": round(total_mb, 1)}


def _trade_log_inventory() -> dict:
    """Locate the all-bugfixes IS+OOS combined trade log used in OneMinL2
    Step 5/7 (~371 trades, 146 sessions). The two halves live in
    diagnostics/all-bugfixes-baseline/."""
    is_csv = REPO / "diagnostics/all-bugfixes-baseline/is_all_bugfixes.csv"
    oos_csv = REPO / "diagnostics/all-bugfixes-baseline/oos_all_bugfixes.csv"
    out = {"is_path": str(is_csv), "is_exists": is_csv.exists(),
            "oos_path": str(oos_csv), "oos_exists": oos_csv.exists()}
    if is_csv.exists():
        df = pd.read_csv(is_csv)
        df["entry_date"] = pd.to_datetime(df["entry_time"], utc=True).dt.date
        out["is_n_trades"] = int(len(df))
        out["is_n_sessions"] = int(df["entry_date"].nunique())
        out["is_first"] = str(df["entry_date"].min())
        out["is_last"] = str(df["entry_date"].max())
    if oos_csv.exists():
        df = pd.read_csv(oos_csv)
        df["entry_date"] = pd.to_datetime(df["entry_time"], utc=True).dt.date
        out["oos_n_trades"] = int(len(df))
        out["oos_n_sessions"] = int(df["entry_date"].nunique())
        out["oos_first"] = str(df["entry_date"].min())
        out["oos_last"] = str(df["entry_date"].max())
    return out


def _gex_inventory() -> dict:
    """Sanity-check GEX coverage on the IS+OOS date range."""
    gex_dir = REPO / "backend/data/gex"
    files = sorted(gex_dir.glob("*.parquet"))
    sessions_present = sorted(p.stem for p in files)
    return {
        "n_parquet": len(files),
        "earliest": sessions_present[0] if sessions_present else None,
        "latest": sessions_present[-1] if sessions_present else None,
        "n_missing_sentinels": len(list(gex_dir.glob("*.missing"))),
    }


def _read_atr_window_from_features() -> int | None:
    """Read (do NOT modify) features.py to extract the locked ATR window."""
    p = REPO / "backend/cheese/features.py"
    if not p.exists():
        return None
    src = p.read_text()
    # Look for the hardcoded rolling(14, ...) or any rolling(N, ... for atr
    import re
    m = re.search(r"rolling\(\s*(\d+)\s*,\s*min_periods", src)
    return int(m.group(1)) if m else None


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    print(DISCLOSURE)
    print("=" * 78)
    print("STEP 0 — Data inventory for vol-regime conditioning analysis")
    print("=" * 78)
    print()

    # 1. ES bars
    print("1) ES 1s bars (backend/data/market/)")
    es = _es_bars_inventory()
    for f in es["files"]:
        if f["symlink_to"]:
            print(f"   [SYMLINK] {f['name']}  →  {f['symlink_to']}")
        else:
            print(f"   [FILE   ] {f['name']:<55s}  {f['size_mb']:>6.1f}MB")
    print(f"   total file size (non-symlink): {es['total_mb']:.1f}MB")
    print()

    # 2. ATR window from features.py
    atr_window = _read_atr_window_from_features()
    print(f"   features.py hardcoded ATR window: {atr_window} bars "
          "(read-only; replicating below)")
    print()

    # 3. GEX inventory (informational; not required for ATR-only conditioning)
    print("2) GEX cache (backend/data/gex/) — sanity check")
    gex = _gex_inventory()
    print(f"   parquet files: {gex['n_parquet']}")
    print(f"   missing sentinels: {gex['n_missing_sentinels']}")
    print(f"   range: {gex['earliest']} → {gex['latest']}")
    print()

    # 4. VIX search
    print("3) VIX data search")
    vix_hits = _search(VIX_SEARCH_GLOBS)
    if vix_hits:
        for h in vix_hits:
            print(f"   FOUND: {h}")
    else:
        print("   NONE FOUND anywhere in repo or home caches.")
    print()

    # 5. OPRA / options skew search
    print("4) OPRA / options skew search")
    opra_hits = _search(OPRA_SEARCH_GLOBS)
    if opra_hits:
        for h in opra_hits:
            print(f"   FOUND: {h}")
    else:
        print("   NONE FOUND anywhere in repo or home caches.")
    print()

    # 6. Trade log inventory
    print("5) All-bugfixes IS+OOS combined trade log (target for analysis)")
    tl = _trade_log_inventory()
    print(f"   IS  path     : {tl['is_path']}")
    print(f"   IS  exists   : {tl['is_exists']}")
    if tl["is_exists"]:
        print(f"   IS  trades   : {tl['is_n_trades']} "
              f"({tl['is_n_sessions']} sessions, "
              f"{tl['is_first']} → {tl['is_last']})")
    print(f"   OOS path     : {tl['oos_path']}")
    print(f"   OOS exists   : {tl['oos_exists']}")
    if tl["oos_exists"]:
        print(f"   OOS trades   : {tl['oos_n_trades']} "
              f"({tl['oos_n_sessions']} sessions, "
              f"{tl['oos_first']} → {tl['oos_last']})")
    if tl.get("is_exists") and tl.get("oos_exists"):
        total_trades = tl["is_n_trades"] + tl["oos_n_trades"]
        total_sessions = tl["is_n_sessions"] + tl["oos_n_sessions"]
        print(f"   combined     : {total_trades} trades / {total_sessions} sessions")
    print()

    # ---- Write markdown ----
    L: list[str] = []
    L.append("# Step 0 — data inventory (vol-regime conditioning)\n")
    L.append("Branch: `analysis/vol-regime-conditioning-throwaway` "
             "(throwaway / archive only; never merges to main).")
    L.append(f"Generated: {datetime.now().isoformat(timespec='seconds')}\n")
    L.append("## Disclosure\n")
    L.append("```")
    L.append(DISCLOSURE)
    L.append("```\n")

    L.append("## 1. ES 1s bars (backend/data/market/)\n")
    L.append("| file | size (MB) | symlink → |")
    L.append("|---|---:|---|")
    for f in es["files"]:
        link = f["symlink_to"] or "—"
        L.append(f"| {f['name']} | {f['size_mb']:.1f} | {link} |")
    L.append(f"\nTotal non-symlink size: **{es['total_mb']:.1f} MB**.")
    L.append("")
    L.append(f"**ATR window** (read from `backend/cheese/features.py`, "
             f"line containing `rolling(N, min_periods=...)`): **{atr_window} bars**. "
             "This is the canonical OMEN ATR window we will replicate in Step 1; "
             "we will NOT modify `features.py`.")
    L.append("")

    L.append("## 2. GEX cache (sanity)\n")
    L.append(f"- parquet files: {gex['n_parquet']}")
    L.append(f"- missing sentinels: {gex['n_missing_sentinels']}")
    L.append(f"- range: {gex['earliest']} → {gex['latest']}")
    L.append("")
    is_2025_present = (gex['earliest'] or '').startswith('2025')
    if not is_2025_present:
        L.append("> ⚠ **Note**: no 2025 GEX parquets present. The Step 1 ATR analysis "
                 "does not depend on GEX (ATR is derived from ES bars only), so this "
                 "does not block Step 1. Flagged for your awareness — the OOS window "
                 "covers 2025-09-08 → 2025-12-23.")
        L.append("")

    L.append("## 3. VIX data\n")
    if vix_hits:
        L.append("| path |")
        L.append("|---|")
        for h in vix_hits:
            L.append(f"| {h} |")
    else:
        L.append("**No VIX parquet/CSV found** anywhere in repo, "
                 "`backend/data/`, or home caches.")
        L.append("")
        L.append("**Implication**: Step 2 (VIX conditioning) will be skipped unless "
                 "you authorize a Databento VIX pull (~$5 for the corpus).")
    L.append("")

    L.append("## 4. OPRA / options skew data\n")
    if opra_hits:
        L.append("| path |")
        L.append("|---|")
        for h in opra_hits:
            L.append(f"| {h} |")
    else:
        L.append("**No OPRA / options-chain / skew data found** anywhere in "
                 "repo, `backend/data/`, or home caches.")
        L.append("")
        L.append("**Implication**: Step 3 (skew consistency filter) will be skipped. "
                 "Per spec, the proposed forward-test spec for skew is:\n")
        L.append("> For each OMEN signal, measure 25-delta skew direction over the ")
        L.append("> 30 minutes leading up to entry. Take trade only if skew is moving ")
        L.append("> in direction consistent with GEX z-sign (skew up + GEX z positive, ")
        L.append("> or skew down + GEX z negative).")
        L.append("")
        L.append("This would require either a Databento OPRA subscription (~$199/mo) ")
        L.append("or a proxy (VIX vs VIX3M term structure ratio).")
    L.append("")

    L.append("## 5. Target trade log (IS + OOS combined, all-bugfixes)\n")
    L.append("| half | path | exists | trades | sessions | range |")
    L.append("|---|---|---|---:|---:|---|")
    L.append(f"| IS  | `{tl['is_path']}` | {tl['is_exists']} | "
             f"{tl.get('is_n_trades','—')} | {tl.get('is_n_sessions','—')} | "
             f"{tl.get('is_first','—')} → {tl.get('is_last','—')} |")
    L.append(f"| OOS | `{tl['oos_path']}` | {tl['oos_exists']} | "
             f"{tl.get('oos_n_trades','—')} | {tl.get('oos_n_sessions','—')} | "
             f"{tl.get('oos_first','—')} → {tl.get('oos_last','—')} |")
    if tl.get("is_exists") and tl.get("oos_exists"):
        L.append(f"\n**Combined**: {tl['is_n_trades'] + tl['oos_n_trades']} trades / "
                 f"{tl['is_n_sessions'] + tl['oos_n_sessions']} sessions.")
    L.append("")

    # Spec reference
    L.append("## 6. Spec reference vs observed\n")
    L.append("The prompt cites 371 trades / 146 sessions from OneMinL2 Step 5/7. "
             f"Observed: **{tl.get('is_n_trades', '?') + tl.get('oos_n_trades', 0)} "
             f"trades / {tl.get('is_n_sessions', 0) + tl.get('oos_n_sessions', 0)} "
             f"sessions** in the all-bugfixes IS+OOS combined log.")
    L.append("")
    L.append("If those numbers disagree (e.g. 371 ≠ observed), it likely means "
             "OneMinL2 Step 5/7 used a different subset (perhaps post-microprice-filter, "
             "or only evaluable trades). Flagging for confirmation before Step 1.")
    L.append("")

    L.append("## 7. Stop gate\n")
    L.append("Per spec, **STOP HERE**. Step 1 (ATR conditioning) runs only after "
             "you confirm based on this inventory.")
    L.append("")
    L.append("Available without further pulls:")
    L.append("- ✅ Step 1 (ATR conditioning) — ES bars are on disk, ATR computed from them.")
    if vix_hits:
        L.append("- ✅ Step 2 (VIX conditioning) — VIX data found.")
    else:
        L.append("- ❌ Step 2 (VIX conditioning) — VIX data NOT on disk; will be skipped.")
    if opra_hits:
        L.append("- ✅ Step 3 (skew filter) — OPRA data found; will require spec confirmation.")
    else:
        L.append("- ❌ Step 3 (skew filter) — OPRA data NOT on disk; will be skipped.")
    L.append("")

    OUT_MD.write_text("\n".join(L) + "\n")
    print(f"Saved: {OUT_MD}")
    print()
    print("=" * 78)
    print("STOPPED per spec — Step 1+ awaits your confirmation.")
    print("=" * 78)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
