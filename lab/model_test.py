import numpy as np
import plotly.graph_objects as go
import yfinance as yf

stock_data = yf.download("SPY", period="1y", interval="1h")
stock_data.columns = stock_data.columns.get_level_values(0)
stock_data.dropna(inplace=True)

X, Y = np.meshgrid(stock_data["Close"], stock_data.index)
Z = stock_data["Volume"]

fig = go.Figure(data=[
    go.Scatter3d(
        x=stock_data.index,
        y=stock_data["Close"],
        z=stock_data["Volume"],
        mode='markers',
        marker=dict(size=2)
    )
])

fig.update_layout(
    title="3D Price-Volume-Time",
    scene=dict(
        xaxis_title='Time',
        yaxis_title='Price',
        zaxis_title='Volume'
    )
)

fig.show()
