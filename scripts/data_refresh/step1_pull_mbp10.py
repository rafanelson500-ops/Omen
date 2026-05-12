"""Step 1 — pull MBP-10 for the 9 forward-gap trading days, one day at a time.

Pulls via Databento `timeseries.get_range` with stype_in='continuous',
symbols=['ES.c.0'], schema='mbp-10', RTH window (DST-aware via zoneinfo).
Validates schema column-by-column against the existing 2026-04-28 cache
file BEFORE writing each new day. Writes:
  <cache>/front_month_<YYYY-MM-DD>.parquet
  <cache>/front_month_<YYYY-MM-DD>.meta.json

Mirrors the convention used to produce the 2026-04-27 and 2026-04-28
cache files (symbol='ES.c.0', instrument_id=42140864 = ESM6 front-month).

Hard rules (user pre-flight constraints):
  - Never overwrite an existing file. Skip if cache already present.
  - Estimate cost first, print, request user confirmation if total > $10.
    (For mbp-10 RTH one day ~ a few cents; nine days well under threshold.)
  - Stop on any API error or empty response; do not retry silently.
  - Process one day at a time; print progress after each.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import sys
from pathlib import Path
from zoneinfo import ZoneInfo

import databento as db
import pandas as pd

# ----- Paths & constants ----------------------------------------------------
CACHE_DIR = Path("/Users/rafanelson/Library/Caches/omen-pipeline-synthesis/mbp10_cache")
ENV_PATH = Path("/Users/rafanelson/Omen/backend/.env")
REFERENCE_PARQUET = CACHE_DIR / "front_month_2026-04-28.parquet"

DATASET = "GLBX.MDP3"
SYMBOL = "ES.c.0"
STYPE_IN = "continuous"
SCHEMA = "mbp-10"

ET = ZoneInfo("America/New_York")
UTC = ZoneInfo("UTC")

# RTH window (DST-aware)
RTH_OPEN_HM = (9, 30)
RTH_CLOSE_HM = (16, 0)

# Step 1 scope — 9 confirmed-available days. May 12 deferred (API processing lag).
TARGET_DATES = [
    dt.date(2026, 4, 29),
    dt.date(2026, 4, 30),
    dt.date(2026, 5, 1),
    dt.date(2026, 5, 4),
    dt.date(2026, 5, 5),
    dt.date(2026, 5, 6),
    dt.date(2026, 5, 7),
    dt.date(2026, 5, 8),
    dt.date(2026, 5, 11),
]


def _load_api_key() -> str:
    if not ENV_PATH.exists():
        raise FileNotFoundError(f".env not found: {ENV_PATH}")
    for line in ENV_PATH.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        k, _, v = line.partition("=")
        if k.strip() == "DATABENTO_API_KEY":
            return v.strip().strip('"').strip("'")
    raise KeyError("DATABENTO_API_KEY not found in .env")


def _rth_window_utc(d: dt.date) -> tuple[pd.Timestamp, pd.Timestamp]:
    """RTH window in UTC for a given session date (DST-aware)."""
    open_et = dt.datetime(d.year, d.month, d.day, *RTH_OPEN_HM, tzinfo=ET)
    close_et = dt.datetime(d.year, d.month, d.day, *RTH_CLOSE_HM, tzinfo=ET)
    return (pd.Timestamp(open_et).tz_convert(UTC),
            pd.Timestamp(close_et).tz_convert(UTC))


def _cache_paths(d: dt.date) -> tuple[Path, Path]:
    iso = d.isoformat()
    return (CACHE_DIR / f"front_month_{iso}.parquet",
            CACHE_DIR / f"front_month_{iso}.meta.json")


def _load_reference_schema() -> tuple[list[str], dict[str, str], str | None]:
    """Return (column_names, dtype_map, index_name) of the reference file."""
    if not REFERENCE_PARQUET.exists():
        raise FileNotFoundError(
            f"Reference parquet not found: {REFERENCE_PARQUET}. "
            "Cannot validate schema."
        )
    ref = pd.read_parquet(REFERENCE_PARQUET)
    cols = list(ref.columns)
    dtypes = {c: str(ref[c].dtype) for c in cols}
    return cols, dtypes, ref.index.name


def _validate_schema(df: pd.DataFrame,
                     ref_cols: list[str],
                     ref_dtypes: dict[str, str],
                     ref_index_name: str | None,
                     session_date: dt.date) -> None:
    """Strict schema check against reference. Raise on mismatch."""
    new_cols = list(df.columns)
    if new_cols != ref_cols:
        only_ref = set(ref_cols) - set(new_cols)
        only_new = set(new_cols) - set(ref_cols)
        raise RuntimeError(
            f"[{session_date}] Column mismatch vs reference:\n"
            f"  only-in-reference: {sorted(only_ref)}\n"
            f"  only-in-new      : {sorted(only_new)}\n"
            f"  reference order  : {ref_cols[:5]}...\n"
            f"  new order        : {new_cols[:5]}..."
        )
    mismatches = []
    for c in ref_cols:
        if str(df[c].dtype) != ref_dtypes[c]:
            mismatches.append((c, ref_dtypes[c], str(df[c].dtype)))
    if mismatches:
        msg = "\n".join(f"  {c}: ref={r} new={n}" for c, r, n in mismatches)
        raise RuntimeError(f"[{session_date}] Dtype mismatch vs reference:\n{msg}")
    if df.index.name != ref_index_name:
        raise RuntimeError(
            f"[{session_date}] Index name mismatch: "
            f"new={df.index.name!r} ref={ref_index_name!r}"
        )


def _pull_one_day(client: db.Historical,
                  d: dt.date,
                  ref_cols: list[str],
                  ref_dtypes: dict[str, str],
                  ref_index_name: str | None) -> dict:
    """Pull one MBP-10 RTH session, validate schema, write cache. Return summary."""
    parquet_path, meta_path = _cache_paths(d)
    if parquet_path.exists() or meta_path.exists():
        return {"date": d.isoformat(), "status": "skipped_existing",
                "rows": None, "bytes": parquet_path.stat().st_size if parquet_path.exists() else None}

    start_utc, end_utc = _rth_window_utc(d)
    print(f"  [{d.isoformat()}] pulling {SCHEMA} {SYMBOL} "
          f"{start_utc.isoformat()} -> {end_utc.isoformat()}", flush=True)

    data = client.timeseries.get_range(
        dataset=DATASET,
        symbols=[SYMBOL],
        stype_in=STYPE_IN,
        schema=SCHEMA,
        start=start_utc,
        end=end_utc,
    )
    df = data.to_df()
    if df.empty:
        raise RuntimeError(f"[{d.isoformat()}] Databento returned 0 rows.")

    # Sanity: index should be ts_recv UTC tz-aware
    if df.index.name != "ts_recv":
        raise RuntimeError(
            f"[{d.isoformat()}] Unexpected index name: {df.index.name!r} "
            f"(expected 'ts_recv')"
        )

    # Strict schema check vs reference (2026-04-28)
    _validate_schema(df, ref_cols, ref_dtypes, ref_index_name, d)

    # Sanity: single instrument_id (continuous mode resolves to one outright per day)
    uniq_iid = df["instrument_id"].nunique()
    if uniq_iid != 1:
        raise RuntimeError(
            f"[{d.isoformat()}] Expected 1 unique instrument_id, got {uniq_iid}. "
            f"Possible mid-session roll — halting for manual inspection."
        )
    fm_iid = int(df["instrument_id"].iloc[0])
    fm_sym = str(df["symbol"].iloc[0])
    n_rows = len(df)

    # Write parquet + meta
    df.to_parquet(parquet_path)
    meta = {
        "session_date": d.isoformat(),
        "front_month": {
            "instrument_id": fm_iid,
            "symbol": fm_sym,
            "record_count": n_rows,        # for continuous pulls, total == RTH
            "rth_record_count": n_rows,
        },
        "roll_event": None,
        "_provenance": {
            "pulled_by": "scripts/data_refresh/step1_pull_mbp10.py",
            "pulled_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
            "dataset": DATASET,
            "schema": SCHEMA,
            "stype_in": STYPE_IN,
            "symbol": SYMBOL,
            "start_utc": start_utc.isoformat(),
            "end_utc": end_utc.isoformat(),
        },
    }
    with open(meta_path, "w") as f:
        json.dump(meta, f, indent=2)

    return {
        "date": d.isoformat(),
        "status": "pulled",
        "rows": n_rows,
        "bytes": parquet_path.stat().st_size,
        "instrument_id": fm_iid,
    }


def main() -> int:
    print("=" * 78)
    print("STEP 1 — MBP-10 pull (continuous, ES.c.0, RTH)")
    print("=" * 78)
    print(f"cache_dir: {CACHE_DIR}")
    print(f"reference: {REFERENCE_PARQUET.name}")
    print(f"target dates ({len(TARGET_DATES)}):")
    for d in TARGET_DATES:
        print(f"  {d.isoformat()}  ({d.strftime('%A')})")

    if not REFERENCE_PARQUET.exists():
        print(f"\n[FATAL] reference parquet missing: {REFERENCE_PARQUET}")
        return 1

    api_key = _load_api_key()
    client = db.Historical(api_key)

    # Pre-flight: cost estimate for the whole batch
    print("\nCost estimate (RTH-only, continuous, schema=mbp-10):")
    total_cost = 0.0
    per_day_costs = []
    for d in TARGET_DATES:
        parquet_path, _ = _cache_paths(d)
        if parquet_path.exists():
            print(f"  {d.isoformat()}: SKIP (cache exists)")
            continue
        start_utc, end_utc = _rth_window_utc(d)
        try:
            c = float(client.metadata.get_cost(
                dataset=DATASET,
                symbols=[SYMBOL],
                stype_in=STYPE_IN,
                schema=SCHEMA,
                start=start_utc,
                end=end_utc,
            ))
        except Exception as e:
            print(f"  {d.isoformat()}: cost estimate FAILED ({type(e).__name__}: {e})")
            return 1
        total_cost += c
        per_day_costs.append((d, c))
        print(f"  {d.isoformat()}: ${c:.4f}")
    print(f"  ---")
    print(f"  TOTAL ESTIMATED COST: ${total_cost:.4f}")

    if total_cost > 10.0:
        print(f"\n[ABORT] cost estimate ${total_cost:.2f} > $10.00 threshold. "
              "Edit script to confirm or reduce scope.")
        return 1
    print(f"  → under $10 threshold, proceeding.\n")

    # Load reference schema once
    ref_cols, ref_dtypes, ref_index_name = _load_reference_schema()
    print(f"reference schema loaded: {len(ref_cols)} cols, index={ref_index_name!r}")

    # Pull one day at a time
    print("\n" + "-" * 78)
    print("PULLING (one day at a time)")
    print("-" * 78)
    summaries = []
    for d in TARGET_DATES:
        try:
            s = _pull_one_day(client, d, ref_cols, ref_dtypes, ref_index_name)
            summaries.append(s)
            if s["status"] == "pulled":
                print(f"  [{s['date']}] OK  rows={s['rows']:,}  "
                      f"size={s['bytes']/(1024*1024):.1f}MB  iid={s['instrument_id']}")
            else:
                print(f"  [{s['date']}] {s['status']}")
        except Exception as e:
            print(f"\n[FATAL] failed on {d.isoformat()}: {type(e).__name__}: {e}")
            print("Halting; no retry. Inspect API state and re-run.")
            return 1

    # Summary
    print("\n" + "=" * 78)
    print("STEP 1 SUMMARY")
    print("=" * 78)
    n_pulled = sum(1 for s in summaries if s["status"] == "pulled")
    n_skipped = sum(1 for s in summaries if s["status"] == "skipped_existing")
    print(f"  pulled : {n_pulled}")
    print(f"  skipped: {n_skipped}")
    print(f"  total  : {len(summaries)}")
    print(f"  estimated cost charged: ${total_cost:.4f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
