import databento as db
import dotenv
import os
import numpy as np
import pandas as pd
import pathway as pw
import datetime
from scipy.stats import norm
from scipy.optimize import brentq

dotenv.load_dotenv()
DATABENTO_API_KEY = os.getenv("DATABENTO_API_KEY")

interest_rate = 0.037
date = datetime.datetime.now(tz=datetime.timezone.utc).date()

class OptionsHandler:
    def __init__(self):
        self.client = db.Historical(DATABENTO_API_KEY)

    def get_options(self):
        dataset = "GLBX.MDP3"
        parent_symbol = "ES"  # E-mini S&P 500 options (CME)
        date = datetime.datetime.now(tz=datetime.timezone.utc)

        print("Getting option expirations...")
        data = self.client.timeseries.get_range(
            dataset=dataset,
            schema="definition",
            symbols=f"{parent_symbol}.OPT",
            stype_in="parent",
            start=date.date(),
            end=date - datetime.timedelta(minutes=15),
        )

        df = data.to_df()

        # Remove strategies
        df = df[df["security_type"] != "MLEG"]

        # Keep calls and puts
        df = df[df["cfi"].str.startswith(("OCA", "OPA"))]

        # Only expirations in the future
        df = df[df["expiration"] >= date]

        # Select nearest expiration
        nearest_exp = df["expiration"].min()
        df = df[df["expiration"] == nearest_exp]

        print("Nearest expiration:", nearest_exp)
        print("Getting option prices...")

        # Include the underlying futures instrument IDs so we can get the futures price
        underlying_ids = [
            int(uid) for uid in df["underlying_id"].dropna().unique() if int(uid) != 0
        ]
        options_data = self.client.timeseries.get_range(
            dataset=dataset,
            schema="mbp-1",
            symbols=df["instrument_id"].to_list() + underlying_ids,
            stype_in="instrument_id",
            start=date - datetime.timedelta(minutes=30),
            end=date - datetime.timedelta(minutes=15),
        )
        # groupby().last() makes instrument_id the index — reset so it's a column
        raw_df = options_data.to_df().groupby("instrument_id").last().reset_index()

        # Extract futures mid price (bid/ask are int64 fixed-point, divide by 1e9)
        underlying_df = raw_df[raw_df["instrument_id"].isin(underlying_ids)][
            ["instrument_id", "bid_px_00", "ask_px_00"]
        ].copy()
        underlying_df["underlying_price"] = (
            underlying_df["bid_px_00"] + underlying_df["ask_px_00"]
        ) / 2 / 1e9

        # Options-only rows
        options_df = raw_df[~raw_df["instrument_id"].isin(underlying_ids)].copy()
        options_df = options_df.merge(
            df[[
                "instrument_id",
                "expiration",
                "strike_price",
                "contract_multiplier",
                "symbol",
                "underlying_id",
                "cfi",
            ]],
            on="instrument_id",
            how="left"
        )
        # Scale strike_price from int64 fixed-point to float
        options_df["strike_price"] = options_df["strike_price"] / 1e9

        # Join underlying (futures) price via underlying_id → instrument_id
        options_df = options_df.merge(
            underlying_df[["instrument_id", "underlying_price"]].rename(
                columns={"instrument_id": "underlying_id"}
            ),
            on="underlying_id",
            how="left"
        )

        print("Computing implied volatility...")
        options_df = self.compute_implied_volatility(options_df)
        options_df.fillna(0, inplace=True)
        print(options_df)
        return options_df
    
    def compute_implied_volatility(self, df):
        """
        Compute implied volatility for each option in df using Black 76.
        Assumes 'mid_price' and 'underlying_price' columns exist.
        Returns df with a new column 'implied_vol'.
        """

        def black76_price(F, K, T, sigma, option_type="call"):
            """Black 76 price"""
            d1 = (np.log(F / K) + 0.5 * sigma**2 * T) / (sigma * np.sqrt(T))
            d2 = d1 - sigma * np.sqrt(T)
            discount = np.exp(-interest_rate * T)
            if option_type == "call":
                price = discount * (F * norm.cdf(d1) - K * norm.cdf(d2))
            else:
                price = discount * (K * norm.cdf(-d2) - F * norm.cdf(-d1))
            return price

        def iv_solver(mid, F, K, T, option_type):
            """Solve for implied volatility"""
            try:
                return brentq(
                    lambda sigma: black76_price(F, K, T, sigma, option_type) - mid,
                    1e-6,
                    5.0,
                )
            except ValueError:
                return np.nan  # if no solution

        # Ensure mid price exists (bid/ask are int64 fixed-point, divide by 1e9)
        df["mid_price"] = (df["bid_px_00"] + df["ask_px_00"]) / 2 / 1e9

        # Time to expiry in years
        now = datetime.datetime.now(datetime.timezone.utc)
        df["T"] = (df["expiration"] - now).dt.total_seconds() / (365.25 * 24 * 60 * 60)

        # Determine option type
        df["option_type"] = np.where(df["cfi"].str[1] == "C", "call", "put")

        # Assume underlying price is in 'underlying_price' column (from futures)
        if "underlying_price" not in df.columns:
            raise ValueError("Need ES futures price in column 'underlying_price' to compute IV.")

        # Compute IV
        df["implied_vol"] = df.apply(
            lambda row: iv_solver(
                row["mid_price"],
                row["underlying_price"],
                row["strike_price"],
                row["T"],
                row["option_type"],
            ),
            axis=1,
        )

        return df