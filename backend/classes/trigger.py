class Trigger:
    def __init__(self, microstate, setup, regime, strategy):
        self.VWAP_OVEREXTENSION_THRESHOLD = 2.0
        self.RISK_PER_TRADE = 0.1

        self.microstate = microstate
        self.setup = setup
        self.regime = regime
        self.strategy = strategy

        self.ticks_since_overextension = 0
        self.ticks_since_underextension = 0

        self.recent_tick = None

        self.status = "WARMING_UP"
        self.entry_code = "NONE"

    def on_confluence(self, confluence):
        price = self.recent_tick["close"]
        if self.status == "WARMING_UP":
            if len(self.regime.vwap) > 1 \
             and len(self.regime.vwap_std) > 1\
             and self.recent_tick is not None:
                self.status = "READY"
            else:
                return      



        # VWAP Overextension -----------------------------------------------------
        #ENTRY
        vwap_sigma = self.regime.vwap_std[-1] if len(self.regime.vwap_std) > 0 else 0
        if price > self.regime.vwap[-1] + self.VWAP_OVEREXTENSION_THRESHOLD * self.regime.vwap_std[-1]: # Price is above +sig2
            self.ticks_since_overextension += 1
        elif self.ticks_since_overextension > 0: # Price crossed back below +sig2
            self.ticks_since_overextension = 0
            if confluence == "- Aggression Extreme":
                success = self.strategy.handle_signal(-1, 1*vwap_sigma, 1*vwap_sigma, self.RISK_PER_TRADE)
                if success:
                    self.entry_code = "OVEREXTENSION"
        #EXIT
        # if self.entry_code == "OVEREXTENSION" and self.strategy.status == "IN_TRADE":
        #     if confluence == "+ Aggression Extreme" and self.recent_tick["close"] > self.strategy.entry_price:
        #         self.strategy.queue_exit(f"Exiting trade due to Extreme Pos Agression & unrealized loss")




        # VWAP Under extension ---------------------------------------------------
        #ENTRY
        if price < self.regime.vwap[-1] - self.VWAP_OVEREXTENSION_THRESHOLD * self.regime.vwap_std[-1]: # Price is below -sig2
            self.ticks_since_underextension += 1
        elif self.ticks_since_underextension > 0: # Price crossed back above -sig2
            self.ticks_since_underextension = 0
            if confluence == "+ Aggression Extreme":
                success = self.strategy.handle_signal(1, 1*vwap_sigma, 1*vwap_sigma, self.RISK_PER_TRADE)
                if success:
                    self.entry_code = "UNDEREXTENSION"
        #EXIT
        # if self.entry_code == "UNDEREXTENSION" and self.strategy.status == "IN_TRADE":
        #     if confluence == "- Aggression Extreme" and self.recent_tick["close"] < self.strategy.entry_price:
        #         self.strategy.queue_exit(f"Exiting trade due to Extreme Neg Agression & unrealized loss")

    def on_tick(self, tick):
        self.recent_tick = tick