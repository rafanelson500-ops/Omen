import joblib
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import utils.data as d

HMM_FEATURES = ["es_rvol", "es_efficiency", "es_vol_ratio", "es_rel_volume"]
ZSCORE_WINDOW = 288

data = d.get_data()
for col in HMM_FEATURES:
    mu = data[col].rolling(ZSCORE_WINDOW).mean()
    sigma = data[col].rolling(ZSCORE_WINDOW).std()
    data[f"{col}_z"] = (data[col] - mu) / sigma
data = data.dropna().reset_index(drop=True)

model = joblib.load("models/es_hmm.pkl")
Z_COLS = [f"{c}_z" for c in HMM_FEATURES]

means = data.groupby(model.predict(data[Z_COLS].values))[HMM_FEATURES].mean()
tradable_id = int(means["es_rvol"].idxmax())

posteriors = model.predict_proba(data[Z_COLS].values)
data["tradable_pct"] = posteriors[:, tradable_id]

idx = data.index.values
timestamps = data["ts_event"].values
tick_step = max(1, len(idx) // 20)
tickvals = idx[::tick_step]
ticktext = [str(t)[:16] for t in timestamps[::tick_step]]

y_min, y_max = data["es_close"].min(), data["es_close"].max()
y_pad = (y_max - y_min) * 0.02

fig = go.Figure()

fig.add_trace(go.Bar(
    x=idx,
    y=[y_max - y_min + 2 * y_pad] * len(idx),
    base=y_min - y_pad,
    marker=dict(
        color=data["tradable_pct"].values,
        colorscale=[
            [0.0, "rgba(60, 60, 60, 0.5)"],
            [0.5, "rgba(140, 140, 40, 0.5)"],
            [1.0, "rgba(0, 220, 0, 0.5)"],
        ],
        colorbar=dict(title="Tradable %", tickformat=".0%"),
        cmin=0, cmax=1,
        line_width=0,
    ),
    width=1,
    showlegend=False,
    hovertemplate="tradable: %{marker.color:.1%}<extra></extra>",
))

fig.add_trace(go.Scatter(
    x=idx, y=data["es_close"],
    mode="lines", line=dict(color="white", width=1), name="ES",
))

fig.update_layout(
    template="plotly_dark",
    title="ES 5m — Tradability Heatmap",
    xaxis=dict(
        title="Time",
        tickvals=tickvals,
        ticktext=ticktext,
        tickangle=-45,
    ),
    yaxis=dict(title="ES Close", range=[y_min - y_pad, y_max + y_pad]),
    bargap=0,
    margin=dict(l=50, r=80, t=60, b=40),
)
fig.show()
