from numba import jit
import pandas as pd
import numpy as np

@jit(nopython=True)
def ingest_tick(
    #Variables
    cost_per_entry: float,
    max_ticks_in_trade: int,

    #Context
    price: float,
    tps_spike: int,
    tps_stall: int,
    agg_eff_spike: int,
    agg_eff: float,
    raw_delta: int,
    vwap: float,
    vwap_upper: float,
    vwap_lower: float,

    #State
    ticks_since_stall: int,
    ticks_since_spike: int,
    ticks_since_over: int,
    ticks_since_under: int,
    ticks_since_pos_agg_eff_spike: int,
    ticks_since_neg_agg_eff_spike: int,
    ticks_in_trade: int,

    #Account State
    position: int,
    entry_price: float,
    unrealizedpnl: float,
    realizedpnl: float,

) -> tuple[int, int, int, int, int, int, int, float, float]: # Return new states and position
    # Counters
    ticks_since_stall = 0 if tps_stall == 1 else ticks_since_stall + 1
    ticks_since_spike = 0 if tps_spike == 1 else ticks_since_spike + 1
    ticks_since_over = 0 if price > vwap_upper else ticks_since_over + 1
    ticks_since_under = 0 if price < vwap_lower else ticks_since_under + 1
    ticks_since_pos_agg_eff_spike = 0 if agg_eff_spike == 1 else ticks_since_pos_agg_eff_spike + 1
    ticks_since_neg_agg_eff_spike = 0 if agg_eff_spike == -1 else ticks_since_neg_agg_eff_spike + 1
    ticks_in_trade = 0 if position == 0 else ticks_in_trade + 1

    if position != 0:
        # Trade Management
        unrealizedpnl = position * (price - entry_price)

        if unrealizedpnl > 10: # Take Profit
            position = 0
            entry_price = 0
            realizedpnl += unrealizedpnl - cost_per_entry
            unrealizedpnl = 0
        elif unrealizedpnl < -5: # Stop Loss
            position = 0
            entry_price = 0
            realizedpnl += unrealizedpnl - cost_per_entry
            unrealizedpnl = 0

        if ticks_in_trade >= max_ticks_in_trade:
            position = 0
            entry_price = 0
            realizedpnl += unrealizedpnl - cost_per_entry
            unrealizedpnl = 0

    else:
        # Conditions
        if ticks_since_over == 0 or ticks_since_under == 0:
            if ticks_since_stall == 0 and ticks_since_spike <= 5:
                if ticks_since_pos_agg_eff_spike <= 5:
                    position = 1
                    entry_price = price
                    unrealizedpnl = 0
                elif ticks_since_neg_agg_eff_spike <= 5:
                    entry_price = price
                    position = -1
                    unrealizedpnl = 0

    return (ticks_since_stall, ticks_since_spike, ticks_since_over, ticks_since_under, ticks_since_pos_agg_eff_spike, ticks_since_neg_agg_eff_spike, ticks_in_trade, position, entry_price, unrealizedpnl, realizedpnl)

