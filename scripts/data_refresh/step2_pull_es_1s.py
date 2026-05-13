"""Step 2 — pull ES 1s bars for the forward gap Apr 28 → May 11 (10 trading days).

Writes a NEW separate parquet file (does NOT overwrite the existing primary):
  backend/data/market/ES_c_0_ohlcv1s_2026-04-28_2026-05-11.parquet

Mirrors backend/cheese/market.py.fetch convention:
  - dataset=GLBX.MDP3
  - schema=ohlcv-1s
  - stype_in=continuous, symbols=['ES.c.0']
  - start = 09:25 ET on Apr 28 (UTC-converted), end = end-of-day May 11 ET (UTC-converted)
  - index = America/New_York tz-aware, name='timestamp'
  - columns = [open, high, low, close, volume] float64 (volume kept native)

Hard rules:
  - Never overwrite existing file (refuse if path exists).
  - Estimate cost first; abort if > $10.
  - Stop on API error; do not retry silently.
  - Schema compatibility check against the existing primary file
    (ES_c_0_ohlcv1s_2025-09-08_2026-04-27.parquet).
"""
from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path
from zoneinfo import ZoneInfo

import databento as db
import pandas as pd

# Paths
ES_DIR = Path("/Users/rafanelson/Omen/backend/data/market")
ENV_PATH = Path("/Users/rafanelson/Omen/backend/.env")
REFERENCE_PARQUET = ES_DIR / "ES_c_0_ohlcv1s_2025-09-08_2026-04-27.parquet"

DATASET = "GLBX.MDP3"
SYMBOL = "ES.c.0"
STYPE_IN = "continuous"
SCHEMA = "ohlcv-1s"

ET = ZoneInfo("America/New_York")
UTC = ZoneInfo("UTC")

START_SESSION = dt.date(2026, 5, 12)
END_SESSION = dt.date(2026, 5, 12)


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


def _start_utc(d: dt.date) -> pd.Timestamp:
    """09:25 ET on `d` -> UTC (mirrors backend/cheese/market.py)."""
    et = dt.datetime(d.year, d.month, d.day, 9, 25, tzinfo=ET)
    return pd.Timestamp(et).tz_convert(UTC)


def _end_utc(d: dt.date) -> pd.Timestamp:
    """End-of-day boundary: start of (d + 1 day) in ET, converted to UTC.
    Matches the existing market.py `_clamp_end` formula except never clamped
    here — we're well past any 35min publishing lag for these historical dates.
    """
    next_day = d + dt.timedelta(days=1)
    et = dt.datetime(next_day.year, next_day.month, next_day.day, 0, 0, tzinfo=ET)
    return pd.Timestamp(et).tz_convert(UTC)


def _output_path() -> Path:
    return ES_DIR / f"ES_c_0_ohlcv1s_{START_SESSION.isoformat()}_{END_SESSION.isoformat()}.parquet"


def _load_reference_schema() -> tuple[list[str], dict[str, str], str | None, str | None]:
    """Return (cols, dtypes, index_name, index_tz)."""
    ref = pd.read_parquet(REFERENCE_PARQUET)
    if not isinstance(ref.index, pd.DatetimeIndex):
        raise RuntimeError(
            f"Reference index is not DatetimeIndex: {type(ref.index)}"
        )
    cols = list(ref.columns)
    dtypes = {c: str(ref[c].dtype) for c in cols}
    return cols, dtypes, ref.index.name, str(ref.index.tz) if ref.index.tz is not None else None


def _validate_schema(df: pd.DataFrame,
                     ref_cols: list[str],
                     ref_dtypes: dict[str, str],
                     ref_index_name: str | None,
                     ref_index_tz: str | None) -> None:
    new_cols = list(df.columns)
    if new_cols != ref_cols:
        raise RuntimeError(
            f"Column mismatch vs reference:\n"
            f"  ref={ref_cols}\n  new={new_cols}"
        )
    mismatches = []
    for c in ref_cols:
        if str(df[c].dtype) != ref_dtypes[c]:
            mismatches.append((c, ref_dtypes[c], str(df[c].dtype)))
    if mismatches:
        msg = "\n".join(f"  {c}: ref={r} new={n}" for c, r, n in mismatches)
        raise RuntimeError(f"Dtype mismatch:\n{msg}")
    if df.index.name != ref_index_name:
        raise RuntimeError(
            f"Index name mismatch: new={df.index.name!r} ref={ref_index_name!r}"
        )
    new_tz = str(df.index.tz) if df.index.tz is not None else None
    if new_tz != ref_index_tz:
        raise RuntimeError(
            f"Index tz mismatch: new={new_tz!r} ref={ref_index_tz!r}"
        )


