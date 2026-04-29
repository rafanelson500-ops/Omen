"""
Smoke test: prove the replication pipeline end-to-end on 5 minutes of data.

WHAT IT DOES:
    1. Streams 5 min of CMBP-1 (9:30-9:35 ET) from Databento API to disk
       (~150 MB, ~$0.79, ~10-15 min at 3.4 Mbps)
    2. Loads OI from the existing statistics file (already on disk, free)
    3. Walks NBBO events, maintains state, computes net_gex per second
       with vectorized BSM, tests all 6 variants in parallel
    4. Compares to GexBot's archived gexoflow for those 300 seconds
    5. Prints per-variant correlation numbers + verdict

WHY THIS MATTERS:
    - Catches sign convention bugs (correlation flips sign)
    - Catches unit scaling bugs (correlation is ~1.0 but std ratio is wildly off)
    - Catches schema parsing bugs (results are all zero or all NaN)
    - Catches DTE handling bugs (0DTE strikes excluded)

LIMITATIONS:
    - 5 minutes = 300 seconds of data. Cannot compute OMEN's 5-min bar
      Z-score (needs 100 min). Only validates raw 1-sec correlation.
    - A promising raw correlation on smoke test (>0.3) means the full run
      is worth doing. A near-zero correlation means kill the project.

USAGE:
    python3 smoke_test_final.py

    No arguments. Uses defaults baked into the script (April 22, 9:30-9:35 ET).

COST: $0.79 from your remaining $85.60 credit balance.
TIME: ~10-15 min download + ~1-2 min compute = ~20 min total at 3.4 Mbps.
"""
from __future__ import annotations

import os
import time
import warnings
from datetime import date
from pathlib import Path
from zoneinfo import ZoneInfo

warnings.filterwarnings("ignore")

import databento as db
import numpy as np
import pandas as pd
from dotenv import load_dotenv
from scipy.stats import norm

# ── Hardcoded smoke test config ──────────────────────────────────────────────
TARGET_DATE  = date(2026, 4, 22)
START_TIME   = "10:00"
END_TIME     = "10:05"
ET           = ZoneInfo("America/New_York")
PRICE_SCALE  = 1e-9

# Paths (relative to script location)
PROJECT_ROOT = Path("./backend")
SCRATCH_DIR  = PROJECT_ROOT / "data" / "repricer_scratch"
CMBP1_PATH   = SCRATCH_DIR / "smoke_cmbp1_apr22_1000_1005.dbn.zst"
STATS_PATH   = PROJECT_ROOT / "data" / "opra_statistics_apr22_23.dbn.zst"
GEXBOT_PATH  = PROJECT_ROOT / "data" / "gex" / "2026-04-22.parquet"

# BSM constants
RISK_FREE_RATE   = 0.045
STRIKE_BAND_PCT  = 0.15
SECONDS_PER_YEAR = 365 * 24 * 3600
SPX_EXPIRY_HM    = (9, 30)   # SPX standard: AM-settled
SPXW_EXPIRY_HM   = (16, 0)   # SPXW: PM-settled
NEWTON_ITERS     = 12
MIN_IV, MAX_IV   = 0.01, 5.0
CONTRACT_MULT    = 100


