"""
COMBINED CUMULATIVE INVENTORY MODEL — final replication test.

Tests the academic Barbon-Buraschi / Glassnode framework:

    inventory[strike, t] = inventory[strike, t-1] + signed_flow[strike, t]
    net_gex[t] = sum over strikes of (inventory × gamma[t] × spot[t]² × 100)
    gexoflow[t] = net_gex[t] - net_gex[t-1]

This expands to TWO effects, only one of which we tested before:
    1. signed_flow × gamma   (instantaneous flow effect — tested previously, corr 0.05)
    2. inventory × Δgamma    (inventory revaluation as gamma changes — NOT tested)

The combined model is what serious vendors (SpotGamma, Glassnode) actually use.

VARIANTS TESTED:
    1. Lee-Ready signed cumulative inventory + dynamic gamma
    2. Unsigned cumulative volume (assume all volume opens new contracts) + dynamic gamma
    Both with sign conventions A (call - put) and B (put - call).

USES ONLY EXISTING DATA ON DISK. Cost: $0. Time: ~3 min.
"""
from __future__ import annotations

import time
import warnings
from datetime import date
from pathlib import Path
from zoneinfo import ZoneInfo

warnings.filterwarnings("ignore")

import databento as db
import numpy as np
import pandas as pd
from scipy.stats import norm

# ── Config ────────────────────────────────────────────────────────────────────
TARGET_DATE      = date(2026, 4, 22)
ET               = ZoneInfo("America/New_York")
PRICE_SCALE      = 1e-9
RISK_FREE_RATE   = 0.045
STRIKE_BAND_PCT  = 0.15
SECONDS_PER_YEAR = 365 * 24 * 3600
CONTRACT_MULT    = 100

PROJECT_ROOT = Path("./backend")
SCRATCH_DIR  = PROJECT_ROOT / "data" / "repricer_scratch"
QUOTES_PATH  = SCRATCH_DIR / "smoke_cmbp1_apr22_1000_1005.dbn.zst"
TRADES_PATH  = SCRATCH_DIR / "smoke_trades_apr22_1000_1005.dbn.zst"
STATS_PATH   = PROJECT_ROOT / "data" / "opra_statistics_apr22_23.dbn.zst"
GEXBOT_PATH  = PROJECT_ROOT / "data" / "gex" / "2026-04-22.parquet"

SPX_EXPIRY_HM  = (9, 30)
SPXW_EXPIRY_HM = (16, 0)
NEWTON_ITERS = 12
MIN_IV, MAX_IV = 0.01, 5.0


# ── Symbol parsing ────────────────────────────────────────────────────────────
def parse_symbol(sym: str) -> dict | None:
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
    return {"root": root, "expiry": date(2000 + yy, mm, dd),
            "type": opt, "strike": strike}


def expiry_ts_ns(root: str, exp_date: date) -> int:
    h, m = SPX_EXPIRY_HM if root == "SPX" else SPXW_EXPIRY_HM
    ts = pd.Timestamp(exp_date.year, exp_date.month, exp_date.day, h, m, tzinfo=ET)
    return int(ts.tz_convert("UTC").value)


# ── Vectorized BSM ────────────────────────────────────────────────────────────
def bsm_price(S, K, T, sig, r, is_call):
    sqrtT = np.sqrt(T)
    d1 = (np.log(S/K) + (r + 0.5*sig**2)*T) / (sig*sqrtT)
    d2 = d1 - sig*sqrtT
    call = S*norm.cdf(d1) - K*np.exp(-r*T)*norm.cdf(d2)
    put  = K*np.exp(-r*T)*norm.cdf(-d2) - S*norm.cdf(-d1)
    return np.where(is_call, call, put)


def iv_newton(price, S, K, T, is_call, r=RISK_FREE_RATE):
    sigma = np.sqrt(np.maximum(2*np.pi/T, 1e-6)) * (price / np.maximum(S, 1.0))
    sigma = np.clip(sigma, 0.05, 3.0)
    valid = (T > 0) & (price > 0) & (S > 0) & (K > 0)
    sigma = np.where(valid, sigma, np.nan)
    for _ in range(NEWTON_ITERS):
        with np.errstate(invalid="ignore", divide="ignore"):
            sqrtT = np.sqrt(T)
            d1 = (np.log(S/K) + (r + 0.5*sigma**2)*T) / (sigma*sqrtT)
            v = S * sqrtT * norm.pdf(d1)
            theo = bsm_price(S, K, T, sigma, r, is_call)
            step = np.where(v > 1e-6, (price - theo)/v, 0.0)
            sigma = np.clip(sigma + step, MIN_IV, MAX_IV)
    return sigma


