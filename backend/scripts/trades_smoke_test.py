"""
TRADES SMOKE TEST — Lee-Ready replication of GexBot gexoflow.

Hypothesis (from GexBot docs):
    gex_orderflow = (call_gex_imbalance) - (put_gex_imbalance)
where for each strike:
    imbalance_contribution = signed_volume × gamma × spot² × 100
and signed_volume comes from Lee-Ready classification:
    trade above mid  → +1 (aggressive buy / "long")
    trade below mid  → -1 (aggressive sell / "short")
    trade at mid     → use prior-tick rule

PIPELINE:
    1. Stream 5 min of OPRA trades from API to disk ($0.61, ~30 sec)
    2. Load OI metadata, get GexBot spot for the window
    3. Pre-compute gamma per strike (one IV per strike at window mid)
    4. Merge CMBP-1 quotes + trades streams by timestamp
    5. For each trade: classify via Lee-Ready, look up gamma, tally per second
    6. Validate per-second gex_orderflow against GexBot's archived gexoflow

VARIANTS TESTED:
    A: gex_orderflow = call_flow - put_flow   (per docs)
    B: gex_orderflow = put_flow - call_flow   (inverse, in case sign is reversed)

RUNTIME: ~5 min total at 350+ Mbps
COST:    $0.61
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

# ── Config ────────────────────────────────────────────────────────────────────
TARGET_DATE      = date(2026, 4, 22)
START_TIME       = "10:00"
END_TIME         = "10:05"
ET               = ZoneInfo("America/New_York")
PRICE_SCALE      = 1e-9
RISK_FREE_RATE   = 0.045
STRIKE_BAND_PCT  = 0.15
SECONDS_PER_YEAR = 365 * 24 * 3600
CONTRACT_MULT    = 100

# Paths
PROJECT_ROOT = Path("./backend")
SCRATCH_DIR  = PROJECT_ROOT / "data" / "repricer_scratch"
QUOTES_PATH  = SCRATCH_DIR / "smoke_cmbp1_apr22_1000_1005.dbn.zst"
TRADES_PATH  = SCRATCH_DIR / "smoke_trades_apr22_1000_1005.dbn.zst"
STATS_PATH   = PROJECT_ROOT / "data" / "opra_statistics_apr22_23.dbn.zst"
GEXBOT_PATH  = PROJECT_ROOT / "data" / "gex" / "2026-04-22.parquet"

# Expiry conventions
SPX_EXPIRY_HM  = (9, 30)
SPXW_EXPIRY_HM = (16, 0)

# IV solver
NEWTON_ITERS = 12
MIN_IV, MAX_IV = 0.01, 5.0


# ── Step 1: Stream OPRA trades ────────────────────────────────────────────────
def stream_trades() -> None:
    if TRADES_PATH.exists():
        size_mb = TRADES_PATH.stat().st_size / 1e6
        print(f"[1/6] Trades file exists ({size_mb:.1f} MB), skipping download")
        return

    print(f"[1/6] Streaming OPRA trades from API")
    print(f"      Window: {TARGET_DATE} {START_TIME}-{END_TIME} ET")
    print(f"      Cost:   $0.61")
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
    t0 = time.monotonic()
    print("      Calling Databento API...")
    client.timeseries.get_range(
        dataset  = "OPRA.PILLAR",
        schema   = "trades",
        symbols  = ["SPX.OPT", "SPXW.OPT"],
        stype_in = "parent",
        start    = s_utc.strftime("%Y-%m-%dT%H:%M:%S"),
        end      = e_utc.strftime("%Y-%m-%dT%H:%M:%S"),
        path     = str(TRADES_PATH),
    )
    elapsed = time.monotonic() - t0
    size_mb = TRADES_PATH.stat().st_size / 1e6
    print(f"      Done in {elapsed:.1f} sec. File size: {size_mb:.1f} MB")


# ── Step 2: Inspect first trade record (defensive) ───────────────────────────
def inspect_first_trade() -> dict:
    """Inspect the first trade record to confirm field paths before processing.
    Returns dict with field names we'll use for parsing."""
    print(f"\n[2/6] Inspecting first trade record schema")
    store = db.DBNStore.from_file(TRADES_PATH)
    for record in store:
        rtype = type(record).__name__
        print(f"      Record type: {rtype}")

        attrs_to_check = ["ts_event", "instrument_id", "price", "size", "side", "action"]
        found = {}
        for a in attrs_to_check:
            try:
                val = getattr(record, a)
                if not callable(val):
                    found[a] = val
                    print(f"      record.{a} = {val!r}")
            except AttributeError:
                print(f"      record.{a} = <MISSING>")

        return found

    raise RuntimeError("No records in trades file")


