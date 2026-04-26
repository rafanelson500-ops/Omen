"""Streamlit dashboard for the cheese backtester.

Run:
    cd backend
    streamlit run app.py
"""
from __future__ import annotations

from datetime import date, time
from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

from cheese import backtest, features, gex, market, metrics, strategy
from cheese.config import BacktestConfig, CostModel, ExitConfig

st.set_page_config(page_title="Cheese | GEX Backtester", layout="wide", page_icon=None)

STRAT_DISPLAY = {
    "flow_burst": "Flow Burst",
    "wall_reject": "Wall Reject",
    "wall_break": "Wall Break",
    "regime_flip": "Regime Flip",
    "random": "Random (baseline)",
    "buy_hold": "Buy & Hold (baseline)",
}


# ---------- Cached data layer ----------------------------------------------
@st.cache_data(show_spinner="loading ES bars...")
def _load_mkt(start: date, end: date, freq: str) -> pd.DataFrame:
    return market.load(start, end, freq=freq, rth_only=True)


@st.cache_data(show_spinner="loading ES bars (live cache)...")
def _load_mkt_live_day(day: date, freq: str) -> pd.DataFrame:
    return market.load_live_day(day, freq=freq, rth_only=True)


@st.cache_data(show_spinner="loading GEX...")
def _load_gex(days_tuple: tuple[str, ...], freq: str) -> pd.DataFrame:
    days = [date.fromisoformat(d) for d in days_tuple]
    raw = gex.load_range(days)
    if raw.empty:
        return raw
    return gex.resample(raw, freq=freq)


@st.cache_data(show_spinner="building features...")
def _build_feat(mkt_key: str, gex_key: str, mkt: pd.DataFrame, gx: pd.DataFrame) -> pd.DataFrame:
    return features.build_features(mkt, gx)


@st.cache_data(show_spinner=False)
def _run_buy_hold_baseline(mkt: pd.DataFrame, commission: float, slip_ticks: float) -> tuple[pd.DataFrame, pd.Series]:
    from cheese.config import ES_POINT_VALUE, ES_TICK_SIZE
    slip_pts = slip_ticks * ES_TICK_SIZE
    
    trades = []
    daily_times = []
    daily_pnl = []
    
    for d, df_day in mkt.groupby(mkt.index.date):
        if df_day.empty:
            continue
        first_bar = df_day.iloc[0]
        last_bar = df_day.iloc[-1]
        
        entry_px = float(first_bar["open"] + slip_pts)
        exit_px = float(last_bar["close"] - slip_pts)
        
        pts = exit_px - entry_px
        gross_usd = pts * ES_POINT_VALUE
        commission_usd = 2 * commission
        # Friction is commission + 2 * slippage cost
        friction_total_usd = commission_usd + 2 * slip_pts * ES_POINT_VALUE
        net_usd = gross_usd - commission_usd
        
        trades.append({
            "strategy": "buy_hold",
            "side": 1,
            "entry_time": df_day.index[0],
            "entry_px": entry_px,
            "exit_time": df_day.index[-1],
            "exit_px": exit_px,
            "exit_reason": "session_close",
            "bars_held": len(df_day),
            "stop_px": 0.0,
            "target_px": 0.0,
            "atr_at_entry": 0.0,
            "gamma_regime": "unknown",
            "gross_points": float(pts),
            "gross_dollars": float(gross_usd),
            "cost_dollars": float(friction_total_usd),
            "net_dollars": float(net_usd),
        })
        daily_pnl.append(net_usd)
        daily_times.append(df_day.index[-1])
        
    trades_df = pd.DataFrame(trades)
    if trades_df.empty:
        trades_df = pd.DataFrame(columns=[
            "strategy", "side", "entry_time", "entry_px", "exit_time", "exit_px",
            "exit_reason", "bars_held", "stop_px", "target_px", "atr_at_entry",
            "gamma_regime", "gross_points", "gross_dollars", "cost_dollars", "net_dollars"
        ])
        return trades_df, pd.Series(dtype="float64")
        
    eq = pd.Series(daily_pnl, index=daily_times).cumsum()
    return trades_df, eq


