import numpy as np
import plotly.graph_objects as go
import yfinance as yf

TICKER = "SPY"
yf_ticker = yf.Ticker(TICKER)

def get_expirations():
    return yf_ticker.options

def get_iv_surface(expirations):
    spot = yf_ticker.history(period="1d")["Close"].iloc[-1]
    print(f"Spot price: {spot:.2f}")

    all_strikes = []
    all_ivs = []

    for exp in expirations:
        chain = yf_ticker.option_chain(exp).calls

        # Find ATM index
        atm_idx = (chain["strike"] - spot).abs().idxmin()

        strikes = chain["strike"].values
        ivs = chain["impliedVolatility"].values

        all_strikes.append(strikes)
        all_ivs.append(ivs)

    # Pad arrays to same length
    max_len = max(len(s) for s in all_strikes)

    def pad(arr):
        return np.pad(arr, (0, max_len - len(arr)), constant_values=np.nan)

    strike_grid = np.array([pad(s) for s in all_strikes]).T
    iv_grid = np.array([pad(v) for v in all_ivs]).T

    return strike_grid, iv_grid

# Fetch data
expirations = get_expirations()[0:8]
exp_nums = np.arange(len(expirations))

strike_grid, iv_grid = get_iv_surface(expirations)

# Plot surface
fig = go.Figure(
    data=go.Surface(
        x=exp_nums,
        y=strike_grid,
        z=iv_grid,
        colorscale="Viridis",
        showscale=True,
        colorbar=dict(
            title="IV",
            tickcolor="white",
            len=0.6,
            bgcolor="rgba(0,0,0,0)",
            outlinecolor="white"
        ),
    )
)

fig.update_layout(
    title=dict(
        text="SPY Call Implied Volatility Surface (ATM-Centered)",
        font=dict(color="white", size=18),
        x=0.5
    ),
    paper_bgcolor="rgb(10,10,14)",
    plot_bgcolor="rgb(10,10,14)",
    scene=dict(
        xaxis=dict(
            title=dict(text="Expiration", font=dict(color="white")),
            tickfont=dict(color="white"),
            tickmode="array",
            tickvals=exp_nums,
            ticktext=expirations,
            backgroundcolor="rgb(10,10,14)",
            gridcolor="rgba(255,255,255,0.08)",
            zerolinecolor="rgba(255,255,255,0.25)"
        ),
        yaxis=dict(
            title=dict(text="Strike", font=dict(color="white")),
            tickfont=dict(color="white"),
            backgroundcolor="rgb(10,10,14)",
            gridcolor="rgba(255,255,255,0.08)",
            zerolinecolor="rgba(255,255,255,0.25)"
        ),
        zaxis=dict(
            title=dict(text="Implied Volatility", font=dict(color="white")),
            tickfont=dict(color="white"),
            backgroundcolor="rgb(10,10,14)",
            gridcolor="rgba(255,255,255,0.08)",
            zerolinecolor="rgba(255,255,255,0.25)"
        ),
        camera=dict(
            eye=dict(x=1.4, y=1.4, z=0.9)
        )
    ),


    margin=dict(l=0, r=0, t=50, b=0)
)

fig.show()