# ── Step 3: Load OI + symbol metadata ────────────────────────────────────────
def load_oi() -> pd.DataFrame:
    print(f"\n[3/6] Loading OI metadata")
    store = db.DBNStore.from_file(STATS_PATH)
    df = store.to_df()
    df = df[df["stat_type"] == 9].copy()
    df["date_et"] = df["ts_event"].dt.tz_convert("America/New_York").dt.date
    df = df[df["date_et"] == TARGET_DATE]
    df = (df.sort_values("ts_event").groupby("instrument_id").first().reset_index())

    parsed = df["symbol"].apply(_parse_symbol)
    df["root"]    = parsed.apply(lambda x: x["root"] if x else None)
    df["expiry"]  = parsed.apply(lambda x: x["expiry"] if x else None)
    df["opttype"] = parsed.apply(lambda x: x["type"] if x else None)
    df["strike"]  = parsed.apply(lambda x: x["strike"] if x else None)
    df["oi"]      = df["quantity"].astype(int)
    df = df.dropna(subset=["root", "expiry", "opttype", "strike"])
    df = df[df["oi"] > 0]
    df["expiry_ts_ns"] = df.apply(
        lambda r: _expiry_ts_ns(r["root"], r["expiry"]), axis=1
    )
    df["instrument_id"] = df["instrument_id"].astype("int32")
    df["is_call"] = (df["opttype"] == "c")

    print(f"      {len(df):,} active instruments with OI>0")
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
    return {"root": root, "expiry": date(2000 + yy, mm, dd),
            "type": opt, "strike": strike}


def _expiry_ts_ns(root: str, exp_date: date) -> int:
    h, m = SPX_EXPIRY_HM if root == "SPX" else SPXW_EXPIRY_HM
    ts = pd.Timestamp(exp_date.year, exp_date.month, exp_date.day, h, m, tzinfo=ET)
    return int(ts.tz_convert("UTC").value)