@st.cache_data(show_spinner=False)
def _run_strategy(
    strat_name: str, params: dict, feat_key: str, feat: pd.DataFrame, freq: str,
    cost_commission: float, cost_slip_ticks: float,
    stop_mult: float, tgt_mult: float, trail_r: float, time_min: int,
    trade_start_time: time | None = None,
) -> tuple[pd.DataFrame, pd.Series]:
    strat = strategy.ALL_STRATEGIES[strat_name](**params)
    sig = strat.signals(feat)
    
    if trade_start_time is not None:
        mask = feat.index.time < trade_start_time
        sig.loc[mask] = 0

    cfg = BacktestConfig(
        bar_freq=freq,
        cost=CostModel(commission_per_side=cost_commission,
                       slippage_ticks_per_side=cost_slip_ticks),
        exits=ExitConfig(stop_atr_mult=stop_mult, target_atr_mult=tgt_mult,
                         trail_after_r=trail_r, time_stop_min=time_min),
    )
    return backtest.run(feat, sig, strategy_name=strat_name, cfg=cfg)


# ---------- Sidebar --------------------------------------------------------
st.sidebar.header("Run")

mode = st.sidebar.radio(
    "data source",
    ["Historical range", "Single day (live cache)"],
    index=0,
    help=(
        "Historical range: uses cached Databento pulls + GEXbot historical per-day files.\n"
        "Single day: uses data/market_live/<date>.parquet + data/gex/<date>.parquet "
        "written by the data daemon."
    ),
)
freq = st.sidebar.radio("bar frequency", ["1min", "5min"], index=1, horizontal=True)

single_day: date | None = None
if mode == "Single day (live cache)":
    live_days = market.live_day_available()
    gex_days = {date.fromisoformat(p.stem) for p in gex.GEX_CACHE.glob("*.parquet")}
    candidates = sorted([d for d in live_days if d in gex_days], reverse=True)
    if not candidates:
        st.sidebar.error(
            "no day has both data/market_live/<d>.parquet and data/gex/<d>.parquet. "
            "run the data daemon first."
        )
        st.stop()
    single_day = st.sidebar.selectbox(
        "session",
        candidates,
        index=0,
        format_func=lambda d: d.isoformat(),
    )
    available_days = [single_day]
    start, end = single_day, single_day
    st.sidebar.caption(f"{single_day}  (1 session, live cache)")
else:
    default_days = 14
    n_days = st.sidebar.slider("trading days back", 5, 120, default_days, step=1)
    available_days = gex.last_n_sessions(n_days)
    if not available_days:
        st.sidebar.error("no trading days available")
        st.stop()
    start, end = available_days[0], available_days[-1]
    st.sidebar.caption(f"{start} -> {end}  ({len(available_days)} sessions)")

st.sidebar.markdown("---")
st.sidebar.header("Strategy")
selected = ["flow_burst"]

with st.sidebar.expander("Flow Burst params", expanded=True):
    z_thresh = st.slider("z_threshold", 1.0, 4.0, 2.0, 0.1)

st.sidebar.markdown("---")
st.sidebar.header("Trading Window")
trade_start_time = st.sidebar.time_input("start time (ET)", value=time(9, 30))

st.sidebar.markdown("---")
st.sidebar.header("Risk / Exits")
stop_mult = st.sidebar.slider("stop ATR mult", 0.5, 4.0, 1.0, 0.1)
tgt_mult = st.sidebar.slider("target ATR mult", 0.5, 8.0, 6.0, 0.1)
trail_r = st.sidebar.slider("trail after R (0=off)", 0.0, 2.0, 0.0, 0.25)
time_min = st.sidebar.slider("time stop (minutes)", 5, 180, 25, 5)

st.sidebar.markdown("---")
st.sidebar.header("Costs")
commission = st.sidebar.number_input("commission per side ($)", 0.0, 10.0, 2.50, 0.1)
slip_ticks = st.sidebar.number_input("slippage per side (ticks)", 0.0, 4.0, 0.5, 0.25)