def main() -> int:
    print("=" * 78)
    print("STEP 2 — ES 1s bars pull (continuous, ES.c.0)")
    print("=" * 78)
    print(f"range : {START_SESSION.isoformat()} -> {END_SESSION.isoformat()}")
    print(f"output: {_output_path()}")
    print(f"reference: {REFERENCE_PARQUET.name}")

    out = _output_path()
    if out.exists():
        print(f"\n[ABORT] output file already exists: {out}")
        print("Refusing to overwrite. Delete manually or change scope.")
        return 1
    if not REFERENCE_PARQUET.exists():
        print(f"\n[FATAL] reference parquet missing: {REFERENCE_PARQUET}")
        return 1

    api_key = _load_api_key()
    client = db.Historical(api_key)

    start_utc = _start_utc(START_SESSION)
    end_utc = _end_utc(END_SESSION)
    print(f"\nstart_utc: {start_utc.isoformat()}")
    print(f"end_utc  : {end_utc.isoformat()}")

    # Cost estimate
    print("\nCost estimate (ohlcv-1s, continuous):")
    try:
        cost = float(client.metadata.get_cost(
            dataset=DATASET,
            symbols=[SYMBOL],
            stype_in=STYPE_IN,
            schema=SCHEMA,
            start=start_utc,
            end=end_utc,
        ))
    except Exception as e:
        print(f"  cost estimate FAILED ({type(e).__name__}: {e})")
        return 1
    print(f"  ESTIMATED COST: ${cost:.4f}")
    if cost > 10.0:
        print(f"\n[ABORT] cost {cost:.2f} > $10 threshold.")
        return 1
    print("  → under threshold, proceeding.\n")

    # Load reference schema
    ref_cols, ref_dtypes, ref_index_name, ref_index_tz = _load_reference_schema()
    print(f"reference schema: cols={ref_cols}  index={ref_index_name!r}  tz={ref_index_tz}")

    # Pull
    print(f"\nPulling {SCHEMA} {SYMBOL} {start_utc.isoformat()} -> {end_utc.isoformat()} ...")
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
        print("[FATAL] Databento returned 0 rows.")
        return 1

    # Conform to existing convention (mirrors backend/cheese/market.py:97-105)
    df.index = pd.to_datetime(df.index, utc=True).tz_convert(ET)
    df.index.name = "timestamp"
    keep = [c for c in ("open", "high", "low", "close", "volume") if c in df.columns]
    if keep != ref_cols:
        print(f"[FATAL] available cols {keep} != reference cols {ref_cols}")
        return 1
    df = df[keep]
    df = df.astype({"open": "float64", "high": "float64", "low": "float64", "close": "float64"})

    # Strict schema validation against reference
    _validate_schema(df, ref_cols, ref_dtypes, ref_index_name, ref_index_tz)

    # Sanity: session-date coverage
    unique_dates = sorted(set(df.index.date))
    print(f"\nrows: {len(df):,}")
    print(f"first_ts: {df.index.min()}")
    print(f"last_ts : {df.index.max()}")
    print(f"unique session-dates: {len(unique_dates)}")
    for d in unique_dates[:30]:
        print(f"  {d.isoformat()}")
    if len(unique_dates) > 30:
        print(f"  ... and {len(unique_dates) - 30} more")

    # Write
    df.to_parquet(out)
    size_mb = out.stat().st_size / (1024 * 1024)
    print(f"\nwrote: {out}")
    print(f"size : {size_mb:.1f}MB")
    return 0


if __name__ == "__main__":
    sys.exit(main())
