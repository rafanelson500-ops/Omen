from numba import jit
import pandas as pd
import numpy as np

@jit(nopython=True)
def ingest_tick(
    #Variables
    cost_per_entry: float,
    max_ticks_in_trade: int,
    daily_profit_target: float,
    daily_loss_limit: float,
    
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
    hmm_state: int,

    #State
    ticks_since_stall: int,
    ticks_since_spike: int,
    ticks_since_over: int,
    ticks_since_under: int,
    ticks_since_pos_agg_eff_spike: int,
    ticks_since_neg_agg_eff_spike: int,
    ticks_in_trade: int,
    prev_hmm_state: int,

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

        if unrealizedpnl > (vwap_upper - vwap): #                                       EXIT: Take Profit
            position = 0
            entry_price = 0
            realizedpnl += unrealizedpnl - cost_per_entry
            unrealizedpnl = 0
        elif unrealizedpnl < (vwap_lower - vwap) or realizedpnl + unrealizedpnl < -daily_loss_limit: #          EXIT: Stop Loss
            position = 0
            entry_price = 0
            realizedpnl += unrealizedpnl - cost_per_entry
            unrealizedpnl = 0

        if hmm_state != prev_hmm_state: #                                         EXIT: Regime Switch
            position = 0
            entry_price = 0
            realizedpnl += unrealizedpnl - cost_per_entry
            unrealizedpnl = 0

        if ticks_in_trade >= max_ticks_in_trade: #                                     EXIT: Max Trade Duration
            position = 0
            entry_price = 0
            realizedpnl += unrealizedpnl - cost_per_entry
            unrealizedpnl = 0

    else:
        # Conditions
        if realizedpnl > -daily_loss_limit and realizedpnl < daily_profit_target:
            if (ticks_since_over == 0) or (ticks_since_under == 0):
                if ticks_since_stall == 0 and ticks_since_spike <= 5:
                    if ticks_since_pos_agg_eff_spike <= 5:
                        position = -1
                        entry_price = price
                        unrealizedpnl = 0
                    elif ticks_since_neg_agg_eff_spike <= 5:
                        entry_price = price
                        position = 1
                        unrealizedpnl = 0

    prev_hmm_state = hmm_state
    return (ticks_since_stall, ticks_since_spike, ticks_since_over, ticks_since_under, ticks_since_pos_agg_eff_spike, ticks_since_neg_agg_eff_spike, ticks_in_trade, prev_hmm_state, position, entry_price, unrealizedpnl, realizedpnl)

@jit(nopython=True)
def ingest_ticks(
    #Variables
    cost_per_entry: float,
    max_ticks_in_trade: int,
    daily_profit_target: float,
    daily_loss_limit: float,
    
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
    hmm_state: np.ndarray,

    #State
    ticks_since_stall: int,
    ticks_since_spike: int,
    ticks_since_over: int,
    ticks_since_under: int,
    ticks_since_pos_agg_eff_spike: int,
    ticks_since_neg_agg_eff_spike: int,
    ticks_in_trade: int,
    prev_hmm_state: int,

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
        nstall, nspike, nover, nunder, npaggspike, nnegaggspike, nticks_in_trade, nprev_hmm_state, npos, nentry_price, nunrealizedpnl, nrealizedpnl = ingest_tick(
            cost_per_entry,
            max_ticks_in_trade,
            daily_profit_target,
            daily_loss_limit,
            
            price[i],
            tps_spikes[i],
            tps_stalls[i],
            agg_eff_spikes[i],
            agg_eff[i],
            raw_deltas[i],
            vwap[i],
            vwap_upper[i],
            vwap_lower[i],
            hmm_state[i],

            ticks_since_stall,
            ticks_since_spike,
            ticks_since_over,
            ticks_since_under,
            ticks_since_pos_agg_eff_spike,
            ticks_since_neg_agg_eff_spike,
            ticks_in_trade,
            prev_hmm_state,

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
        prev_hmm_state = nprev_hmm_state

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
        self.cost_per_entry = 0.5
        self.max_ticks_in_trade = 10000
        self.daily_profit_target = 100
        self.daily_loss_limit = 100

        # State
        self.ticks_since_stall = 1000
        self.ticks_since_spike = 1000
        self.ticks_since_over = 1000
        self.ticks_since_under = 1000
        self.ticks_since_pos_agg_eff_spike = 1000
        self.ticks_since_neg_agg_eff_spike = 1000
        self.ticks_in_trade = 0
        self.prev_hmm_state = 0

        # Account State
        self.position = 0
        self.entry_price = 0
        self.unrealizedpnl = 0
        self.realizedpnl = 0

    def live_tick(self, row):
        # iloc[-1] may be a view; copy before assigning strategy fields.
        row = row.copy()
        price = row['close']
        tps_spike = row['tps_spike']
        tps_stall = row['tps_stall']
        agg_eff_spike = row['agg_eff_spike']
        agg_eff = row['aggression_efficiency']
        raw_delta = row['raw_delta']
        vwap = row['vwap']
        vwap_upper = row['vwap_upper']
        vwap_lower = row['vwap_lower']
        hmm_state = row['hmm_state']

        nstall, nspike, nover, nunder, npaggspike, nnegaggspike, nticks_in_trade, nprev_hmm_state, npos, nentry_price, nunrealizedpnl, nrealizedpnl =ingest_tick(
            self.cost_per_entry,
            self.max_ticks_in_trade,
            self.daily_profit_target,
            self.daily_loss_limit,
            price,
            tps_spike,
            tps_stall,
            agg_eff_spike,
            agg_eff,
            raw_delta,
            vwap,
            vwap_upper,
            vwap_lower,
            hmm_state,
            self.ticks_since_stall,
            self.ticks_since_spike,
            self.ticks_since_over,
            self.ticks_since_under,
            self.ticks_since_pos_agg_eff_spike,
            self.ticks_since_neg_agg_eff_spike,
            self.ticks_in_trade,
            self.prev_hmm_state,
            self.position,
            self.entry_price,
            self.unrealizedpnl,
            self.realizedpnl,
        )

        self.ticks_since_stall = nstall
        self.ticks_since_spike = nspike
        self.ticks_since_over = nover
        self.ticks_since_under = nunder
        self.ticks_since_pos_agg_eff_spike = npaggspike
        self.ticks_since_neg_agg_eff_spike = nnegaggspike
        self.ticks_in_trade = nticks_in_trade
        self.prev_hmm_state = nprev_hmm_state

        if npos != self.position:
            print(f"Position changed from {self.position} to {npos}")

        self.position = npos
        self.entry_price = nentry_price
        self.unrealizedpnl = nunrealizedpnl
        self.realizedpnl = nrealizedpnl

        row['position'] = self.position
        row['entry_price'] = self.entry_price
        row['unrealizedpnl'] = self.unrealizedpnl
        row['realizedpnl'] = self.realizedpnl

        return row

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
        hmm_state = master_df['hmm_state'].values

        # State
        ticks_since_stall = self.ticks_since_stall
        ticks_since_spike = self.ticks_since_spike
        ticks_since_over = self.ticks_since_over
        ticks_since_under = self.ticks_since_under
        ticks_since_pos_agg_eff_spike = self.ticks_since_pos_agg_eff_spike
        ticks_since_neg_agg_eff_spike = self.ticks_since_neg_agg_eff_spike
        ticks_in_trade = self.ticks_in_trade
        prev_hmm_state = self.prev_hmm_state

        # Scalar account state for ingest_tick / Numba (not per-row arrays).
        position = int(self.position)
        entry_price = float(self.entry_price)
        unrealizedpnl = float(self.unrealizedpnl)
        realizedpnl = float(self.realizedpnl)

        # Ingest Ticks
        print("Ingesting ticks")
        positions, entry_prices, unrealizedpnls, realizedpnls = ingest_ticks(
            self.cost_per_entry,
            self.max_ticks_in_trade,
            self.daily_profit_target,
            self.daily_loss_limit,

            prices,
            tps_spikes,
            tps_stalls,
            agg_eff_spikes,
            agg_eff,
            raw_deltas,
            vwap,
            vwap_upper,
            vwap_lower,
            hmm_state,

            ticks_since_stall,
            ticks_since_spike,
            ticks_since_over,
            ticks_since_under,
            ticks_since_pos_agg_eff_spike,
            ticks_since_neg_agg_eff_spike,
            ticks_in_trade,
            prev_hmm_state,

            position,
            entry_price,
            unrealizedpnl,
            realizedpnl,
        )

        print("Ingesting ticks complete")

        master_df['position'] = positions
        master_df['entry_price'] = entry_prices
        master_df['unrealizedpnl'] = unrealizedpnls
        master_df['realizedpnl'] = realizedpnls

        return master_df
