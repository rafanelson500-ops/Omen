from data.data import get_data
from data.features import featurize_HMM, featurize_GBT
from data.cleaner import normalize_HMM_features
from hmm.model import train_hmm, predict_regimes, save_model as save_hmm_model
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from gbt.model import train_gbt, save_model as save_gbt_model

def main():
    # Get data
    print("Getting data...")
    data = get_data(training=True)

    # Add features for HMM training
    print("Adding features for HMM training...")
    data = featurize_HMM(data)
    print("Adding features for Gradient Boosted Tree training...")
    data = featurize_GBT(data)

    
    data.dropna(inplace=True) # Drop rows with NaN values (due to rolling calculations)
    data = normalize_HMM_features(data) # Normalize features
    features_normalized = data[['Returns', 'RealizedVolatility', 'Autocorrelation']].values # Convert to numpy array for HMM

    # Train HMM
    print("Training HMM...")
    hmm_model = train_hmm(features_normalized, n_components=3, n_iter=100, random_state=41)
    print("HMM trained successfully")
    save_hmm_model(hmm_model, "./trained_models/hmm_model.pkl")


    # Predict regimes
    print("Assigning Regiemes to Data...")
    regiemes = predict_regimes(hmm_model, features_normalized)
    
    # Add regime to data (keep all GBT features that were already added)
    data['Regieme'] = regiemes
    
    # Check data size after dropna
    print(f"Data shape after feature engineering and dropna: {data.shape}")
    if len(data) == 0:
        raise ValueError("No data remaining after feature engineering. Try increasing the data size or reducing feature window sizes.")
    
    # Train Gradient Boosted Tree
    print("Training Gradient Boosted Tree...")
    gbt_model, sequence_length = train_gbt(data, sequence_length=10)
    print("Gradient Boosted Tree trained successfully")
    save_gbt_model(gbt_model, "./trained_models/gbt_model.pkl", sequence_length)

if __name__ == "__main__":
    main()