# ---------- Load data ------------------------------------------------------
st.title("Cheese: GEX ES Backtester")
st.caption("GEXbot orderflow + ES.c.0 Databento 1s -> resampled bars -> ATR stop/target engine with realistic costs")

try:
    if single_day is not None:
        mkt = _load_mkt_live_day(single_day, freq)
    else:
        mkt = _load_mkt(start, end, freq)
except FileNotFoundError as e:
    st.error(str(e))
    if single_day is not None:
        st.info("make sure the data daemon has written data/market_live/<date>.parquet")
    else:
        st.info("run `python scripts/fetch_market.py --days 80` first")
    st.stop()

gex_bars = _load_gex(tuple(d.isoformat() for d in available_days), freq)
if gex_bars.empty:
    if single_day is not None:
        st.error(f"no GEX parquet for {single_day} at data/gex/{single_day}.parquet")
    else:
        st.error("no GEX parquet cached. run `python scripts/fetch_gex.py --days 80`")
    st.stop()

feat_key = f"{start}_{end}_{freq}_{len(mkt)}_{len(gex_bars)}"
feat = _build_feat(f"mkt:{start}:{end}:{freq}", f"gx:{start}:{end}:{freq}", mkt, gex_bars)

c1, c2, c3, c4 = st.columns(4)
c1.metric("ES bars", f"{len(mkt):,}")
c2.metric("GEX bars", f"{len(gex_bars):,}")
c3.metric("Sessions", f"{len(available_days)}")
c4.metric("First GEX col", next((c for c in gex_bars.columns if c.startswith("z_")), "--"))


# ---------- Run all selected strategies ------------------------------------
def _params(name: str) -> dict:
    if name == "flow_burst":
        return {"z_threshold": z_thresh}
    return {}


results: dict[str, tuple[pd.DataFrame, pd.Series, dict]] = {}
with st.spinner("running backtests..."):
    for s_name in selected:
        if s_name == "buy_hold":
            continue
        trades, equity = _run_strategy(
            s_name, _params(s_name), feat_key, feat, freq,
            commission, slip_ticks, stop_mult, tgt_mult, trail_r, int(time_min),
            trade_start_time,
        )
        summ = metrics.summarize(trades, equity)
        results[s_name] = (trades, equity, summ)

    # Always include intraday buy & hold baseline
    bh_trades, bh_equity = _run_buy_hold_baseline(mkt, commission, slip_ticks)
    bh_summ = metrics.summarize(bh_trades, bh_equity)
    results["buy_hold"] = (bh_trades, bh_equity, bh_summ)


# ---------- Overview tab ---------------------------------------------------
tab_overview, tab_detail, tab_features, tab_trades = st.tabs(
    ["Overview", "Per-Strategy", "Features", "Trades"]
)

with tab_overview:
    st.subheader("Equity curves")
    fig = go.Figure()
    for name, (_, eq, _) in results.items():
        if eq.empty:
            continue
        fig.add_trace(go.Scatter(x=eq.index, y=eq.values, mode="lines", name=STRAT_DISPLAY[name]))
    fig.update_layout(height=420, margin=dict(l=0, r=0, t=10, b=0),
                      yaxis_title="$ P&L (cum)", hovermode="x unified")
    st.plotly_chart(fig, use_container_width=True)

    st.subheader("Headline metrics")
    rows = []
    for name, (_, _, summ) in results.items():
        rows.append({"strategy": STRAT_DISPLAY[name], **summ})
    df_sum = pd.DataFrame(rows).set_index("strategy")
    st.dataframe(
        df_sum.style.format({
            "win_rate": "{:.1%}", "avg_win": "${:,.2f}", "avg_loss": "${:,.2f}",
            "expectancy": "${:,.2f}", "profit_factor": "{:,.2f}",
            "total_pnl": "${:,.0f}", "total_cost": "${:,.0f}",
            "sharpe_daily": "{:,.2f}", "max_drawdown": "${:,.0f}",
            "avg_bars_held": "{:,.1f}", "ann_pnl_est": "${:,.0f}",
        }),
        use_container_width=True,
    )


