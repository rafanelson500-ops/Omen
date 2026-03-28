class Trigger:
    def __init__(self, microstate, setup, regime, strategy):
        self.VWAP_OVEREXTENSION_THRESHOLD = 2.0

        self.microstate = microstate
        self.setup = setup
        self.regime = regime
        self.strategy = strategy

        self.recent_tick = None

        self.status = "WARMING_UP"
        self.exit_conditions = []

    def on_confluence(self, confluence):
        price = self.recent_tick["close"]
        if self.status == "WARMING_UP":
            if len(self.regime.vwap) > 1 \
             and len(self.regime.vwap_std) > 1\
             and self.recent_tick is not None:
                self.status = "READY"
            else:
                return        

        if confluence in self.exit_conditions:
            print(f"Exiting trade due to {confluence}")
            self.exit_conditions = []
            self.strategy.exit_trade(self.recent_tick)

        # VWAP Overextension
        if price > self.regime.vwap[-1] + self.VWAP_OVEREXTENSION_THRESHOLD * self.regime.vwap_std[-1]:
            if confluence == "- Aggression Extreme":
                self.strategy.handle_signal(-1, 1.5*self.regime.vwap_std[-1], price - self.regime.vwap[-1], 0.1)
                self.exit_conditions = ["+ Aggression Extreme"]

        # VWAP Under extension
        if price < self.regime.vwap[-1] - self.VWAP_OVEREXTENSION_THRESHOLD * self.regime.vwap_std[-1]:
            if confluence == "+ Aggression Extreme":
                self.strategy.handle_signal(1, 1.5*self.regime.vwap_std[-1], self.regime.vwap[-1] - price, 0.1)
                self.exit_conditions = ["- Aggression Extreme"]

    def on_tick(self, tick):
        self.recent_tick = tick