def gamma_vec(S, K, T, sig, r=RISK_FREE_RATE):
    with np.errstate(invalid="ignore", divide="ignore"):
        sqrtT = np.sqrt(T)
        d1 = (np.log(S/K) + (r + 0.5*sig**2)*T) / (sig*sqrtT)
        g = norm.pdf(d1) / (S * sig * sqrtT)
    return np.where(np.isfinite(g) & (sig > 0), g, 0.0)


# ── Load OI metadata ──────────────────────────────────────────────────────────
def load_oi() -> pd.DataFrame:
    print(f"[1/5] Loading OI metadata")
    store = db.DBNStore.from_file(STATS_PATH)
    df = store.to_df()
    df = df[df["stat_type"] == 9].copy()
    df["date_et"] = df["ts_event"].dt.tz_convert("America/New_York").dt.date
    df = df[df["date_et"] == TARGET_DATE]
    df = (df.sort_values("ts_event").groupby("instrument_id").first().reset_index())

    parsed = df["symbol"].apply(parse_symbol)
    df["root"]    = parsed.apply(lambda x: x["root"] if x else None)
    df["expiry"]  = parsed.apply(lambda x: x["expiry"] if x else None)
    df["opttype"] = parsed.apply(lambda x: x["type"] if x else None)
    df["strike"]  = parsed.apply(lambda x: x["strike"] if x else None)
    df["oi"]      = df["quantity"].astype(int)
    df = df.dropna(subset=["root", "expiry", "opttype", "strike"])
    df = df[df["oi"] > 0]
    df["expiry_ts_ns"] = df.apply(lambda r: expiry_ts_ns(r["root"], r["expiry"]), axis=1)
    df["instrument_id"] = df["instrument_id"].astype("int32")
    df["is_call"] = (df["opttype"] == "c")
    print(f"      {len(df):,} active instruments")
    return df.set_index("instrument_id")


# ── Build per-strike IV (one IV per strike, fixed across window) ──────────────
def compute_iv_per_strike(oi_df: pd.DataFrame, avg_spot: float, mid_sec_ns: int) -> dict:
    """For each instrument, get NBBO mid at end of window and solve IV."""
    print(f"[2/5] Computing IV per strike using NBBO mids")

    nbbo_state: dict[int, tuple[int, int]] = {}
    store = db.DBNStore.from_file(QUOTES_PATH)
    for record in store:
        try:
            iid = int(record.instrument_id)
            lvl = record.levels[0]
            br = int(lvl.bid_px)
            ar = int(lvl.ask_px)
        except (AttributeError, IndexError):
            continue
        if br > 0 and ar > 0 and ar >= br:
            nbbo_state[iid] = (br, ar)

    iv_lookup = {}
    valid_iids = []
    for iid, (br, ar) in nbbo_state.items():
        if iid not in oi_df.index:
            continue
        meta = oi_df.loc[iid]
        K = meta["strike"]
        if abs(K / avg_spot - 1.0) > STRIKE_BAND_PCT:
            continue
        valid_iids.append(iid)

    if not valid_iids:
        raise RuntimeError("No valid strikes in band")

    n = len(valid_iids)
    bids = np.zeros(n)
    asks = np.zeros(n)
    K_arr = np.zeros(n)
    is_call_arr = np.zeros(n, dtype=bool)
    expiry_ns_arr = np.zeros(n, dtype=np.int64)

    for i, iid in enumerate(valid_iids):
        b, a = nbbo_state[iid]
        bids[i] = b * PRICE_SCALE
        asks[i] = a * PRICE_SCALE
        meta = oi_df.loc[iid]
        K_arr[i] = meta["strike"]
        is_call_arr[i] = meta["is_call"]
        expiry_ns_arr[i] = meta["expiry_ts_ns"]

    mid_px = 0.5 * (bids + asks)
    S_arr = np.full(n, avg_spot)
    dte_years = (expiry_ns_arr - mid_sec_ns) / 1e9 / SECONDS_PER_YEAR
    valid = dte_years > 0

    iv = iv_newton(mid_px[valid], S_arr[valid], K_arr[valid],
                   dte_years[valid], is_call_arr[valid])

    iids_arr = np.array(valid_iids)
    for i, iid in enumerate(iids_arr[valid]):
        if np.isfinite(iv[i]) and iv[i] > MIN_IV:
            iv_lookup[int(iid)] = float(iv[i])

    print(f"      Computed IV for {len(iv_lookup):,} strikes")
    return iv_lookup


