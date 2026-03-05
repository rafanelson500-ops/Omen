import helpers.data as data
import helpers.features as features
import joblib
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import hmmlearn.hmm as hmm
import numpy as np
import flask
from flask import jsonify
from flask_cors import CORS
import joblib

app = flask.Flask(__name__)
CORS(app)

hmm_features = ["mean_spread", "spread_std", "vol_accel", "har_rv"]

def graph_notation(df):
    df["graph:0:white"] = df["composite_mean"]
    return df

@app.route("/data")
def get_data():
    df = data.get_data()
    df = features.add_features(df)
    df = df.dropna()
    hmm = joblib.load("trained_models/regime_hmm.pkl")
    df["hmm_state"] = hmm.predict(df[hmm_features])
    df = graph_notation(df)
    return jsonify(df.to_dict(orient="records"))

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=8000)