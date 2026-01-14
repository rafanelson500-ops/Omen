import numpy as np
import plotly.graph_objects as go
from noise import pnoise2  # Perlin noise 2D

# Generate grid points
n_points = 100
x = np.linspace(0, 10, n_points)
y = np.linspace(0, 10, n_points)
X, Y = np.meshgrid(x, y)

# Generate "Merlin-like" noise for Z
scale = 0.1  # frequency of noise
Z = np.zeros_like(X)
for i in range(n_points):
    for j in range(n_points):
        Z[i, j] = pnoise2(X[i, j] * scale, Y[i, j] * scale, octaves=4)

# Flatten for Mesh3d
X_flat = X.flatten()
Y_flat = Y.flatten()
Z_flat = Z.flatten()

# Plot
fig = go.Figure(data=[
    go.Mesh3d(
        x=X_flat,
        y=Y_flat,
        z=Z_flat,
        color='lightblue',
        opacity=0.8
    )
])

fig.update_layout(
    title="Merlin-like Noise Surface",
    scene=dict(
        xaxis_title='X',
        yaxis_title='Y',
        zaxis_title='Z'
    )
)

fig.show()
