from datetime import datetime, timedelta
import time
import os
from data.data import get_data
from config.config import HEADSTART, LOOKBACK_WINDOW, SEQUENCE_LENGTH, OFFSET, TARGET
from data.features import add_features
import matplotlib.pyplot as plt
import joblib
from hmm.model import train_hmm, predict_regimes
from gbt.model import train_gbt, predict_with_quartiles
import plotly.graph_objects as go
import numpy as np
from broker import buy, sell

def get_sleep_time(current_time):
    next_time = current_time.replace(second=0, microsecond=0) + timedelta(minutes=5-current_time.minute%5)
    return max(0, (next_time - current_time).total_seconds() - HEADSTART)

def load_hmm(df):
    # Ensure trained_models directory exists
    os.makedirs("./trained_models", exist_ok=True)
    
    try:
        model = joblib.load("./trained_models/regieme_model.pkl")
    except:
        print("No regieme model found, training new model...")
        model = train_hmm(df.iloc[:-OFFSET])
        # train_hmm already saves the model, but ensure directory exists
        os.makedirs("./trained_models", exist_ok=True)
    return model

def load_gbt(df):
    # Ensure trained_models directory exists
    os.makedirs("./trained_models", exist_ok=True)
    
    try:
        model = joblib.load("./trained_models/gbt_model.pkl")
    except:
        print("No gbt model found, training new model...")
        try:
            model = train_gbt(df.iloc[:-OFFSET])
            # Ensure directory exists before saving
            os.makedirs("./trained_models", exist_ok=True)
        except ValueError as e:
            print(f"Error training GBT model: {e}")
            print("Attempting to use existing model or creating minimal model...")
            # Try to load existing model even if it's old
            try:
                model = joblib.load("./trained_models/gbt_model.pkl")
                print("Using existing model despite training error")
            except:
                # If all else fails, raise the error
                raise ValueError(f"Could not train or load GBT model: {e}")
    return model

def loop():
    last_candle = None
    while True:
        # Get & print current time
        current_time = datetime.now()
        print(f"Current time: {current_time}")

        # Get data
        df = get_data()
        if df.index[-1] == last_candle:
            sleep_time = get_sleep_time(datetime.now())
            print(f"Sleeping for {sleep_time} seconds")
            time.sleep(sleep_time)
            continue
        last_candle = df.index[-1]

        # Add features to data
        print("Adding features to data...")
        df = add_features(df)
        # Only drop NaN rows for feature columns (not ForwardReturn, which is only for training)
        # This allows us to keep the last TARGET candles for prediction even though ForwardReturn is NaN
        feature_cols = [col for col in df.columns if col not in ['ForwardReturn', 'IsGreen']]
        df = df.dropna(subset=feature_cols)
        df = df.iloc[-LOOKBACK_WINDOW:]

        # Add regiemes to data
        hmm_model = load_hmm(df)
        df['Regieme'] = predict_regimes(hmm_model, df)

        # Add Predictions
        gbt_model = load_gbt(df)
        df = predict_with_quartiles(gbt_model, df)
        df.dropna(inplace=False)

        df['PredictedPrice'] = df['Close'] * (1 + df['PredictedReturn'].fillna(0))

        current_price = df['Close'].iloc[-1]
        current_predicted_price = df['PredictedPrice'].iloc[-1]
        last_price = df['Close'].iloc[-2]
        last_predicted_price = df['PredictedPrice'].iloc[-2]
        if last_predicted_price > last_price and current_predicted_price < current_price:
            sell()
        elif last_predicted_price < last_price and current_predicted_price > current_price:
            buy()
        
        # Crossover logic: 
        # Buy (1): PredictedPrice crosses above Close (was below, now above)
        # Sell (-1): PredictedPrice crosses below Close (was above, now below)
        # Hold (0): otherwise
        crossed_above = (df['PredictedPrice'] > df['Close']) & (df['PredictedPrice'].shift(1) <= df['Close'].shift(1))
        crossed_below = (df['PredictedPrice'] < df['Close']) & (df['PredictedPrice'].shift(1) >= df['Close'].shift(1))
        df['Signal'] = np.where(crossed_above, 1, np.where(crossed_below, -1, 0))
        
        print(df[['Close','PredictedPrice', 'Signal']].tail(24))

        if df['Signal'].iloc[-1] == 1:
            with open('signal.txt', 'a') as f:
                f.write(current_time.strftime('%Y-%m-%d %H:%M:%S') + ' LONG @ ' + str(current_price) + '\n')
        elif df['Signal'].iloc[-1] == -1:
            with open('signal.txt', 'a') as f:
                f.write(current_time.strftime('%Y-%m-%d %H:%M:%S') + ' SHORT @ ' + str(current_price) + '\n')

        # Retrain model if needed
        if current_time.minute % 15 == 0:
            print("Retraining model")
            # Ensure directory exists before retraining
            os.makedirs("./trained_models", exist_ok=True)
            
            try:
                train_hmm(df)
            except Exception as e:
                print(f"Error retraining HMM model: {e}")
                print("Continuing with existing HMM model...")
            
            try:
                train_gbt(df.iloc[:-OFFSET])
            except ValueError as e:
                print(f"Error retraining GBT model: {e}")
                print("Continuing with existing GBT model...")
            except Exception as e:
                print(f"Unexpected error retraining GBT model: {e}")
                print("Continuing with existing GBT model...")

        # Sleep for remaining time
        sleep_time = get_sleep_time(datetime.now())
        print(f"Sleeping for {sleep_time} seconds")
        time.sleep(sleep_time)

