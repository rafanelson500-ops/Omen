import databento as db
import dotenv
import os
import numpy as np
import pandas as pd
import pathway as pw
import datetime
from scipy.stats import norm
from scipy.optimize import brentq
import math

dotenv.load_dotenv()
DATABENTO_API_KEY = os.getenv("DATABENTO_API_KEY")

interest_rate = 0.037

class OptionsHandler:
    def __init__(self):
        self.client = db.Historical(DATABENTO_API_KEY)

    def get_options(self):
        dataset = "GLBX.MDP3"
        parent_symbol = "ES"  # E-mini S&P 500 options (CME)
        date = datetime.datetime(2026, 2, 27, tzinfo=datetime.timezone.utc)

        print("Getting option expirations...")
        data = self.client.timeseries.get_range(
            dataset=dataset,
            schema="definition",
            symbols=f"{parent_symbol}.OPT",
            stype_in="parent",
            start=date.replace(hour=0, minute=0, second=0, microsecond=0),
            end=date.replace(hour=0, minute=15, second=0, microsecond=0),
        )

        df = data.to_df()
        df.to_csv("df.csv")
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
        print("Getting volume data...")
        volume_data = self.client.timeseries.get_range(
            dataset=dataset,
            schema="statistics",
            symbols=df["instrument_id"].to_list(),
            stype_in="instrument_id",
            start=date.replace(hour=0, minute=0, second=0, microsecond=0),
            end=date.replace(hour=14, minute=15, second=0, microsecond=0),
        )
        volume_df = volume_data.to_df()
        volume_df = volume_df[volume_df["stat_type"] == 7]
        volume_df = volume_df.groupby("instrument_id").last().reset_index()
        volume_df = volume_df[["instrument_id", "price"]].rename(columns={"price": "open_interest"})
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
            start=date.replace(hour=14, minute=0, second=0, microsecond=0),
            end=date.replace(hour=14, minute=15, second=0, microsecond=0),
        )
        # groupby().last() makes instrument_id the index — reset so it's a column
        raw_df = options_data.to_df().groupby("instrument_id").last().reset_index()

        # Extract futures mid price (bid/ask are int64 fixed-point, divide by 1e9)
        underlying_df = raw_df[raw_df["instrument_id"].isin(underlying_ids)][
            ["instrument_id", "bid_px_00", "ask_px_00"]
        ].copy()
        underlying_df["underlying_price"] = (
            underlying_df["bid_px_00"] + underlying_df["ask_px_00"]
        ) / 2

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
        options_df["strike_price"] = options_df["strike_price"]

        # Join underlying (futures) price via underlying_id → instrument_id
        options_df = options_df.merge(
            underlying_df[["instrument_id", "underlying_price"]].rename(
                columns={"instrument_id": "underlying_id"}
            ),
            on="underlying_id",
            how="left"
        )

        options_df = options_df[abs(options_df["strike_price"] - options_df["underlying_price"])< 0.10 * options_df["underlying_price"]]

        # Merge open interest
        options_df = options_df.merge(
            volume_df,
            on="instrument_id",
            how="left",
        )
        options_df["open_interest"] = options_df["open_interest"].round().astype("Int64")

        print("Computing implied volatility...")
        options_df["contract_multiplier"] = 50
        options_df = self.compute_implied_volatility(options_df)
        #options_df.fillna(0, inplace=True)
        print(options_df)
        options_df.to_csv("options_df.csv")

        # Calculate gamma flip via spot-price sweep (correct method)
        # For each candidate spot price S, recompute Black-76 gamma for every option
        # and sum the signed GEX (calls +, puts -). The flip is where total GEX = 0.
        # This is correct because gamma itself changes as spot moves — deep ITM options
        # naturally have near-zero gamma at any given spot and won't distort the result.
        gex_df = options_df.dropna(subset=["open_interest", "implied_vol", "T"]).copy()
        gex_df = gex_df[
            (gex_df["open_interest"] > 0) &
            (gex_df["implied_vol"] > 0) &
            (gex_df["T"] > 0)
        ]

        spot_current = float(gex_df["underlying_price"].iloc[0])
        spot_range   = np.arange(spot_current * 0.85, spot_current * 1.15, 1.0)

        K_arr     = gex_df["strike_price"].values.astype(float)
        sigma_arr = gex_df["implied_vol"].values.astype(float)
        T_arr     = gex_df["T"].values.astype(float)
        OI_arr    = gex_df["open_interest"].values.astype(float)
        mult_arr  = gex_df["contract_multiplier"].values.astype(float)
        sign_arr  = np.where(gex_df["option_type"].values == "call", 1.0, -1.0)

        # Broadcast to (M spots) × (N options) — recomputes gamma at each spot level
        S2d     = spot_range[:, np.newaxis]
        K2d     = K_arr[np.newaxis, :]
        sigma2d = sigma_arr[np.newaxis, :]
        T2d     = T_arr[np.newaxis, :]
        OI2d    = OI_arr[np.newaxis, :]
        mult2d  = mult_arr[np.newaxis, :]
        sign2d  = sign_arr[np.newaxis, :]

        with np.errstate(divide="ignore", invalid="ignore"):
            d1       = (np.log(S2d / K2d) + 0.5 * sigma2d**2 * T2d) / (sigma2d * np.sqrt(T2d))
            gamma_2d = np.exp(-interest_rate * T2d) * norm.pdf(d1) / (S2d * sigma2d * np.sqrt(T2d))
            gamma_2d = np.where(np.isfinite(gamma_2d), gamma_2d, 0.0)

        total_gex = (sign2d * gamma_2d * OI2d * mult2d * S2d).sum(axis=1)

        crossings = np.where(np.diff(np.sign(total_gex)))[0]
        if len(crossings) > 0:
            idx = crossings[0]
            s1, s2 = spot_range[idx], spot_range[idx + 1]
            g1, g2 = total_gex[idx], total_gex[idx + 1]
            gamma_flip = float(s1 + (s2 - s1) * (-g1) / (g2 - g1))
        else:
            gamma_flip = float(spot_range[np.argmin(np.abs(total_gex))])

        print(f"\nGamma Flip: {gamma_flip:,.2f}")

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
        df["mid_price"] = (df["bid_px_00"] + df["ask_px_00"]) / 2 

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

        # Compute Gamma (Black-76)
        # Γ = e^(-rT) * N'(d1) / (F * σ * √T)
        F = df["underlying_price"]
        K = df["strike_price"]
        T = df["T"]
        sigma = df["implied_vol"]

        with np.errstate(divide="ignore", invalid="ignore"):
            d1 = (np.log(F / K) + 0.5 * sigma**2 * T) / (sigma * np.sqrt(T))
            valid = (T > 0) & sigma.notna() & (sigma > 0)

            df["gamma"] = np.where(
                valid,
                np.exp(-interest_rate * T) * norm.pdf(d1) / (F * sigma * np.sqrt(T)),
                np.nan,
            )

            # Compute Delta (Black-76)
            # Call:  Δ =  e^(-rT) * N(d1)
            # Put:   Δ = -e^(-rT) * N(-d1)
            discount = np.exp(-interest_rate * T)
            call_delta = discount * norm.cdf(d1)
            put_delta  = -discount * norm.cdf(-d1)
            df["delta"] = np.where(
                ~valid,
                np.nan,
                np.where(df["option_type"] == "call", call_delta, put_delta),
            )

        return df