"""Streamlit dashboard for the cheese backtester.

Run:
    cd backend
    streamlit run app.py
"""
from __future__ import annotations

from datetime import date, time
from pathlib import Path

import pandas as pd
import numpy as np
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
def _run_buy_hold_baseline(mkt: pd.DataFrame, commission: float, slip_ticks: float, instrument: str = "ES", static_quantity: int = 1) -> tuple[pd.DataFrame, pd.Series]:
    from cheese.config import INSTRUMENTS
    inst = INSTRUMENTS.get(instrument, INSTRUMENTS["ES"])
    slip_pts = slip_ticks * inst.tick_size
    
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
        gross_usd = pts * inst.point_value * static_quantity
        commission_usd = 2 * commission * static_quantity
        # Friction is commission + 2 * slippage cost
        friction_total_usd = commission_usd + 2 * slip_pts * inst.point_value * static_quantity
        net_usd = gross_usd - commission_usd
        
        trades.append({
            "strategy": "buy_hold",
            "side": 1,
            "contracts": static_quantity,
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
            "strategy", "side", "contracts", "entry_time", "entry_px", "exit_time", "exit_px",
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
    instrument: str = "ES", sizing_mode: str = "static", static_quantity: int = 1,
    account_size: float = 100000.0, kelly_fraction: float = 1.0,
) -> tuple[pd.DataFrame, pd.Series]:
    strat = strategy.ALL_STRATEGIES[strat_name](**params)
    sig = strat.signals(feat)
    
    if trade_start_time is not None:
        mask = feat.index.time < trade_start_time
        sig.loc[mask] = 0

    cfg = BacktestConfig(
        bar_freq=freq,
        instrument=instrument,
        sizing_mode=sizing_mode,
        static_quantity=static_quantity,
        account_size=account_size,
        kelly_fraction=kelly_fraction,
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
st.sidebar.header("Instrument & Sizing")
instrument = st.sidebar.radio("instrument", ["ES", "MES"], index=0, horizontal=True)

sizing_mode = st.sidebar.radio("sizing mode", ["static", "kelly"], index=0, horizontal=True)
if sizing_mode == "kelly":
    account_size = st.sidebar.number_input("account size ($)", 1000.0, 1000000.0, 100000.0, 5000.0)
    kelly_fraction = st.sidebar.slider("kelly fraction", 0.05, 1.0, 0.25, 0.05)
    static_quantity = 1
else:
    static_quantity = st.sidebar.number_input("lot size (contracts)", 1, 100, 1, 1)
    account_size = 100000.0
    kelly_fraction = 1.0

st.sidebar.markdown("---")
st.sidebar.header("Risk / Exits")
stop_mult = st.sidebar.slider("stop ATR mult", 0.5, 4.0, 1.0, 0.1)
tgt_mult = st.sidebar.slider("target ATR mult", 0.5, 8.0, 6.0, 0.1)
trail_r = st.sidebar.slider("trail after R (0=off)", 0.0, 2.0, 0.0, 0.25)
time_min = st.sidebar.slider("time stop (minutes)", 5, 180, 25, 5)

st.sidebar.markdown("---")
st.sidebar.header("Costs")
default_comm = 2.50 if instrument == "ES" else 0.65
commission = st.sidebar.number_input("commission per side ($)", 0.0, 10.0, default_comm, 0.05)
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
            trade_start_time, instrument, sizing_mode, static_quantity, account_size, kelly_fraction,
        )
        summ = metrics.summarize(trades, equity)
        results[s_name] = (trades, equity, summ)

    # Always include intraday buy & hold baseline
    bh_trades, bh_equity = _run_buy_hold_baseline(mkt, commission, slip_ticks, instrument=instrument, static_quantity=static_quantity)
    bh_summ = metrics.summarize(bh_trades, bh_equity)
    results["buy_hold"] = (bh_trades, bh_equity, bh_summ)


# ---------- Overview tab ---------------------------------------------------
tab_overview, tab_detail, tab_features, tab_robustness, tab_trades = st.tabs(
    ["Overview", "Per-Strategy", "Features", "Monte Carlo / Prop Firm", "Trades"]
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
            "mc_drawdown_95": "${:,.0f}", "p_value": "{:.3f}",
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

        st.markdown("---")
        st.subheader(f"Robustness: {summ.get('robustness_label', 'Unknown')}")
        r1, r2, r3 = st.columns(3)
        r1.metric("Monte Carlo 95% DD", f"${summ.get('mc_drawdown_95', 0):,.0f}")
        r2.metric("Permutation p-value", f"{summ.get('p_value', 1.0):.3f}")
        r3.metric("Label", summ.get("robustness_label", "Unknown"))
        st.markdown("---")

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


with tab_robustness:
    if not results:
        st.info("run at least one strategy")
    else:
        # Filter out buy_hold from selection (no point bootstrapping a baseline)
        strat_choices = [k for k in results.keys() if k != "buy_hold"]
        if not strat_choices:
            st.info("no strategy results available")
        else:
            chosen = st.selectbox(
                "strategy to bootstrap",
                strat_choices,
                format_func=lambda k: STRAT_DISPLAY.get(k, k),
                key="bootstrap_strategy",
            )
            chosen_trades, _, _ = results[chosen]

            if chosen_trades.empty or len(chosen_trades) < 10:
                st.warning("need at least 10 trades to run a meaningful bootstrap.")
            else:
                # ----- Settings -----
                st.markdown("### Settings")
                s1, s2, s3 = st.columns(3)
                n_iter = s1.number_input("iterations", 200, 20000, 2000, 200,
                                         help="More iterations = smoother distributions but slower.")
                n_days_total = chosen_trades["entry_time"].apply(lambda t: t.date()).nunique()
                n_days_sim = s2.number_input(
                    "trading days per simulation", 1, 500, int(n_days_total), 1,
                    help=f"How many trading days each simulated equity path covers. Default = backtest length ({n_days_total}).",
                )
                show_paths = s3.number_input("sample paths to plot", 10, 500, 100, 10)

                # ----- Run bootstrap -----
                with st.spinner("running daily-block bootstrap..."):
                    bs = metrics.daily_block_bootstrap(
                        chosen_trades, n_iter=int(n_iter), n_days=int(n_days_sim),
                    )

                # ----- Distribution metrics -----
                st.markdown("---")
                st.subheader("Distribution of outcomes")
                fr = bs["final_returns"]
                dd = bs["max_drawdowns"]
                ev = bs["ev_per_trade"]

                d1, d2, d3, d4 = st.columns(4)
                d1.metric("median return", f"${np.median(fr):,.0f}",
                          delta=f"P(profit) = {(fr > 0).mean():.1%}")
                d2.metric("5th pct return", f"${np.percentile(fr, 5):,.0f}")
                d3.metric("median max DD", f"${np.median(dd):,.0f}")
                d4.metric("5th pct max DD", f"${np.percentile(dd, 5):,.0f}",
                          help="Worst 5% (most negative) drawdown across all simulations.")

                hist_fig = make_subplots(rows=1, cols=3,
                                         subplot_titles=("Final Return $", "Max Drawdown $", "EV / trade $"))
                hist_fig.add_trace(go.Histogram(x=fr, nbinsx=60, name="return",
                                                marker_color="seagreen"), row=1, col=1)
                hist_fig.add_trace(go.Histogram(x=dd, nbinsx=60, name="dd",
                                                marker_color="crimson"), row=1, col=2)
                hist_fig.add_trace(go.Histogram(x=ev, nbinsx=60, name="ev",
                                                marker_color="royalblue"), row=1, col=3)
                hist_fig.update_layout(height=320, showlegend=False,
                                       margin=dict(l=0, r=0, t=40, b=0))
                st.plotly_chart(hist_fig, use_container_width=True)

                # ----- Spaghetti chart -----
                st.markdown("---")
                st.subheader("Sample equity paths (daily-block bootstrap)")
                tp = bs["trade_paths"]
                k = min(int(show_paths), tp.shape[0])
                rng = np.random.default_rng(0)
                idx_sample = rng.choice(tp.shape[0], size=k, replace=False)
                spaghetti = go.Figure()
                for i in idx_sample:
                    p = tp[i]
                    spaghetti.add_trace(go.Scatter(
                        y=p, mode="lines", showlegend=False,
                        line=dict(width=1, color="rgba(80,120,200,0.18)"),
                        hoverinfo="skip",
                    ))
                # overlay median
                med = np.nanmedian(tp, axis=0)
                spaghetti.add_trace(go.Scatter(y=med, mode="lines", name="median path",
                                               line=dict(color="black", width=2.5)))
                spaghetti.update_layout(height=420, margin=dict(l=0, r=0, t=10, b=0),
                                        xaxis_title="trade #", yaxis_title="$ cumulative")
                st.plotly_chart(spaghetti, use_container_width=True)

                # ----- Prop Firm Simulator -----
                st.markdown("---")
                st.header("Prop Firm Challenge Simulator")
                st.caption(
                    "Double-barrier simulation. Each draw is a daily-block bootstrap path "
                    "walked trade-by-trade. The first barrier touched determines the outcome. "
                    "Lower barrier trails the high-water mark upward indefinitely."
                )

                pf1, pf2, pf3, pf4 = st.columns(4)
                profit_target = pf1.number_input("profit target ($)", 100.0, 100000.0, 3000.0, 100.0)
                drawdown_limit = pf2.number_input("trailing DD limit ($)", 100.0, 50000.0, 2500.0, 100.0)
                pf_iter = pf3.number_input("simulations", 200, 20000, 2000, 200, key="pf_iter")
                pf_days = pf4.number_input("max days per challenge", 1, 500, int(n_days_total), 1, key="pf_days")
                trailing_mode = st.radio(
                    "drawdown mode",
                    ["eod", "instant", "static"],
                    index=0,
                    horizontal=True,
                    help="eod: Topstep-style EOD trailing. instant: trails every trade. static: no trailing, fixed at -DD.",
                )

                with st.spinner("simulating prop firm challenges..."):
                    pf = metrics.prop_firm_simulation(
                        chosen_trades,
                        profit_target=float(profit_target),
                        drawdown_limit=float(drawdown_limit),
                        trailing_mode=str(trailing_mode),
                        n_iter=int(pf_iter),
                        n_days=int(pf_days),
                    )

                p1, p2, p3, p4 = st.columns(4)
                p1.metric("Pass rate", f"{pf['pass_rate']:.1%}",
                          delta=f"{pf['outcomes']['pass']} sims")
                p2.metric("Fail rate", f"{pf['fail_rate']:.1%}",
                          delta=f"{pf['outcomes']['fail']} sims",
                          delta_color="inverse")
                p3.metric("Timeout", f"{pf['timeout_rate']:.1%}",
                          delta=f"{pf['outcomes']['timeout']} sims")
                p4.metric("Median days to outcome", f"{pf['median_days_to_outcome']:.0f}")

                # Outcome label
                pr = pf["pass_rate"]
                if pr >= 0.7:
                    lbl = "Highly Viable"
                elif pr >= 0.5:
                    lbl = "Promising"
                elif pr >= 0.3:
                    lbl = "Risky"
                elif pr >= 0.1:
                    lbl = "Low Edge"
                else:
                    lbl = "Not Viable"
                st.subheader(f"Verdict: {lbl}")

                # Spaghetti of prop firm paths (color by outcome)
                if pf["sample_paths"]:
                    pf_fig = go.Figure()
                    color_map = {"pass": "rgba(40,170,90,0.25)",
                                 "fail": "rgba(220,50,60,0.25)",
                                 "timeout": "rgba(150,150,150,0.18)"}
                    for path, oc in zip(pf["sample_paths"], pf["sample_outcomes"]):
                        pf_fig.add_trace(go.Scatter(
                            y=path, mode="lines", showlegend=False,
                            line=dict(width=1, color=color_map[oc]),
                            hoverinfo="skip",
                        ))
                    pf_fig.add_hline(y=profit_target, line=dict(color="green", dash="dash"),
                                     annotation_text="profit target")
                    pf_fig.add_hline(y=-drawdown_limit, line=dict(color="red", dash="dash"),
                                     annotation_text="initial DD limit")
                    pf_fig.update_layout(height=460, margin=dict(l=0, r=0, t=10, b=0),
                                         xaxis_title="trade #", yaxis_title="$ equity",
                                         title="Prop firm sample paths (green=pass, red=fail, gray=timeout)")
                    st.plotly_chart(pf_fig, use_container_width=True)


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
