from flask_socketio import emit
from helpers.data import get_data
from helpers.features import add_features
from hmmlearn.hmm import GaussianHMM
import os
import pickle
import pandas as pd
from typing import Literal

current_hmm = None
last_data = pd.DataFrame()

def start_model_lab(socketio):
    @socketio.on('load_data')
    def load_data(t: Literal['live', 'cache']):
        global last_data
        df = None
        if t == 'cache':
            df = pd.read_csv('cached_data/data.csv')
            split_idx = int(len(df) * (2/3))
            df = df.iloc[split_idx:]
            last_data = df.copy()
        else:
            df = get_data()
            df = add_features(df).dropna()
            last_data = df.copy()
            split_idx = int(len(df) * (2/3))
            df = df.iloc[split_idx:]
        emit('load_data', df.to_dict(orient='records'))

    @socketio.on('save_cache')
    def save_cache():
            global last_data
            if not last_data.empty:
                if not os.path.exists('cached_data'):
                    os.makedirs('cached_data')
                last_data.to_csv('cached_data/data.csv')
        
    @socketio.on('train_hmm')
    def train_hmm(data):
        global current_hmm
        print("Training HMM... ", data)
        df = pd.read_csv('cached_data/data.csv')
        split_idx = int(len(df) * (2/3))
        training_data = df.iloc[:split_idx].copy()
        testing_data = df.iloc[split_idx:].copy()
        hmm = GaussianHMM(n_components=data['states'], covariance_type='diag').fit(training_data[data['features']].values)
        current_hmm = hmm
        testing_data["hmm_state"] = hmm.predict(testing_data[data['features']].values)
        emit('train_hmm', testing_data.to_dict(orient='records'))

    @socketio.on('load_hmm')
    def load_hmm(data):
        global current_hmm, last_data
        try:
            # Check if model file exists
            model_path = 'trained_models/hmm.pkl'
            if not os.path.exists(model_path):
                emit('load_hmm', {'error': 'HMM model file not found. Please train and save a model first.'})
                return
            
            # Load the model
            if not os.path.exists('trained_models'):
                os.makedirs('trained_models')
            with open(model_path, 'rb') as f:
                current_hmm = pickle.load(f)
            
            # Validate that we have data to predict on
            if last_data.empty:
                emit('load_hmm', {'error': 'No data loaded. Please load data first.'})
                return
            
            # Validate features exist in data
            features = data.get('features', [])
            if not features:
                emit('load_hmm', {'error': 'No features specified.'})
                return
            
            missing_features = [f for f in features if f not in last_data.columns]
            if missing_features:
                emit('load_hmm', {'error': f'Features not found in data: {missing_features}'})
                return
            
            # Make a copy and predict
            result_data = last_data.copy()
            result_data["hmm_state"] = current_hmm.predict(result_data[features].values)
            emit('load_hmm', result_data.to_dict(orient='records'))
        except FileNotFoundError:
            emit('load_hmm', {'error': 'HMM model file not found.'})
        except Exception as e:
            emit('load_hmm', {'error': f'Error loading HMM: {str(e)}'})

    @socketio.on('save_hmm')
    def save_hmm():
        global current_hmm
        if current_hmm:
            if not os.path.exists('trained_models'):
                os.makedirs('trained_models')
            with open('trained_models/hmm.pkl', 'wb') as f:
                pickle.dump(current_hmm, f)
