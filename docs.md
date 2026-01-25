Model          #################################################################################

    Features:
        Open
        High
        Low
        Close
        Volume
        PctChange
        IsGreen
        UpperWickLength
        LowerWickLength

    Arcitecture: Gradient Boosted Trees

    Goal: Take a sample of candles with the previous features and predict the next candle's IsGreen value.

################################################################################################

Steps to build
    1) Collect price candle data (Open, High, Low, Close, Volume).
    2) Create derived features (PctChange, IsGreen, UpperWickLength, LowerWickLength).
    3) Build a dataset of sequences of candles and the next candle's IsGreen label.
    4) Split data into train/validation/test sets.
    5) Train a Gradient Boosted Trees model on the feature sequences.
    6) Evaluate with accuracy and confusion matrix on the test set.
    7) Save the trained model for inference.
    8) Run predictions on new data and compare to actual labels.