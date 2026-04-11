import joblib

def zscore(data, features, zscore_window):
    for col in features:
        mu = data[col].rolling(zscore_window).mean()
        sigma = data[col].rolling(zscore_window).std()
        data[f"{col}_z"] = (data[col] - mu) / sigma
    data = data.dropna().reset_index(drop=True)
    return data

def predict(df, model_dir, features, target_col, target_regime_col, zscore_window=240):
    #Load model
    model = joblib.load(model_dir)

    #Z-score features
    data = zscore(df, features, zscore_window)

    # Get z-scored cols and data
    Z_COLS = [f"{c}_z" for c in features]
    means = data.groupby(model.predict(data[Z_COLS].values))[features].mean()
    tradable_id = int(means[target_regime_col].idxmax())

    # Predict posteriors
    posteriors = model.predict_proba(data[Z_COLS].values)
    data[target_col] = posteriors[:, tradable_id]

    return data