# ── Step 4: Pre-compute gamma per strike ─────────────────────────────────────
def precompute_gamma(oi_df: pd.DataFrame) -> dict:
    """
    For each instrument, compute its gamma at the mid-window spot using its
    NBBO mid as the IV input. Returns dict: instrument_id -> gamma.

    This is an approximation: we use one gamma value per strike for the entire
    5-min window. Acceptable for a smoke test since spot moves <0.5% over 5 min.
    """
    print(f"\n[4/6] Pre-computing gamma per strike")

    # Get spot at window midpoint from GexBot archive
    gb = pd.read_parquet(GEXBOT_PATH)
    ms_since_epoch = gb["timestamp"].astype("int64")
    ns_since_epoch = ms_since_epoch * 1_000_000
    gb["second_ns"] = (ns_since_epoch // 1_000_000_000) * 1_000_000_000

    sh, sm = [int(x) for x in START_TIME.split(":")]
    mid_h, mid_m = sh, sm + 2  # 2.5 min into the window
    mid_ts = pd.Timestamp(TARGET_DATE.year, TARGET_DATE.month, TARGET_DATE.day,
                           mid_h, mid_m, 30, tzinfo=ET).tz_convert("UTC")
    mid_ns = int(mid_ts.value)
    mid_sec_ns = (mid_ns // 1_000_000_000) * 1_000_000_000

    # Find closest spot snapshot
    spot_lookup = gb.set_index("second_ns")["spot"].to_dict()
    avg_spot = spot_lookup.get(mid_sec_ns)
    if avg_spot is None or avg_spot <= 0:
        # Fallback: average over the window
        avg_spot = float(gb["spot"].mean())
    print(f"      Window-mid spot: {avg_spot:.2f}")

    # Walk CMBP-1 quotes, capture NBBO mid per instrument at the END of the window
    # (gives us a representative NBBO for IV solving)
    print(f"      Walking CMBP-1 to capture per-strike NBBO mid...")
    nbbo_state: dict[int, tuple[int, int]] = {}
    store = db.DBNStore.from_file(QUOTES_PATH)
    for record in store:
        try:
            iid = int(record.instrument_id)
            lvl = record.levels[0]
            bid_r = int(lvl.bid_px)
            ask_r = int(lvl.ask_px)
        except (AttributeError, IndexError):
            continue
        if bid_r <= 0 or ask_r <= 0 or ask_r < bid_r:
            continue
        nbbo_state[iid] = (bid_r, ask_r)

    print(f"      NBBO captured for {len(nbbo_state):,} instruments")

    # Filter to instruments we have OI for AND in strike band
    valid_iids = []
    for iid in nbbo_state.keys():
        if iid not in oi_df.index:
            continue
        meta = oi_df.loc[iid]
        K = meta["strike"]
        if abs(K / avg_spot - 1.0) > STRIKE_BAND_PCT:
            continue
        valid_iids.append(iid)

    print(f"      Filtered to {len(valid_iids):,} strikes within ±{STRIKE_BAND_PCT*100:.0f}% of spot")

    # Build vectorized arrays
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

    iv = _iv_newton(mid_px[valid], S_arr[valid], K_arr[valid],
                     dte_years[valid], is_call_arr[valid])
    gamma = _gamma_safe(S_arr[valid], K_arr[valid], dte_years[valid], iv)

    # Build lookup dict: iid → gamma
    gamma_lookup = {}
    valid_iids_arr = np.array(valid_iids)
    for i, iid in enumerate(valid_iids_arr[valid]):
        if np.isfinite(gamma[i]) and gamma[i] > 0:
            gamma_lookup[int(iid)] = float(gamma[i])

    n_with_gamma = len(gamma_lookup)
    print(f"      Successfully computed gamma for {n_with_gamma:,} strikes")
    print(f"      Avg gamma: {np.mean(list(gamma_lookup.values())):.6f}")

    return {
        "gamma_per_iid": gamma_lookup,
        "avg_spot": avg_spot,
    }


def _iv_newton(price, S, K, T, is_call, r=RISK_FREE_RATE):
    sigma = np.sqrt(np.maximum(2*np.pi/T, 1e-6)) * (price / np.maximum(S, 1.0))
    sigma = np.clip(sigma, 0.05, 3.0)
    valid = (T > 0) & (price > 0) & (S > 0) & (K > 0)
    sigma = np.where(valid, sigma, np.nan)
    for _ in range(NEWTON_ITERS):
        with np.errstate(invalid="ignore", divide="ignore"):
            sqrtT = np.sqrt(T)
            d1 = (np.log(S/K) + (r + 0.5*sigma**2)*T) / (sigma*sqrtT)
            d2 = d1 - sigma*sqrtT
            call = S*norm.cdf(d1) - K*np.exp(-r*T)*norm.cdf(d2)
            put  = K*np.exp(-r*T)*norm.cdf(-d2) - S*norm.cdf(-d1)
            theo = np.where(is_call, call, put)
            v = S * sqrtT * norm.pdf(d1)
            step = np.where(v > 1e-6, (price - theo)/v, 0.0)
            sigma = np.clip(sigma + step, MIN_IV, MAX_IV)
    return sigma


def _gamma_safe(S, K, T, sig, r=RISK_FREE_RATE):
    with np.errstate(invalid="ignore", divide="ignore"):
        sqrtT = np.sqrt(T)
        d1 = (np.log(S/K) + (r + 0.5*sig**2)*T) / (sig*sqrtT)
        g = norm.pdf(d1) / (S * sig * sqrtT)
    return np.where(np.isfinite(g) & (sig > 0), g, 0.0)


# ── Step 5: Merge streams + Lee-Ready classify ───────────────────────────────
def compute_orderflow(oi_df: pd.DataFrame, gamma_data: dict) -> pd.DataFrame:
    print(f"\n[5/6] Merging quote+trade streams, classifying via Lee-Ready")

    gamma_per_iid = gamma_data["gamma_per_iid"]
    avg_spot = gamma_data["avg_spot"]
    spot_sq = avg_spot * avg_spot

    # is_call lookup (precomputed)
    is_call_per_iid = oi_df["is_call"].to_dict()

    # State
    nbbo_state: dict[int, tuple[int, int]] = {}
    prior_sign: dict[int, int] = {}

    # Per-second buckets — separate call and put flows
    sec_call_flow: dict[int, float] = {}
    sec_put_flow:  dict[int, float] = {}

    # Counters
    n_quotes = 0
    n_trades = 0
    n_classified = 0
    n_skipped_no_nbbo = 0
    n_skipped_no_gamma = 0
    n_skipped_at_mid_no_prior = 0

    quote_iter = iter(db.DBNStore.from_file(QUOTES_PATH))
    trade_iter = iter(db.DBNStore.from_file(TRADES_PATH))

    next_q = next(quote_iter, None)
    next_t = next(trade_iter, None)

    t0 = time.monotonic()
    last_log = t0

    while next_q is not None or next_t is not None:
        # Pick whichever has earlier timestamp
        q_ts = int(next_q.ts_event) if next_q is not None else None
        t_ts = int(next_t.ts_event) if next_t is not None else None

        if t_ts is None or (q_ts is not None and q_ts <= t_ts):
            # Process quote: update NBBO state
            try:
                iid = int(next_q.instrument_id)
                lvl = next_q.levels[0]
                bid_r = int(lvl.bid_px)
                ask_r = int(lvl.ask_px)
                if bid_r > 0 and ask_r > 0 and ask_r >= bid_r:
                    nbbo_state[iid] = (bid_r, ask_r)
                n_quotes += 1
            except (AttributeError, IndexError):
                pass
            next_q = next(quote_iter, None)
        else:
            # Process trade
            try:
                ts = int(next_t.ts_event)
                iid = int(next_t.instrument_id)
                price = int(next_t.price)
                size = int(next_t.size)
                n_trades += 1

                if price <= 0 or size <= 0:
                    next_t = next(trade_iter, None)
                    continue

                # Get NBBO at trade time
                nbbo = nbbo_state.get(iid)
                if not nbbo:
                    n_skipped_no_nbbo += 1
                    next_t = next(trade_iter, None)
                    continue
                bid_r, ask_r = nbbo

                # Lee-Ready classification
                mid = (bid_r + ask_r) / 2.0
                if price > mid:
                    sign = +1
                elif price < mid:
                    sign = -1
                else:
                    sign = prior_sign.get(iid, 0)
                    if sign == 0:
                        n_skipped_at_mid_no_prior += 1
                        next_t = next(trade_iter, None)
                        continue
                prior_sign[iid] = sign

                # Look up gamma
                gamma = gamma_per_iid.get(iid)
                if gamma is None:
                    n_skipped_no_gamma += 1
                    next_t = next(trade_iter, None)
                    continue

                # Compute contribution
                # imbalance_contribution = signed_volume × gamma × spot² × 100
                contribution = sign * size * gamma * spot_sq * CONTRACT_MULT

                sec_ns = (ts // 1_000_000_000) * 1_000_000_000

                if is_call_per_iid.get(iid, False):
                    sec_call_flow[sec_ns] = sec_call_flow.get(sec_ns, 0.0) + contribution
                else:
                    sec_put_flow[sec_ns] = sec_put_flow.get(sec_ns, 0.0) + contribution

                n_classified += 1
            except AttributeError:
                pass
            next_t = next(trade_iter, None)

        # Periodic progress
        now = time.monotonic()
        if now - last_log >= 10:
            print(f"      quotes={n_quotes:,}  trades={n_trades:,}  "
                  f"classified={n_classified:,}  "
                  f"skip_no_nbbo={n_skipped_no_nbbo:,}  "
                  f"skip_no_gamma={n_skipped_no_gamma:,}",
                  flush=True)
            last_log = now

    elapsed = time.monotonic() - t0
    print()
    print(f"      Done in {elapsed:.1f} sec")
    print(f"      Quotes processed:    {n_quotes:,}")
    print(f"      Trades processed:    {n_trades:,}")
    print(f"      Trades classified:   {n_classified:,}")
    print(f"      Skipped no NBBO:     {n_skipped_no_nbbo:,}")
    print(f"      Skipped no gamma:    {n_skipped_no_gamma:,}")
    print(f"      Skipped at-mid:      {n_skipped_at_mid_no_prior:,}")

    # Build per-second DataFrame
    all_secs = sorted(set(sec_call_flow.keys()) | set(sec_put_flow.keys()))
    rows = []
    for s in all_secs:
        cf = sec_call_flow.get(s, 0.0)
        pf = sec_put_flow.get(s, 0.0)
        rows.append({
            "second_ns":          s,
            "call_flow":          cf,
            "put_flow":           pf,
            "gex_orderflow_A":    cf - pf,    # per docs
            "gex_orderflow_B":    pf - cf,    # inverse
        })
    df = pd.DataFrame(rows).set_index("second_ns").sort_index()
    print(f"      Per-second rows: {len(df)}")
    return df


# ── Step 6: Validate against GexBot ──────────────────────────────────────────
def validate(rep: pd.DataFrame) -> None:
    print(f"\n[6/6] Validating against GexBot archive")
    rep.index = pd.to_datetime(rep.index, unit="ns", utc=True)

    gb = pd.read_parquet(GEXBOT_PATH)
    gb["ts_utc"] = gb["timestamp"].dt.tz_convert("UTC").dt.floor("s")
    gb = gb.set_index("ts_utc").sort_index()
    gb = gb[~gb.index.duplicated(keep="last")]

    joined = rep.join(gb[["gexoflow"]], how="inner").dropna()
    print(f"      Overlapping seconds: {len(joined)}")

    if len(joined) < 30:
        print("      ERROR: too few overlapping seconds")
        return

    gbot_std = joined["gexoflow"].std()
    if gbot_std == 0 or pd.isna(gbot_std):
        print("      ERROR: GexBot gexoflow has zero variance over this window")
        print("      (Likely warmup zone — re-pick a window after 9:35:49 ET)")
        return

    print()
    print(f"  {'VARIANT':<6} {'CORR':>10} {'SIGN_AGREE':>11} "
          f"{'REP_STD':>16} {'GBOT_STD':>10} {'STD_RATIO':>12}")
    print("  " + "─" * 70)

    best_corr = 0.0
    best_var = None

    for col, label in [("gex_orderflow_A", "A (call-put, per docs)"),
                        ("gex_orderflow_B", "B (put-call, inverse)")]:
        s = joined[col].dropna()
        gb_s = joined["gexoflow"].loc[s.index]
        if len(s) < 30 or s.std() == 0:
            print(f"  {col[-1]:<6} {'NaN':>10} {'-':>11} "
                  f"{'-':>16} {gbot_std:>10.2f} {'-':>12}")
            continue
        corr = s.corr(gb_s)
        sign_ag = (np.sign(s) == np.sign(gb_s)).mean()
        ratio = s.std() / gbot_std

        print(f"  {col[-1]:<6} {corr:>+10.4f} {sign_ag:>10.1%} "
              f"{s.std():>16,.2f} {gbot_std:>10.2f} {ratio:>12.3e}x")

        if pd.notna(corr) and abs(corr) > abs(best_corr):
            best_corr = corr
            best_var = col[-1]

    print("  " + "─" * 70)
    print()

    print("=" * 60)
    if best_var is None:
        print("  VERDICT: BOTH VARIANTS FAILED")
        print("  No correlation could be computed. Check pipeline.")
    elif abs(best_corr) > 0.5:
        print(f"  VERDICT: STRONG SIGNAL (variant {best_var}, corr={best_corr:+.4f})")
        print("  Lee-Ready replication is viable. Recommend full 2-day pull ($47.94).")
        if best_corr < 0:
            print("  NOTE: best correlation is NEGATIVE — sign convention reversed.")
    elif abs(best_corr) > 0.3:
        print(f"  VERDICT: MODERATE SIGNAL (variant {best_var}, corr={best_corr:+.4f})")
        print("  Methodology partially right. Tune before committing.")
        print("  Possible refinements: per-second gamma, volume>OI filter,")
        print("  Databento `side` field instead of Lee-Ready price-vs-mid.")
    elif abs(best_corr) > 0.15:
        print(f"  VERDICT: WEAK SIGNAL (variant {best_var}, corr={best_corr:+.4f})")
        print("  Some signal but methodology has issues. Diagnose before spending.")
    else:
        print(f"  VERDICT: NO SIGNAL (best corr={best_corr:+.4f})")
        print("  Lee-Ready replication does not match GexBot's gexoflow at this scale.")
        print("  Likely they use proprietary classification beyond simple price-vs-mid.")
        print("  RECOMMEND: stop replication, pursue GexBot orderflow purchase.")
    print("=" * 60)


def main() -> None:
    print("=" * 70)
    print("OPRA TRADES SMOKE TEST — Lee-Ready replication of gexoflow")
    print("=" * 70)
    print(f"  Window:  {TARGET_DATE} {START_TIME}-{END_TIME} ET")
    print(f"  Cost:    $0.61")
    print()

    stream_trades()
    inspect_first_trade()
    oi_df = load_oi()
    gamma_data = precompute_gamma(oi_df)
    rep = compute_orderflow(oi_df, gamma_data)

    out = SCRATCH_DIR / "trades_smoke_results.parquet"
    rep.to_parquet(out)
    print(f"\n  Saved: {out}")

    validate(rep)


if __name__ == "__main__":
    main()