@jit(nopython=True)
def ingest_ticks(
    #Variables
    cost_per_entry: float,
    max_ticks_in_trade: int,

    #Context
    price: np.ndarray,
    tps_spikes: np.ndarray,
    tps_stalls: np.ndarray,
    agg_eff_spikes: np.ndarray,
    agg_eff: np.ndarray,
    raw_deltas: np.ndarray,
    vwap: np.ndarray,
    vwap_upper: np.ndarray,
    vwap_lower: np.ndarray,

    #State
    ticks_since_stall: int,
    ticks_since_spike: int,
    ticks_since_over: int,
    ticks_since_under: int,
    ticks_since_pos_agg_eff_spike: int,
    ticks_since_neg_agg_eff_spike: int,
    ticks_in_trade: int,

    # Account State
    position: int,
    entry_price: float,
    unrealizedpnl: float,
    realizedpnl: float,

) -> tuple[np.ndarray, np.ndarray, np.ndarray]:

    positions = np.zeros(len(price))
    entry_prices = np.zeros(len(price))
    unrealizedpnls = np.zeros(len(price))
    realizedpnls = np.zeros(len(price))

    for i in range(len(price)):
        # Numba nopython: cannot unpack into position[i] in one statement — use temps.
        nstall, nspike, nover, nunder, npaggspike, nnegaggspike, nticks_in_trade, npos, nentry_price, nunrealizedpnl, nrealizedpnl = ingest_tick(
            cost_per_entry,
            max_ticks_in_trade,

            price[i],
            tps_spikes[i],
            tps_stalls[i],
            agg_eff_spikes[i],
            agg_eff[i],
            raw_deltas[i],
            vwap[i],
            vwap_upper[i],
            vwap_lower[i],

            ticks_since_stall,
            ticks_since_spike,
            ticks_since_over,
            ticks_since_under,
            ticks_since_pos_agg_eff_spike,
            ticks_since_neg_agg_eff_spike,
            ticks_in_trade,

            position,
            entry_price,
            unrealizedpnl,
            realizedpnl,
        )

        ticks_since_stall = nstall
        ticks_since_spike = nspike
        ticks_since_over = nover
        ticks_since_under = nunder
        ticks_since_pos_agg_eff_spike = npaggspike
        ticks_since_neg_agg_eff_spike = nnegaggspike
        ticks_in_trade = nticks_in_trade

        position = npos
        entry_price = nentry_price
        unrealizedpnl = nunrealizedpnl
        realizedpnl = nrealizedpnl
        positions[i] = npos
        entry_prices[i] = nentry_price
        unrealizedpnls[i] = nunrealizedpnl
        realizedpnls[i] = nrealizedpnl

    return positions, entry_prices, unrealizedpnls, realizedpnls

class Strategy:
    def __init__(self):
        # Variables
        self.cost_per_entry = 2
        self.max_ticks_in_trade = 1500

        # State
        self.ticks_since_stall = 1000
        self.ticks_since_spike = 1000
        self.ticks_since_over = 1000
        self.ticks_since_under = 1000
        self.ticks_since_pos_agg_eff_spike = 1000
        self.ticks_since_neg_agg_eff_spike = 1000
        self.ticks_in_trade = 0

        # Account State
        self.position = 0
        self.entry_price = 0
        self.unrealizedpnl = 0
        self.realizedpnl = 0

    def live_tick(self):
        pass

    def backtest(self, master_df):
        # Context
        prices = master_df['close'].values
        tps_spikes = master_df['tps_spike'].values
        tps_stalls = master_df['tps_stall'].values
        agg_eff_spikes = master_df['agg_eff_spike'].values
        agg_eff = master_df['aggression_efficiency'].values
        raw_deltas = master_df['raw_delta'].values
        vwap = master_df['vwap'].values
        vwap_upper = (master_df['vwap'] + 2 * master_df['vwap_std']).values
        vwap_lower = (master_df['vwap'] - 2 * master_df['vwap_std']).values


        # State
        ticks_since_stall = self.ticks_since_stall
        ticks_since_spike = self.ticks_since_spike
        ticks_since_over = self.ticks_since_over
        ticks_since_under = self.ticks_since_under
        ticks_since_pos_agg_eff_spike = self.ticks_since_pos_agg_eff_spike
        ticks_since_neg_agg_eff_spike = self.ticks_since_neg_agg_eff_spike
        ticks_in_trade = self.ticks_in_trade
        
        # Scalar account state for ingest_tick / Numba (not per-row arrays).
        position = int(self.position)
        entry_price = float(self.entry_price)
        unrealizedpnl = float(self.unrealizedpnl)
        realizedpnl = float(self.realizedpnl)

        # Ingest Ticks
        positions, entry_prices, unrealizedpnls, realizedpnls = ingest_ticks(
            self.cost_per_entry,
            self.max_ticks_in_trade,

            prices,
            tps_spikes,
            tps_stalls,
            agg_eff_spikes,
            agg_eff,
            raw_deltas,
            vwap,
            vwap_upper,
            vwap_lower,

            ticks_since_stall,
            ticks_since_spike,
            ticks_since_over,
            ticks_since_under,
            ticks_since_pos_agg_eff_spike,
            ticks_since_neg_agg_eff_spike,
            ticks_in_trade,
            
            position,
            entry_price,
            unrealizedpnl,
            realizedpnl,
        )

        master_df['position'] = positions
        master_df['entry_price'] = entry_prices
        master_df['unrealizedpnl'] = unrealizedpnls
        master_df['realizedpnl'] = realizedpnls

        return master_df
