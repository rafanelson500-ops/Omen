from data.data import get_data
from data.features import featurize_HMM, featurize_GBT
from data.cleaner import normalize_HMM_features
from hmm.model import train_hmm, predict_regimes
import plotly.graph_objects as go
from plotly.subplots import make_subplots

def main():
    # Get data
    print("Getting data...")
    data = get_data()

    # Add features for HMM training
    print("Adding features for HMM training...")
    data = featurize_HMM(data)

    
    data.dropna(inplace=True) # Drop rows with NaN values (due to rolling calculations)
    data = normalize_HMM_features(data) # Normalize features
    features_normalized = data[['Returns', 'RealizedVolatility', 'Autocorrelation']].values # Convert to numpy array for HMM

    # Train HMM
    print("Training HMM...")
    hmm_model = train_hmm(features_normalized, n_components=2, n_iter=100, random_state=42)
    print("HMM trained successfully")

    # Predict regimes
    print("Assigning Regiemes to Data...")
    regiemes = predict_regimes(hmm_model, features_normalized)

    # Clean data for Gradient Boosted Tree featurizing
    data['Regieme'] = regiemes
    data = data[['Open', 'High', 'Low', 'Close', 'Volume', 'Regieme']]

    # Add features for Gradient Boosted Tree training
    print("Adding features for Gradient Boosted Tree training...")
    data = featurize_GBT(data)

    data.dropna(inplace=True) # Drop rows with NaN values (due to rolling calculations)

    # Plot Close, Regieme, VAL, VAH
    print("Plotting Close, Regieme, VAL, VAH...")
    fig = make_subplots(
        rows=2, cols=1,
        shared_xaxes=True,
        vertical_spacing=0.1,
        subplot_titles=["Price Levels (Close, VAL, VAH)", "Regieme"],
        row_heights=[0.7, 0.3]
    )
    
    # Price-related plots on first subplot (row 1)
    fig.add_trace(go.Scatter(x=data.index, y=data['High'], name='High', line=dict(color='blue')), row=1, col=1)
    fig.add_trace(go.Scatter(x=data.index, y=data['Low'], name='Low', line=dict(color='green')), row=1, col=1)
    fig.add_trace(go.Scatter(x=data.index, y=data['VAL'], name='VAL', line=dict(color='green')), row=1, col=1)
    fig.add_trace(go.Scatter(x=data.index, y=data['VAH'], name='VAH', line=dict(color='red')), row=1, col=1)
    
    # Regieme on second subplot (row 2) with its own y-axis scale
    fig.add_trace(go.Scatter(x=data.index, y=data['Regieme'], name='Regieme', mode='lines+markers', 
                             line=dict(color='purple', width=2), marker=dict(size=4)), row=2, col=1)
    
    # Update layout
    fig.update_layout(height=800, showlegend=True, hovermode='x unified')
    fig.update_yaxes(title_text="Price", row=1, col=1)
    fig.update_yaxes(title_text="Regieme", row=2, col=1)
    fig.update_xaxes(title_text="Time", row=2, col=1)
    
    # Set y-axis ticks for regime (assuming integer regime values)
    max_regieme = int(data['Regieme'].max())
    fig.update_yaxes(tickmode='linear', tick0=0, dtick=1, range=[-0.2, max_regieme + 0.2], row=2, col=1)
    
    fig.show()

if __name__ == "__main__":
    main()