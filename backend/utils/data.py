import pandas as pd
import utils.features as features

def get_data():
    df = pd.read_csv("data/multi-asset.csv")
    df = df.sort_values("ts_event")
    df = features.featurize(df)
    return df.dropna()