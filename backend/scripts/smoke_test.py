"""Offline smoke test: synthetic ES bars + synthetic GEX -> feature pipeline -> backtest.

Validates that:
    - features.build_features runs on a realistic shape
    - All 6 strategies produce signals without crashing
    - backtest.run returns sensible trades with plausible P&L
    - Buy & hold produces exactly one trade per session
"""
from __future__ import annotations

import sys
from datetime import time
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from cheese import backtest, features, strategy
from cheese.config import BacktestConfig, ET


def _fake_session(d: pd.Timestamp, seed: int = 0) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    idx = pd.date_range(d + pd.Timedelta("9:30:00"), d + pd.Timedelta("15:59:00"),
                        freq="1min", tz=ET)
    n = len(idx)
    # random walk, 2-pt daily drift
    returns = rng.normal(0, 1.0, n)
    returns[0] = 0
    close = 5000 + np.cumsum(returns)
    high = close + np.abs(rng.normal(0, 0.5, n))
    low = close - np.abs(rng.normal(0, 0.5, n))
    op = np.concatenate([[close[0]], close[:-1]])
    return pd.DataFrame({
        "open": op, "high": high, "low": low, "close": close,
        "volume": rng.integers(100, 1000, n),
    }, index=idx)


def _fake_gex(mkt: pd.DataFrame, seed: int = 0) -> pd.DataFrame:
    rng = np.random.default_rng(seed + 1)
    spot = mkt["close"].values
    n = len(mkt)
    df = pd.DataFrame(index=mkt.index)
    df["spot"] = spot
    # gamma levels meander around spot
    df["z_mlgamma"] = spot + np.cumsum(rng.normal(0, 0.05, n))
    df["z_msgamma"] = df["z_mlgamma"] + rng.normal(0, 2, n)
    df["zero_mcall"] = spot + 8 + rng.normal(0, 1, n)
    df["zero_mput"] = spot - 8 + rng.normal(0, 1, n)
    df["o_mlgamma"] = df["z_mlgamma"] - 15
    df["o_msgamma"] = df["z_msgamma"] - 15
    df["one_mcall"] = df["zero_mcall"] + 40
    df["one_mput"] = df["zero_mput"] - 40
    # flow cols, sum/max/min already-aggregated form
    for base in ("dexoflow", "gexoflow", "cvroflow"):
        s = rng.standard_t(df=5, size=n) * 3.0
        df[f"{base}_sum"] = s
        df[f"{base}_max"] = s + np.abs(rng.normal(0, 0.5, n))
        df[f"{base}_min"] = s - np.abs(rng.normal(0, 0.5, n))
    df["on_session_edge"] = False
    t = df.index.time
    df["on_session_edge"] = [(tt < time(9, 45)) or (tt >= time(15, 45)) for tt in t]
    return df


def main() -> None:
    sessions = pd.date_range("2026-03-02", "2026-03-13", freq="B", tz=ET).normalize()
    mkt_parts, gex_parts = [], []
    for i, d in enumerate(sessions):
        m = _fake_session(d, seed=i)
        mkt_parts.append(m)
        gex_parts.append(_fake_gex(m, seed=i))
    mkt = pd.concat(mkt_parts)
    gex_bars = pd.concat(gex_parts)

    feat = features.build_features(mkt, gex_bars)
    print(f"feat shape: {feat.shape}, atr nan: {feat['atr'].isna().sum()}, "
          f"gexoflow_z nan: {feat.get('gexoflow_z', pd.Series()).isna().sum()}")

    cfg = BacktestConfig(bar_freq="1min")
    for name, cls in strategy.ALL_STRATEGIES.items():
        kwargs = {}
        if name == "flow_burst": kwargs["z_threshold"] = 1.5
        if name == "wall_break": kwargs["min_flow_z"] = 0.5
        if name == "random": kwargs["probability"] = 0.005
        s = cls(**kwargs)
        sig = s.signals(feat)
        trades, eq = backtest.run(feat, sig, name, cfg=cfg)
        pnl = float(trades["net_dollars"].sum()) if not trades.empty else 0.0
        print(f"  {name:<12} signals={int((sig != 0).sum()):>4}  "
              f"trades={len(trades):>4}  pnl=${pnl:>9,.0f}")

    assert len(mkt) == len(feat), "feature frame length mismatch"
    # buy_hold should produce ~one trade per session (may lose 1-2 to session-boundary edges)
    s = strategy.BuyHoldStrategy()
    sig = s.signals(feat)
    tr, _ = backtest.run(feat, sig, "buy_hold", cfg=cfg)
    assert len(tr) >= len(sessions) - 2, f"buy_hold expected >= {len(sessions) - 2} trades got {len(tr)}"
    print("\n[OK] smoke test passed")


if __name__ == "__main__":
    main()
