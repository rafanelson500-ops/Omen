Project Flow

1. Subscribe to alerts for high volatility / inefficent stocks
2. Download 1m data
3. Featurize (Returns, Realized_Volatility, and Autocorrelation)
4. Use a Hidden Markov Model to define regiemes from NYSE open to current time
5. Featurize (IsGreen, LVNHighTap, LVNLowTap, VAHTap, VALTap, High(5), High(8), High(13), Low(5), Low(8), Low(13), Regieme)
6. Train a Gradient Boosted Tree (Predicting IsGreen)