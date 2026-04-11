import plotly.graph_objects as go
from plotly.subplots import make_subplots
import utils.data as d
import utils.hmm_handler as hmm

data = d.get_data()

data = hmm.predict(data, "models/cl_hmm.pkl", ["cl_rvol", "cl_efficiency", "cl_vol_ratio", "cl_rel_volume"], "cl_tradable_pct", "cl_efficiency", 240)
data = hmm.predict(data, "models/es_hmm.pkl", ["es_rvol", "es_efficiency", "es_vol_ratio", "es_rel_volume"], "es_tradable_pct", "es_efficiency", 240)

idx = data.index.values
timestamps = data["ts_event"].values
tick_step = max(1, len(idx) // 20)
tickvals = idx[::tick_step]
ticktext = [str(t)[:19] for t in timestamps[::tick_step]]

ES_COLOR = "#7ec8e3"
CL_COLOR = "#f4a460"

fig = make_subplots(
    rows=4,
    cols=1,
    shared_xaxes=True,
    vertical_spacing=0.05,
    row_heights=[0.30, 0.20, 0.30, 0.20],
    subplot_titles=(
        "ES — close",
        "ES — tradable probability",
        "CL — close",
        "CL — tradable probability",
    ),
)

fig.add_trace(
    go.Scatter(
        x=idx,
        y=data["es_close"],
        mode="lines",
        name="ES close",
        line=dict(color=ES_COLOR, width=1.2),
        hovertemplate="%{customdata}<br>close: %{y:.2f}<extra></extra>",
        customdata=timestamps,
    ),
    row=1,
    col=1,
)

fig.add_trace(
    go.Scatter(
        x=idx,
        y=data["es_tradable_pct"],
        mode="lines",
        name="ES tradable",
        line=dict(color=ES_COLOR, width=1),
        fill="tozeroy",
        fillcolor="rgba(126, 200, 227, 0.22)",
        hovertemplate="%{customdata}<br>tradable: %{y:.1%}<extra></extra>",
        customdata=timestamps,
        showlegend=False,
    ),
    row=2,
    col=1,
)

fig.add_trace(
    go.Scatter(
        x=idx,
        y=data["cl_close"],
        mode="lines",
        name="CL close",
        line=dict(color=CL_COLOR, width=1.2),
        hovertemplate="%{customdata}<br>close: %{y:.2f}<extra></extra>",
        customdata=timestamps,
    ),
    row=3,
    col=1,
)

fig.add_trace(
    go.Scatter(
        x=idx,
        y=data["cl_tradable_pct"],
        mode="lines",
        name="CL tradable",
        line=dict(color=CL_COLOR, width=1),
        fill="tozeroy",
        fillcolor="rgba(244, 164, 96, 0.22)",
        hovertemplate="%{customdata}<br>tradable: %{y:.1%}<extra></extra>",
        customdata=timestamps,
        showlegend=False,
    ),
    row=4,
    col=1,
)

x_ticks = dict(tickvals=tickvals, ticktext=ticktext, tickangle=-45, showgrid=True)

fig.update_layout(
    template="plotly_dark",
    title="ES & CL — close and tradability",
    height=900,
    margin=dict(l=56, r=24, t=72, b=48),
    legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0, xanchor="left"),
    hovermode="x unified",
)

fig.update_xaxes({**x_ticks, "showticklabels": False}, row=1, col=1)
fig.update_xaxes({**x_ticks, "showticklabels": False}, row=2, col=1)
fig.update_xaxes({**x_ticks, "showticklabels": False}, row=3, col=1)
fig.update_xaxes({**x_ticks, "title_text": "Time"}, row=4, col=1)

fig.update_yaxes(title_text="price", row=1, col=1)
fig.update_yaxes(title_text="P(tradable)", range=[0, 1], tickformat=".0%", row=2, col=1)
fig.update_yaxes(title_text="price", row=3, col=1)
fig.update_yaxes(title_text="P(tradable)", range=[0, 1], tickformat=".0%", row=4, col=1)

fig.show()