# ── Step 1: Stream 5 min from API to disk ────────────────────────────────────
def stream_to_disk() -> None:
    if CMBP1_PATH.exists():
        size_mb = CMBP1_PATH.stat().st_size / 1e6
        print(f"[1/4] CMBP-1 file already exists ({size_mb:.1f} MB), skipping download")
        return

    print(f"[1/4] Streaming CMBP-1 from API to {CMBP1_PATH}")
    print(f"      Window: {TARGET_DATE} {START_TIME}-{END_TIME} ET")
    print(f"      Cost: ~$0.79  Time at 350 Mbps: ~30 sec download")
    print()

    SCRATCH_DIR.mkdir(parents=True, exist_ok=True)

    load_dotenv("./backend/.env")
    api_key = os.getenv("DATABENTO_API_KEY", "")
    if not api_key:
        raise RuntimeError("DATABENTO_API_KEY not in ./backend/.env")

    sh, sm = [int(x) for x in START_TIME.split(":")]
    eh, em = [int(x) for x in END_TIME.split(":")]
    s_utc = pd.Timestamp(TARGET_DATE.year, TARGET_DATE.month, TARGET_DATE.day,
                         sh, sm, tzinfo=ET).tz_convert("UTC")
    e_utc = pd.Timestamp(TARGET_DATE.year, TARGET_DATE.month, TARGET_DATE.day,
                         eh, em, tzinfo=ET).tz_convert("UTC")

    client = db.Historical(key=api_key)

    print("      Calling Databento API (will take ~1 min)...")
    t0 = time.monotonic()
    client.timeseries.get_range(
        dataset  = "OPRA.PILLAR",
        schema   = "cmbp-1",
        symbols  = ["SPX.OPT", "SPXW.OPT"],
        stype_in = "parent",
        start    = s_utc.strftime("%Y-%m-%dT%H:%M:%S"),
        end      = e_utc.strftime("%Y-%m-%dT%H:%M:%S"),
        path     = str(CMBP1_PATH),
    )
    elapsed_min = (time.monotonic() - t0) / 60
    size_mb = CMBP1_PATH.stat().st_size / 1e6
    print(f"      Done in {elapsed_min:.1f} min. File size: {size_mb:.1f} MB")


# ── Step 2: Load OI ──────────────────────────────────────────────────────────
def load_oi() -> pd.DataFrame:
    print(f"\n[2/4] Loading OI from {STATS_PATH}")

    if not STATS_PATH.exists():
        raise FileNotFoundError(f"OI file missing: {STATS_PATH}")

    store = db.DBNStore.from_file(STATS_PATH)
    df = store.to_df()
    df = df[df["stat_type"] == 9].copy()
    df["date_et"] = df["ts_event"].dt.tz_convert("America/New_York").dt.date
    df = df[df["date_et"] == TARGET_DATE]
    df = (df.sort_values("ts_event")
            .groupby("instrument_id").first().reset_index())

    parsed = df["symbol"].apply(_parse_symbol)
    df["root"]    = parsed.apply(lambda x: x["root"]   if x else None)
    df["expiry"]  = parsed.apply(lambda x: x["expiry"] if x else None)
    df["opttype"] = parsed.apply(lambda x: x["type"]   if x else None)
    df["strike"]  = parsed.apply(lambda x: x["strike"] if x else None)
    df["oi"]      = df["quantity"].astype(int)
    df = df.dropna(subset=["root", "expiry", "opttype", "strike"])
    df = df[df["oi"] > 0]

    df["expiry_ts_ns"] = df.apply(
        lambda r: _expiry_ts_ns(r["root"], r["expiry"]), axis=1
    )
    df["instrument_id"] = df["instrument_id"].astype("int32")

    print(f"      {len(df):,} active instruments")
    return df.set_index("instrument_id")


def _parse_symbol(sym: str) -> dict | None:
    sym = sym.strip()
    i = 0
    while i < len(sym) and not sym[i].isdigit():
        i += 1
    root = sym[:i].strip()
    body = sym[i:]
    if len(body) < 15:
        return None
    try:
        yy = int(body[0:2]); mm = int(body[2:4]); dd = int(body[4:6])
        opt = body[6].lower()
        strike = int(body[7:15]) / 1000.0
    except (ValueError, IndexError):
        return None
    if opt not in ("c", "p"):
        return None
    return {
        "root": root,
        "expiry": date(2000 + yy, mm, dd),
        "type": opt,
        "strike": strike,
    }


