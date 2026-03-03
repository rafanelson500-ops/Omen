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

    @socketio.on('save_hmm')
    def save_hmm():
        global current_hmm
        if current_hmm:
            if not os.path.exists('trained_models'):
                os.makedirs('trained_models')
            with open('trained_models/hmm.pkl', 'wb') as f:
                pickle.dump(current_hmm, f)
