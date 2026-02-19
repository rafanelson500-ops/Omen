# Psedocode:

# Initialze a loop that triggers on the 0th second of every 5th minute.
#     Check if the bot is enabled
#     Check if the session is correct
#     Check if not in deadzone
#     Get recent data from the database
#     Featurize data
#     Run HMM model to get probabilities of each regime
#     Run Chop & Trend GBTs
#     Weight & average predictions according to regime probabilities
#     Execution Logic
#     Store featurized & targetted data for frontend visualization

#     If time is multiple of retrain interval, retrain GBTs
#     If time is hmm retrain time, retrain HMM
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from datetime import datetime, timezone
from helpers.timing import get_sleep_time
from helpers.config_handler import load_config
import time
from helpers.data_handler import get_data
from helpers.features import add_regime_features, add_technical_features, add_prediction_features_chop, add_prediction_features_trend, add_targets
from helpers.hmm import load_model as load_hmm, predict_regimes, train_hmm
from helpers.gbt.chop_gbt import load_model as load_chop_model, predict_chop_target
import pandas as pd
from helpers.logs import log

enriched_data = pd.DataFrame()

def get_enriched_data():
    return enriched_data.dropna().iloc[-1500:].to_json(orient="records")

def main(current_time):
    global enriched_data

    print("🟢\nCurrent time: ", current_time)
    log("Run")
    config = load_config()

    # Check if bot is enabled
    if not config["enabled"]:
        print("Bot is disabled")
        return

    # Check if current time is a deadzone
    # TODO: Implement deadzone check

    # Get data from database
    data = get_data(config["session"], jsonify = False, include_volume = True)

    # Calculate difference between current time and last candle time
    difference = current_time.timestamp() - data.iloc[-1]["time"]
    if difference > 3300:
        log(f"No new data (difference: {difference}). Last candle time: {datetime.fromtimestamp(data.iloc[-1]["time"]).strftime("%Y-%m-%d %H:%M:%S")}")
        return
    
    # Featurize data
    data = add_regime_features(data)
    data = add_technical_features(data)
    data = add_prediction_features_chop(data)
    data = add_targets(data)
    
    # Drop all rows with NaN except in 'forward_return' and 'target'
    cols_to_check = [c for c in data.columns if c not in ["forward_return", "target"]]
    data.dropna(subset=cols_to_check, inplace=True)


    # Run HMM model to get probabilities of each regime
    hmm_model = load_hmm("trained_models/regime_model.pkl", data.iloc[:-24])
    data["regime"] = predict_regimes(hmm_model, data)

    # Run Chop & Trend GBTs
    chop_model = load_chop_model("trained_models/chop_gbt_model.pkl", data.iloc[:-24])
    data = predict_chop_target(chop_model, data)

    # Weight & average predictions according to regime probabilities

    # Execution Logic

    # Store featurized & targetted data for frontend visualization
    enriched_data = data.copy()

    # If time is hmm retrain time, retrain HMM
    if current_time.strftime("%H:%M") == config["hmm_retrain_time"]:
        log("Retraining HMM...")
        train_hmm(data)

    # If time is multiple of retrain interval, retrain GBTs
    if round(current_time.timestamp()) % (config["gbt_retrain_interval"] * 60) == 0:
        log("Retraining GBTs...")

def loop():
    while True:
        current_time = datetime.now(timezone.utc)

        main(current_time)

        sleep_time = get_sleep_time(datetime.now(timezone.utc))
        print(f"Sleeping for {sleep_time} seconds\n🔴")
        time.sleep(sleep_time)