def _expiry_ts_ns(root: str, exp_date: date) -> int:
    h, m = SPX_EXPIRY_HM if root == "SPX" else SPXW_EXPIRY_HM
    ts = pd.Timestamp(exp_date.year, exp_date.month, exp_date.day, h, m, tzinfo=ET)
    return int(ts.tz_convert("UTC").value)


# ── Step 3: Walk CMBP-1 events, compute net_gex per second ───────────────────
def compute(oi_df: pd.DataFrame) -> pd.DataFrame:
    print(f"\n[3/4] Walking CMBP-1 events, computing net_gex per second")

    # Build spot lookup from GexBot archive
    gb = pd.read_parquet(GEXBOT_PATH)
    # GexBot timestamps are datetime64[ms, tz]. .astype("int64") on this
    # returns ms since epoch (NOT ns). Multiply by 1e6 to get ns. Then
    # floor to nearest second for the lookup key.
    ms_since_epoch = gb["timestamp"].astype("int64")        # ms since epoch (UTC)
    ns_since_epoch = ms_since_epoch * 1_000_000             # convert ms → ns
    gb["second_ns"] = (ns_since_epoch // 1_000_000_000) * 1_000_000_000
    spot_lookup = gb.set_index("second_ns")["spot"].to_dict()
    print(f"      Loaded {len(spot_lookup):,} spot snapshots from GexBot archive")

    # NBBO state per instrument
    state: dict[int, tuple[float, float]] = {}

    # Precompute OI metadata as numpy arrays for fast lookup
    # Build a lookup keyed by instrument_id → row index in oi_df
    oi_index = {iid: i for i, iid in enumerate(oi_df.index)}
    n_instruments = len(oi_df)

    strike_arr  = oi_df["strike"].values.astype(np.float64)
    oi_arr      = oi_df["oi"].values.astype(np.float64)
    optcall_arr = (oi_df["opttype"].values == "c")
    expiry_arr  = oi_df["expiry_ts_ns"].values.astype(np.int64)

    # Walk CMBP-1 records
    print(f"      Walking CMBP-1 records...")
    store = db.DBNStore.from_file(CMBP1_PATH)
    n_records = 0
    n_updates = 0

    # Per-second net_gex accumulator: {sec_ns: {variant: value}}
    results: dict[int, dict] = {}
    current_sec = None

    t0 = time.monotonic()

    for record in store:
        n_records += 1
        try:
            ts_ns = int(record.ts_event)
            iid   = int(record.instrument_id)
            lvl   = record.levels[0]
            bid_r = int(lvl.bid_px)
            ask_r = int(lvl.ask_px)
        except (AttributeError, IndexError):
            continue

        if bid_r <= 0 or ask_r <= 0:
            continue

        bid = bid_r * PRICE_SCALE
        ask = ask_r * PRICE_SCALE
        if ask < bid:
            continue

        # Only update state for instruments we have OI for
        if iid not in oi_index:
            continue

        state[iid] = (bid, ask)
        n_updates += 1

        # Process per-second snapshots
        sec_ns = (ts_ns // 1_000_000_000) * 1_000_000_000

        if current_sec is None:
            current_sec = sec_ns
            continue

        if sec_ns > current_sec:
            # Snapshot the previous second
            row = compute_snapshot(
                current_sec, state, oi_index, oi_df,
                strike_arr, oi_arr, optcall_arr, expiry_arr,
                spot_lookup,
            )
            if row is not None:
                results[current_sec] = row
            current_sec = sec_ns

    # Final snapshot
    if current_sec is not None:
        row = compute_snapshot(
            current_sec, state, oi_index, oi_df,
            strike_arr, oi_arr, optcall_arr, expiry_arr, spot_lookup,
        )
        if row is not None:
            results[current_sec] = row

    elapsed_min = (time.monotonic() - t0) / 60
    print(f"      {n_records:,} records, {n_updates:,} kept, "
          f"{len(results):,} seconds computed, {elapsed_min:.1f} min")

    if not results:
        raise RuntimeError("No seconds computed. Check time window and data.")

    df = pd.DataFrame.from_dict(results, orient="index").sort_index()
    df.index.name = "second_ns"
    # Add gexoflow (first differences)
    for col in [c for c in df.columns if c.startswith("net_gex_")]:
        df[col.replace("net_gex_", "gexoflow_")] = df[col].diff()
    return df


def compute_snapshot(
    sec_ns: int,
    state: dict,
    oi_index: dict,
    oi_df: pd.DataFrame,
    strike_arr: np.ndarray,
    oi_arr: np.ndarray,
    optcall_arr: np.ndarray,
    expiry_arr: np.ndarray,
    spot_lookup: dict,
) -> dict | None:
    """Compute net_gex for all 6 variants for one second."""
    if not state:
        return None
    spot = spot_lookup.get(sec_ns)
    if spot is None or spot <= 0:
        return None

    # Build aligned arrays
    iids = np.array([i for i in state.keys() if i in oi_index], dtype=np.int32)
    if len(iids) == 0:
        return None
    idx = np.array([oi_index[i] for i in iids])
    bids = np.array([state[i][0] for i in iids])
    asks = np.array([state[i][1] for i in iids])

    K       = strike_arr[idx]
    OI      = oi_arr[idx]
    is_call = optcall_arr[idx]
    exp_ns  = expiry_arr[idx]

    # Strike band filter
    in_band = np.abs(K / spot - 1.0) <= STRIKE_BAND_PCT
    if not in_band.any():
        return None

    K = K[in_band]; OI = OI[in_band]; is_call = is_call[in_band]
    exp_ns = exp_ns[in_band]; bids = bids[in_band]; asks = asks[in_band]

    # Fractional DTE in years (handles 0DTE)
    dte_years = (exp_ns - sec_ns) / 1e9 / SECONDS_PER_YEAR
    valid = dte_years > 0
    if not valid.any():
        return None

    K = K[valid]; OI = OI[valid]; is_call = is_call[valid]
    bids = bids[valid]; asks = asks[valid]; dte_years = dte_years[valid]
    S_arr = np.full_like(K, spot)

    mid = 0.5 * (bids + asks)

    iv_mid = iv_newton(mid,  S_arr, K, dte_years, is_call)
    iv_bid = iv_newton(bids, S_arr, K, dte_years, is_call)
    iv_ask = iv_newton(asks, S_arr, K, dte_years, is_call)

    g_mid = gamma_safe(S_arr, K, dte_years, iv_mid)
    g_bid = gamma_safe(S_arr, K, dte_years, iv_bid)
    g_ask = gamma_safe(S_arr, K, dte_years, iv_ask)

    spot_sq = spot * spot
    base_mid = g_mid * OI * CONTRACT_MULT * spot_sq
    base_bid = g_bid * OI * CONTRACT_MULT * spot_sq
    base_ask = g_ask * OI * CONTRACT_MULT * spot_sq

    sign_A = np.where(is_call, +1.0, -1.0)
    sign_B = np.where(is_call, -1.0, +1.0)

    return {
        "spot":          float(spot),
        "n_strikes":     int(len(K)),
        "net_gex_A_mid": float((base_mid * sign_A).sum()),
        "net_gex_A_bid": float((base_bid * sign_A).sum()),
        "net_gex_A_ask": float((base_ask * sign_A).sum()),
        "net_gex_B_mid": float((base_mid * sign_B).sum()),
        "net_gex_B_bid": float((base_bid * sign_B).sum()),
        "net_gex_B_ask": float((base_ask * sign_B).sum()),
    }


# ── Vectorized BSM ───────────────────────────────────────────────────────────
def bsm_price(S, K, T, sig, r, is_call):
    sqrtT = np.sqrt(T)
    d1 = (np.log(S/K) + (r + 0.5*sig**2)*T) / (sig*sqrtT)
    d2 = d1 - sig*sqrtT
    call = S*norm.cdf(d1) - K*np.exp(-r*T)*norm.cdf(d2)
    put  = K*np.exp(-r*T)*norm.cdf(-d2) - S*norm.cdf(-d1)
    return np.where(is_call, call, put)


def bsm_vega(S, K, T, sig, r):
    sqrtT = np.sqrt(T)
    d1 = (np.log(S/K) + (r + 0.5*sig**2)*T) / (sig*sqrtT)
    return S * sqrtT * norm.pdf(d1)


def iv_newton(price, S, K, T, is_call, r=RISK_FREE_RATE):
    sigma = np.sqrt(np.maximum(2*np.pi/T, 1e-6)) * (price / np.maximum(S, 1.0))
    sigma = np.clip(sigma, 0.05, 3.0)
    valid = (T > 0) & (price > 0) & (S > 0) & (K > 0)
    sigma = np.where(valid, sigma, np.nan)
    for _ in range(NEWTON_ITERS):
        with np.errstate(invalid="ignore", divide="ignore"):
            theo = bsm_price(S, K, T, sigma, r, is_call)
            diff = price - theo
            v = bsm_vega(S, K, T, sigma, r)
            step = np.where(v > 1e-6, diff / v, 0.0)
            sigma = np.clip(sigma + step, MIN_IV, MAX_IV)
    final = bsm_price(S, K, T, sigma, r, is_call)
    converged = np.abs(final - price) < (price * 0.05 + 0.01)
    return np.where(converged & (sigma > MIN_IV) & (sigma < MAX_IV), sigma, np.nan)


def gamma_safe(S, K, T, sig, r=RISK_FREE_RATE):
    with np.errstate(invalid="ignore", divide="ignore"):
        sqrtT = np.sqrt(T)
        d1 = (np.log(S/K) + (r + 0.5*sig**2)*T) / (sig*sqrtT)
        g = norm.pdf(d1) / (S * sig * sqrtT)
    return np.where(np.isfinite(g) & (sig > 0), g, 0.0)


# ── Step 4: Validate ─────────────────────────────────────────────────────────
def validate(rep: pd.DataFrame) -> None:
    print(f"\n[4/4] Validating against GexBot archive")

    rep.index = pd.to_datetime(rep.index, unit="ns", utc=True)
    flow_cols = [c for c in rep.columns if c.startswith("gexoflow_")]

    gb = pd.read_parquet(GEXBOT_PATH)
    gb["ts_utc"] = gb["timestamp"].dt.tz_convert("UTC").dt.floor("s")
    gb = gb.set_index("ts_utc").sort_index()
    gb = gb[~gb.index.duplicated(keep="last")]

    joined = rep[flow_cols].join(gb[["gexoflow"]], how="inner").dropna()
    print(f"      Overlapping seconds: {len(joined)}")

    if len(joined) < 50:
        print("      ERROR: not enough overlapping seconds. Check timezone alignment.")
        return

    print()
    print(f"  {'VARIANT':<12} {'RAW_CORR':>10} {'SIGN_AGREE':>11} "
          f"{'REP_STD':>14} {'GBOT_STD':>14} {'STD_RATIO':>10}")
    print("  " + "─" * 72)

    best_corr = 0.0
    best_var = None
    gbot_std = joined["gexoflow"].std()

    for col in flow_cols:
        variant = col.replace("gexoflow_", "")
        s = joined[col].dropna()
        gb_s = joined["gexoflow"].loc[s.index]
        if len(s) < 30:
            continue
        corr = s.corr(gb_s)
        sign_ag = (np.sign(s) == np.sign(gb_s)).mean()
        rep_std = s.std()
        ratio = rep_std / gbot_std if gbot_std > 0 else float("nan")

        print(f"  {variant:<12} {corr:>+10.4f} {sign_ag:>10.1%} "
              f"{rep_std:>14,.2f} {gbot_std:>14,.2f} {ratio:>10.3f}x")

        if pd.notna(corr) and abs(corr) > abs(best_corr):
            best_corr = corr
            best_var = variant

    print()
    print("  " + "═" * 72)
    if best_var is None:
        print("  BEST: NONE  (all correlations were NaN)")
    else:
        print(f"  BEST: {best_var}  (corr={best_corr:+.4f})")
    print("  " + "═" * 72)
    print()

    # Detect zero-variance GexBot — likely warmup window or dead data
    if gbot_std == 0 or pd.isna(gbot_std):
        print(f"  CANNOT VALIDATE: GexBot gexoflow has zero variance over the {len(joined)}-second")
        print("  overlapping window. This usually means the window is in GexBot's warmup")
        print("  period (gexoflow is a rolling derivative — first ~5 min after open are 0).")
        print()
        print("  ACTION: re-run on a window that starts AT LEAST 6 minutes after market open.")
        print("  Recommended: 10:00-10:30 ET window (well past warmup, before lunch lull).")
    elif best_var is None:
        print(f"  ALL CORRELATIONS NaN — likely a column-level issue. Check replicated series.")
    elif abs(best_corr) > 0.5:
        print(f"  PROMISING: |correlation| > 0.5 on raw 1-second data over {len(joined)} seconds.")
        print("  This is well above noise. Methodology is in the ballpark.")
        if best_corr < 0:
            print(f"  NOTE: best correlation is NEGATIVE. Sign convention is reversed.")
            print(f"  Use variant '{best_var}' going forward.")
        print()
        print("  RECOMMEND: proceed to full-day run.")
    elif abs(best_corr) > 0.2:
        print(f"  WEAK BUT REAL: |correlation| ≈ 0.2-0.5 over {len(joined)} seconds.")
        print("  Some signal present but methodology may have issues.")
        print("  Investigate: sign convention, IV input, OI timing, spot mismatch (ES vs SPX).")
    else:
        print(f"  NO SIGNAL: |correlation| < 0.2 across all variants.")
        print("  Replication is not working. Likely issues:")
        print("    1. Symbol/instrument_id mapping bug")
        print("    2. NBBO not being tracked correctly")
        print("    3. GexBot uses fundamentally different methodology")
        print("  DO NOT spend more on Databento until this is diagnosed.")

    print()
    print("  Magnitude check:")
    if best_var and gbot_std > 0:
        rep_std_best = joined[f"gexoflow_{best_var}"].std()
        ratio = rep_std_best / gbot_std
        if ratio > 100 or ratio < 0.01:
            print(f"    Std ratio is {ratio:.3e}x — large unit mismatch.")
            print(f"    GexBot likely scales output. Try dividing by 1e6 (if reporting in $MM).")
        elif ratio > 5 or ratio < 0.2:
            print(f"    Std ratio is {ratio:.2f}x — moderate scaling difference.")
        else:
            print(f"    Std ratio is {ratio:.2f}x — magnitudes are roughly aligned.")
    else:
        print(f"    Skipped — no valid comparison (GexBot std = {gbot_std}).")


def main() -> None:
    print("=" * 70)
    print("GEXBOT REPLICATION SMOKE TEST")
    print("=" * 70)
    print(f"  Date:      {TARGET_DATE}")
    print(f"  Window:    {START_TIME}-{END_TIME} ET (5 min, post-warmup)")
    print(f"  Cost:      $0.79 (from your $84.81 credit balance)")
    print(f"  Total time:~3-5 min at 350 Mbps")
    print()

    stream_to_disk()
    oi_df = load_oi()
    rep_df = compute(oi_df)
    validate(rep_df)

    out = SCRATCH_DIR / "smoke_results.parquet"
    rep_df.to_parquet(out)
    print(f"\n  Replicated series saved to: {out}")


if __name__ == "__main__":
    main()