loop()




# OLD PLOTTING LOGIC
# Create a copy of predictions for price chart (forward-looking, not shifted)
        # df_price_predictions = df.copy()
        # # Plot
        # from plotly.subplots import make_subplots
        
        # # Create subplots with shared x-axis
        # fig = make_subplots(
        #     rows=2, cols=1,
        #     shared_xaxes=True,
        #     vertical_spacing=0.1,
        #     subplot_titles=('Close Price with Quartile Regions', 'Predicted Returns (%)'),
        #     row_heights=[0.6, 0.4]
        # )
        
        # # Convert datetime index to sequential numeric index to remove weekend gaps
        # # Keep datetime for hover text
        # x_axis_numeric = np.arange(len(df))
        # datetime_labels = df.index
        
        # # Calculate extended x-axis (numeric) for future predictions
        # extended_x_axis_numeric = list(x_axis_numeric) + list(range(len(df), len(df) + TARGET))
        
        # # Top plot: Close price with shaded quartile regions
        # fig.add_trace(
        #     go.Scatter(
        #         x=x_axis_numeric,
        #         y=df['Close'],
        #         mode='lines',
        #         name='Close',
        #         line=dict(color='black', width=2),
        #         hovertemplate='<b>%{text}</b><br>Price: %{y:.2f}<extra></extra>',
        #         text=[dt.strftime('%Y-%m-%d %H:%M') for dt in datetime_labels]
        #     ),
        #     row=1, col=1
        # )
        
        # # Detect crossovers: when predicted price crosses above/below Close
        # if 'PredictedReturn' in df_price_predictions.columns:
        #     # Calculate predicted price from PredictedReturn
        #     predicted_price = df['Close'] * (1 + df_price_predictions['PredictedReturn'].fillna(0))
            
        #     # Detect crossovers
        #     # Crossover above: predicted_price was below Close, now above
        #     # Crossover below: predicted_price was above Close, now below
        #     cross_above_indices = []
        #     cross_below_indices = []
            
        #     for i in range(1, len(df)):
        #         prev_pred = predicted_price.iloc[i-1]
        #         curr_pred = predicted_price.iloc[i]
        #         prev_close = df['Close'].iloc[i-1]
        #         curr_close = df['Close'].iloc[i]
                
        #         # Check if crossed above (predicted was below, now above)
        #         if prev_pred <= prev_close and curr_pred > curr_close:
        #             cross_above_indices.append(i)
        #         # Check if crossed below (predicted was above, now below)
        #         elif prev_pred >= prev_close and curr_pred < curr_close:
        #             cross_below_indices.append(i)
            
        #     # Add green markers for crossovers above
        #     if cross_above_indices:
        #         cross_above_x = [x_axis_numeric[i] for i in cross_above_indices]
        #         cross_above_y = [df['Close'].iloc[i] for i in cross_above_indices]
        #         cross_above_text = [datetime_labels[i].strftime('%Y-%m-%d %H:%M') for i in cross_above_indices]
                
        #         fig.add_trace(
        #             go.Scatter(
        #                 x=cross_above_x,
        #                 y=cross_above_y,
        #                 mode='markers',
        #                 name='Crossover Above',
        #                 marker=dict(
        #                     symbol='triangle-up',
        #                     size=10,
        #                     color='green',
        #                     line=dict(width=1, color='darkgreen')
        #                 ),
        #                 hovertemplate='<b>%{text}</b><br>Price: %{y:.2f}<br>Crossover Above<extra></extra>',
        #                 text=cross_above_text
        #             ),
        #             row=1, col=1
        #         )
            
        #     # Add red markers for crossovers below
        #     if cross_below_indices:
        #         cross_below_x = [x_axis_numeric[i] for i in cross_below_indices]
        #         cross_below_y = [df['Close'].iloc[i] for i in cross_below_indices]
        #         cross_below_text = [datetime_labels[i].strftime('%Y-%m-%d %H:%M') for i in cross_below_indices]
                
        #         fig.add_trace(
        #             go.Scatter(
        #                 x=cross_below_x,
        #                 y=cross_below_y,
        #                 mode='markers',
        #                 name='Crossover Below',
        #                 marker=dict(
        #                     symbol='triangle-down',
        #                     size=10,
        #                     color='red',
        #                     line=dict(width=1, color='darkred')
        #                 ),
        #                 hovertemplate='<b>%{text}</b><br>Price: %{y:.2f}<br>Crossover Below<extra></extra>',
        #                 text=cross_below_text
        #             ),
        #             row=1, col=1
        #         )
        
        # # Add shaded regions for quartiles (forward-looking predictions)
        # # Predictions extend TARGET bars into the future beyond the close line
        # if 'PredictedReturn_Q1' in df_price_predictions.columns and 'PredictedReturn_Q3' in df_price_predictions.columns:
        #     # Get the last valid predictions to extend into the future
        #     # Find the last non-NaN prediction
        #     valid_pred_mask = ~df_price_predictions['PredictedReturn_Q2'].isna()
        #     if valid_pred_mask.any():
        #         last_valid_idx = df_price_predictions[valid_pred_mask].index[-1]
        #         last_idx = df_price_predictions.index.get_loc(last_valid_idx)
        #         last_close = df['Close'].iloc[last_idx]
        #         last_q1 = df_price_predictions['PredictedReturn_Q1'].iloc[last_idx]
        #         last_q2 = df_price_predictions['PredictedReturn_Q2'].iloc[last_idx]
        #         last_q3 = df_price_predictions['PredictedReturn_Q3'].iloc[last_idx]
        #     else:
        #         last_idx = len(df_price_predictions) - 1
        #         last_close = df['Close'].iloc[last_idx] if last_idx >= 0 else df['Close'].iloc[-1]
        #         last_q1 = 0
        #         last_q2 = 0
        #         last_q3 = 0
            
        #     # Calculate price levels for historical predictions (at prediction time)
        #     price_q1_historical = df['Close'] * (1 + df_price_predictions['PredictedReturn_Q1'].fillna(0))
        #     price_q3_historical = df['Close'] * (1 + df_price_predictions['PredictedReturn_Q3'].fillna(0))
        #     price_q2_historical = df['Close'] * (1 + df_price_predictions['PredictedReturn_Q2'].fillna(0))
            
        #     # Extend predictions into the future
        #     future_price_q1 = [last_close * (1 + last_q1)] * TARGET
        #     future_price_q3 = [last_close * (1 + last_q3)] * TARGET
        #     future_price_q2 = [last_close * (1 + last_q2)] * TARGET
            
        #     # Combine historical and future
        #     price_q1_full = list(price_q1_historical) + future_price_q1
        #     price_q3_full = list(price_q3_historical) + future_price_q3
        #     price_q2_full = list(price_q2_historical) + future_price_q2
            
        #     # Shade region between Q1 and Q3 (including future extension)
        #     fig.add_trace(
        #         go.Scatter(
        #             x=extended_x_axis_numeric,
        #             y=price_q3_full,
        #             mode='lines',
        #             name='Q3 Price',
        #             line=dict(width=0),
        #             showlegend=False,
        #             hoverinfo='skip'
        #         ),
        #         row=1, col=1
        #     )
        #     fig.add_trace(
        #         go.Scatter(
        #             x=extended_x_axis_numeric,
        #             y=price_q1_full,
        #             mode='lines',
        #             name='Q1-Q3 Range',
        #             fill='tonexty',
        #             fillcolor='rgba(0, 100, 255, 0.2)',
        #             line=dict(width=0),
        #             showlegend=True
        #         ),
        #         row=1, col=1
        #     )
            
        #     # Add Q2 (median) line (including future extension)
        #     fig.add_trace(
        #         go.Scatter(
        #             x=extended_x_axis_numeric,
        #             y=price_q2_full,
        #             mode='lines',
        #             name='Q2 (Median)',
        #             line=dict(color='blue', width=1, dash='dash')
        #         ),
        #         row=1, col=1
        #     )
        
        # # Bottom plot: Predicted returns and ForwardReturn as percentages
        # # ForwardReturn is already calculated for TARGET bars ahead, so it aligns with shifted predictions
        # if 'ForwardReturn' in df.columns:
        #     fig.add_trace(
        #         go.Scatter(
        #             x=x_axis_numeric,
        #             y=df['ForwardReturn'] * 100,
        #             mode='lines',
        #             name='Forward Return (%)',
        #             line=dict(color='green', width=2),
        #             hovertemplate='<b>%{text}</b><br>Forward Return: %{y:.2f}%<extra></extra>',
        #             text=[dt.strftime('%Y-%m-%d %H:%M') for dt in datetime_labels]
        #         ),
        #         row=2, col=1
        #     )
        
        # if 'PredictedReturn_Q1' in df.columns:
        #     fig.add_trace(
        #         go.Scatter(
        #             x=x_axis_numeric,
        #             y=df['PredictedReturn_Q1'] * 100,
        #             mode='lines',
        #             name='Predicted Q1 (%)',
        #             line=dict(color='lightblue', width=1),
        #             hovertemplate='<b>%{text}</b><br>Predicted Q1: %{y:.2f}%<extra></extra>',
        #             text=[dt.strftime('%Y-%m-%d %H:%M') for dt in datetime_labels]
        #         ),
        #         row=2, col=1
        #     )
        
        # if 'PredictedReturn_Q2' in df.columns:
        #     fig.add_trace(
        #         go.Scatter(
        #             x=x_axis_numeric,
        #             y=df['PredictedReturn_Q2'] * 100,
        #             mode='lines',
        #             name='Predicted Q2 (%)',
        #             line=dict(color='blue', width=2),
        #             hovertemplate='<b>%{text}</b><br>Predicted Q2: %{y:.2f}%<extra></extra>',
        #             text=[dt.strftime('%Y-%m-%d %H:%M') for dt in datetime_labels]
        #         ),
        #         row=2, col=1
        #     )
        
        # if 'PredictedReturn_Q3' in df.columns:
        #     fig.add_trace(
        #         go.Scatter(
        #             x=x_axis_numeric,
        #             y=df['PredictedReturn_Q3'] * 100,
        #             mode='lines',
        #             name='Predicted Q3 (%)',
        #             line=dict(color='lightblue', width=1),
        #             hovertemplate='<b>%{text}</b><br>Predicted Q3: %{y:.2f}%<extra></extra>',
        #             text=[dt.strftime('%Y-%m-%d %H:%M') for dt in datetime_labels]
        #         ),
        #         row=2, col=1
        #     )
        
        # if 'PredictedReturn' in df.columns:
        #     fig.add_trace(
        #         go.Scatter(
        #             x=x_axis_numeric,
        #             y=df['PredictedReturn'] * 100,
        #             mode='lines',
        #             name='Predicted Mean (%)',
        #             line=dict(color='orange', width=1.5, dash='dot'),
        #             hovertemplate='<b>%{text}</b><br>Predicted Mean: %{y:.2f}%<extra></extra>',
        #             text=[dt.strftime('%Y-%m-%d %H:%M') for dt in datetime_labels]
        #         ),
        #         row=2, col=1
        #     )
        
        # # Add zero line to bottom plot
        # fig.add_hline(y=0, line_dash="dash", line_color="gray", opacity=0.5, row=2, col=1)
        
        # # Update layout
        # fig.update_layout(
        #     height=800,
        #     title_text="Trading Analysis Dashboard",
        #     hovermode='x unified'
        # )
        
        # # Update y-axis labels
        # fig.update_yaxes(title_text="Price", row=1, col=1)
        # fig.update_yaxes(title_text="Return (%)", row=2, col=1)
        
        # # Update x-axis to show datetime labels at selected points
        # # Use tickmode='linear' with tick0 and dtick to show datetime labels
        # # But since we're using numeric x-axis, we'll create custom tick labels
        # n_ticks = 10
        # tick_indices = np.linspace(0, len(df) - 1, n_ticks, dtype=int)
        # tick_values = [x_axis_numeric[i] for i in tick_indices]
        # tick_labels = [datetime_labels[i].strftime('%Y-%m-%d\n%H:%M') for i in tick_indices]
        
        # fig.update_xaxes(
        #     title_text="Time",
        #     tickmode='array',
        #     tickvals=tick_values,
        #     ticktext=tick_labels,
        #     row=2, col=1
        # )
        # fig.update_xaxes(
        #     tickmode='array',
        #     tickvals=tick_values,
        #     ticktext=tick_labels,
        #     row=1, col=1
        # )
        
        # # Show plot
        # fig.show()