with tab_detail:
    if not results:
        st.info("run at least one strategy")
    else:
        which = st.selectbox("strategy", list(results.keys()), format_func=lambda k: STRAT_DISPLAY.get(k, k))
        trades, equity, summ = results[which]

        c1, c2, c3, c4, c5 = st.columns(5)
        c1.metric("trades", summ["trades"])
        c2.metric("win rate", f"{summ['win_rate']:.1%}")
        c3.metric("expectancy", f"${summ['expectancy']:,.2f}")
        c4.metric("total P&L", f"${summ['total_pnl']:,.0f}")
        c5.metric("max DD", f"${summ['max_drawdown']:,.0f}")

        if equity.empty or trades.empty:
            st.info("no trades.")
        else:
            eq_fig = make_subplots(rows=2, cols=1, shared_xaxes=True, row_heights=[0.65, 0.35],
                                   vertical_spacing=0.05,
                                   subplot_titles=("Equity", "Drawdown"))
            eq_fig.add_trace(go.Scatter(x=equity.index, y=equity.values, name="equity"), row=1, col=1)
            peak = equity.cummax()
            dd = equity - peak
            eq_fig.add_trace(go.Scatter(x=dd.index, y=dd.values, name="dd", fill="tozeroy",
                                        line=dict(color="crimson")), row=2, col=1)
            eq_fig.update_layout(height=500, showlegend=False, margin=dict(l=0, r=0, t=30, b=0))
            st.plotly_chart(eq_fig, use_container_width=True)

            daily = metrics.per_day_pnl(equity)
            if not daily.empty:
                bar = px.bar(daily, title="Daily P&L")
                bar.update_layout(height=250, showlegend=False, margin=dict(l=0, r=0, t=30, b=0))
                st.plotly_chart(bar, use_container_width=True)

            col_a, col_b = st.columns(2)
            with col_a:
                st.markdown("**By regime**")
                st.dataframe(metrics.regime_breakdown(trades), use_container_width=True)
            with col_b:
                st.markdown("**By exit reason**")
                st.dataframe(metrics.exit_reason_breakdown(trades), use_container_width=True)


with tab_features:
    st.subheader("Flow z-score distribution")
    flow_cols = [c for c in ("gexoflow_z", "dexoflow_z", "cvroflow_z") if c in feat.columns]
    if not flow_cols:
        st.info("no flow z-scores (not enough lookback yet?)")
    else:
        col = st.selectbox("column", flow_cols)
        hist = px.histogram(feat, x=col, nbins=120, title=col)
        hist.update_layout(height=360, margin=dict(l=0, r=0, t=30, b=0))
        st.plotly_chart(hist, use_container_width=True)

    st.subheader("Spot vs walls (one session)")
    if not feat.empty:
        session = st.selectbox("session", sorted({d.date() for d in feat.index}, reverse=True))
        s = feat[feat.index.date == session]
        if not s.empty:
            fig = go.Figure()
            fig.add_trace(go.Scatter(x=s.index, y=s["close"], name="ES close", line=dict(color="black")))
            for col, color in [("z_mlgamma", "royalblue"), ("zero_mcall", "seagreen"),
                               ("zero_mput", "firebrick"), ("z_msgamma", "darkorange")]:
                if col in s.columns:
                    fig.add_trace(go.Scatter(x=s.index, y=s[col], name=col, line=dict(dash="dot", color=color)))
            fig.update_layout(height=480, margin=dict(l=0, r=0, t=10, b=0), hovermode="x unified")
            st.plotly_chart(fig, use_container_width=True)


with tab_trades:
    if not results:
        st.info("run at least one strategy")
    else:
        rows = []
        for name, (trades, _, _) in results.items():
            if not trades.empty:
                trades = trades.copy()
                trades.insert(0, "strategy_name", STRAT_DISPLAY.get(name, name))
                rows.append(trades)
        if rows:
            all_trades = pd.concat(rows, ignore_index=True)
            st.dataframe(all_trades, use_container_width=True, height=600)
            csv = all_trades.to_csv(index=False).encode()
            st.download_button("download trades CSV", csv, file_name="trades.csv")
        else:
            st.info("no trades across selected strategies.")