# ── Build cumulative inventory + per-second net_gex ───────────────────────────
def compute_combined_model(oi_df: pd.DataFrame, iv_lookup: dict) -> pd.DataFrame:
    """
    Walk quotes + trades chronologically. For each second:
      - Update NBBO state (from quote events)
      - Update cumulative_signed_inventory[strike] (from trade events)
      - At each second boundary, compute net_gex using:
          inventory[strike] × gamma(spot_at_t, K, T, IV_static) × spot_at_t² × 100
      - Sum separately for calls and puts
      - gex_orderflow = call_inventory_gex - put_inventory_gex
    """
    print(f"[3/5] Computing combined cumulative inventory + dynamic gamma")

    # Spot lookup from GexBot
    gb = pd.read_parquet(GEXBOT_PATH)
    ms = gb["timestamp"].astype("int64")
    ns = ms * 1_000_000
    gb["second_ns"] = (ns // 1_000_000_000) * 1_000_000_000
    spot_lookup = gb.set_index("second_ns")["spot"].to_dict()

    # Build active strikes list
    active_iids = sorted(iv_lookup.keys())
    n = len(active_iids)
    print(f"      Active strikes: {n:,}")

    iid_to_idx = {iid: i for i, iid in enumerate(active_iids)}

    # Static per-strike data (vectors)
    K_arr  = np.array([oi_df.loc[iid, "strike"]       for iid in active_iids])
    is_call_arr = np.array([oi_df.loc[iid, "is_call"] for iid in active_iids], dtype=bool)
    expiry_ns_arr = np.array([oi_df.loc[iid, "expiry_ts_ns"] for iid in active_iids], dtype=np.int64)
    iv_arr = np.array([iv_lookup[iid] for iid in active_iids])

    # Cumulative inventories (two variants in parallel)
    inventory_signed = np.zeros(n)   # Lee-Ready signed flow
    inventory_unsigned = np.zeros(n) # All volume = +1 (no classification)

    # Live state
    nbbo_state: dict[int, tuple[int, int]] = {}
    prior_sign: dict[int, int] = {}

    # Per-second results
    results = []
    last_processed_sec_ns = None

    quote_iter = iter(db.DBNStore.from_file(QUOTES_PATH))
    trade_iter = iter(db.DBNStore.from_file(TRADES_PATH))
    next_q = next(quote_iter, None)
    next_t = next(trade_iter, None)

    # Stats counters
    n_quotes = 0
    n_trades = 0
    n_classified = 0
    t0 = time.monotonic()
    last_log = t0

    def snapshot_second(sec_ns: int):
        """Compute net_gex variants at this second using current inventory + spot."""
        spot = spot_lookup.get(sec_ns)
        if spot is None or spot <= 0:
            return None

        dte_years = (expiry_ns_arr - sec_ns) / 1e9 / SECONDS_PER_YEAR
        valid = dte_years > 0
        if not valid.any():
            return None

        S_arr = np.full(n, spot)
        gamma = np.zeros(n)
        gamma[valid] = gamma_vec(S_arr[valid], K_arr[valid],
                                  dte_years[valid], iv_arr[valid])

        spot_sq = spot * spot

        # net_gex per variant: sum (inventory × gamma × spot² × 100)
        contrib_signed   = inventory_signed   * gamma * CONTRACT_MULT * spot_sq
        contrib_unsigned = inventory_unsigned * gamma * CONTRACT_MULT * spot_sq

        # Split call/put (this is per-strike gex; we sum separately)
        call_gex_signed   = contrib_signed[is_call_arr].sum()
        put_gex_signed    = contrib_signed[~is_call_arr].sum()
        call_gex_unsigned = contrib_unsigned[is_call_arr].sum()
        put_gex_unsigned  = contrib_unsigned[~is_call_arr].sum()

        return {
            "second_ns":   sec_ns,
            "spot":        spot,
            "n_active":    int((inventory_signed != 0).sum()),
            # signed inventory (Lee-Ready)
            "net_gex_signed_A":   call_gex_signed - put_gex_signed,
            "net_gex_signed_B":   put_gex_signed - call_gex_signed,
            # unsigned inventory (all volume = +1)
            "net_gex_unsigned_A": call_gex_unsigned - put_gex_unsigned,
            "net_gex_unsigned_B": put_gex_unsigned - call_gex_unsigned,
        }

    while next_q is not None or next_t is not None:
        q_ts = int(next_q.ts_event) if next_q is not None else None
        t_ts = int(next_t.ts_event) if next_t is not None else None

        if t_ts is None or (q_ts is not None and q_ts <= t_ts):
            # Process quote
            try:
                iid = int(next_q.instrument_id)
                lvl = next_q.levels[0]
                br = int(lvl.bid_px)
                ar = int(lvl.ask_px)
                if br > 0 and ar > 0 and ar >= br:
                    nbbo_state[iid] = (br, ar)
                n_quotes += 1
            except (AttributeError, IndexError):
                pass

            # Snapshot when crossing second boundary
            if q_ts is not None:
                sec_ns = (q_ts // 1_000_000_000) * 1_000_000_000
                if last_processed_sec_ns is None:
                    last_processed_sec_ns = sec_ns
                elif sec_ns > last_processed_sec_ns:
                    row = snapshot_second(last_processed_sec_ns)
                    if row is not None:
                        results.append(row)
                    last_processed_sec_ns = sec_ns

            next_q = next(quote_iter, None)
        else:
            # Process trade
            try:
                ts = int(next_t.ts_event)
                iid = int(next_t.instrument_id)
                price = int(next_t.price)
                size = int(next_t.size)
                n_trades += 1

                if price > 0 and size > 0 and iid in iid_to_idx:
                    nbbo = nbbo_state.get(iid)
                    if nbbo:
                        br, ar = nbbo
                        mid = (br + ar) / 2.0
                        if price > mid:
                            sign = +1
                        elif price < mid:
                            sign = -1
                        else:
                            sign = prior_sign.get(iid, 0)
                        if sign != 0:
                            prior_sign[iid] = sign
                            idx = iid_to_idx[iid]
                            inventory_signed[idx]   += sign * size
                            inventory_unsigned[idx] += size  # unsigned: just add volume
                            n_classified += 1

                # Snapshot on second boundary
                sec_ns = (ts // 1_000_000_000) * 1_000_000_000
                if last_processed_sec_ns is None:
                    last_processed_sec_ns = sec_ns
                elif sec_ns > last_processed_sec_ns:
                    row = snapshot_second(last_processed_sec_ns)
                    if row is not None:
                        results.append(row)
                    last_processed_sec_ns = sec_ns
            except AttributeError:
                pass
            next_t = next(trade_iter, None)

        now = time.monotonic()
        if now - last_log >= 10:
            print(f"      quotes={n_quotes:,}  trades={n_trades:,}  "
                  f"classified={n_classified:,}  results={len(results):,}",
                  flush=True)
            last_log = now

    # Final snapshot
    if last_processed_sec_ns is not None:
        row = snapshot_second(last_processed_sec_ns)
        if row is not None:
            results.append(row)

    print(f"      Done in {time.monotonic()-t0:.1f}s")
    print(f"      Total: quotes={n_quotes:,}  trades={n_trades:,}  "
          f"classified={n_classified:,}")

    df = pd.DataFrame(results).set_index("second_ns").sort_index()

    # Compute first differences = gexoflow
    for col in [c for c in df.columns if c.startswith("net_gex_")]:
        df[col.replace("net_gex_", "gexoflow_")] = df[col].diff()

    print(f"      Output: {len(df)} seconds, columns: {df.columns.tolist()}")
    return df


# ── Validate against GexBot ───────────────────────────────────────────────────
def validate(rep: pd.DataFrame) -> None:
    print(f"\n[5/5] Validating against GexBot archive")
    rep.index = pd.to_datetime(rep.index, unit="ns", utc=True)

    gb = pd.read_parquet(GEXBOT_PATH)
    gb["ts_utc"] = gb["timestamp"].dt.tz_convert("UTC").dt.floor("s")
    gb = gb.set_index("ts_utc").sort_index()
    gb = gb[~gb.index.duplicated(keep="last")]

    flow_cols = [c for c in rep.columns if c.startswith("gexoflow_")]
    joined = rep[flow_cols].join(gb[["gexoflow"]], how="inner").dropna(
        subset=["gexoflow"])
    print(f"      Overlapping seconds: {len(joined)}")

    if len(joined) < 30:
        print("      ERROR: too few overlapping seconds")
        return

    gbot_std = joined["gexoflow"].std()
    print(f"      GexBot gexoflow std in this window: {gbot_std:.2f}")
    print(f"      (Daily std typical 200-500; this window is in low-signal zone)")

    if gbot_std == 0:
        print("      ERROR: zero variance — warmup zone")
        return

    print()
    print(f"  {'VARIANT':<25} {'CORR':>10} {'SIGN_AGREE':>11} {'STD_RATIO':>14}")
    print("  " + "─" * 64)

    best_corr = 0.0
    best_var = None
    for col in flow_cols:
        s = joined[col].dropna()
        gb_s = joined["gexoflow"].loc[s.index]
        if len(s) < 30 or s.std() == 0:
            print(f"  {col[9:]:<25} {'NaN':>10} {'-':>11} {'-':>14}")
            continue
        corr = s.corr(gb_s)
        sign_ag = (np.sign(s) == np.sign(gb_s)).mean()
        ratio = s.std() / gbot_std

        flag = "  ←" if pd.notna(corr) and abs(corr) > abs(best_corr) else ""
        print(f"  {col[9:]:<25} {corr:>+10.4f} {sign_ag:>10.1%} {ratio:>12.3e}x{flag}")

        if pd.notna(corr) and abs(corr) > abs(best_corr):
            best_corr = corr
            best_var = col[9:]

    print("  " + "─" * 64)
    print()
    print("=" * 64)
    if best_var is None:
        print("  RESULT: All variants returned NaN")
    elif abs(best_corr) > 0.4:
        print(f"  RESULT: STRONG ({best_var}, corr={best_corr:+.4f})")
        print(f"  Combined model works. Scale up to full 2-day pull ($47.94).")
        if best_corr < 0:
            print(f"  Sign convention is reversed — use inverse variant.")
    elif abs(best_corr) > 0.2:
        print(f"  RESULT: MODERATE ({best_var}, corr={best_corr:+.4f})")
        print(f"  Some signal — but the 10:00-10:05 window is intentionally low-signal.")
        print(f"  Worth testing on a higher-activity window before deciding.")
        print(f"  Cost to test 14:00-14:30 ET: ~$3.65 (trades + quotes for 30 min)")
    elif abs(best_corr) > 0.1:
        print(f"  RESULT: WEAK ({best_var}, corr={best_corr:+.4f})")
        print(f"  Marginal signal. Not strong enough to justify spending more.")
    else:
        print(f"  RESULT: NO SIGNAL (best={best_corr:+.4f})")
        print(f"  Combined model also fails. Walk away — pursue GexBot orderflow purchase.")
    print("=" * 64)


def main() -> None:
    print("=" * 70)
    print("COMBINED CUMULATIVE INVENTORY MODEL")
    print("Final replication test — uses only existing data, $0 cost")
    print("=" * 70)

    # Get window-mid spot for IV solving
    gb = pd.read_parquet(GEXBOT_PATH)
    ms = gb["timestamp"].astype("int64")
    ns = ms * 1_000_000
    gb["second_ns"] = (ns // 1_000_000_000) * 1_000_000_000
    mid_ts = pd.Timestamp(2026, 4, 22, 10, 2, 30, tzinfo=ET).tz_convert("UTC")
    mid_sec_ns = (int(mid_ts.value) // 1_000_000_000) * 1_000_000_000
    spot_lookup = gb.set_index("second_ns")["spot"].to_dict()
    avg_spot = spot_lookup.get(mid_sec_ns, gb["spot"].mean())
    print(f"  Window-mid spot (from GexBot archive, ES): {avg_spot:.2f}")
    print(f"  NOTE: GexBot displays SPX values but archives ES.")
    print(f"        Strikes will be slightly off-moneyness vs. their internal calc.")
    print()

    oi_df = load_oi()
    iv_lookup = compute_iv_per_strike(oi_df, avg_spot, mid_sec_ns)
    rep = compute_combined_model(oi_df, iv_lookup)

    out = SCRATCH_DIR / "combined_model_results.parquet"
    rep.to_parquet(out)
    print(f"\n[4/5] Saved: {out}")

    validate(rep)


if __name__ == "__main__":
    main()
