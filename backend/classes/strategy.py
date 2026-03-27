class Strategy:
    def __init__(self):
        self.TP_COEFF = 1
        self.SL_COEFF = 1
        self.PRESSURE_SWITCH_THRESHOLD = 0.5
        self.QUALITY_FILTER_THRESHOLD = 0.65
        self.TRADE_COOLDOWN_TICKS = 100
        self.TICK_LATENCY_SLIPPAGE = 1
        self.STARTING_ACCOUNT_SIZE = 50000
        self.TRAILING_DRAWDOWN = 2000
        self.ACCOUNT_BLOWN = False
        self.COST_PER_TRADE = 0

        self.status = "IDLE" # IDLE, IN_TRADE, COOLDOWN, ORDER_SUBMITTED
        self.side = 0 # 1, -1, 0
        self.position_size = 0
        self.pnl = 0.0
        self.entry_price = 0.0
        self.commission = 0.0
        self.trade_count = 0
        self.cooldown_ticks = 0
        self.ticks_since_submission = 0
        self.ruin_level = self.STARTING_ACCOUNT_SIZE - self.TRAILING_DRAWDOWN
        self.balance = self.STARTING_ACCOUNT_SIZE

    def handle_signal(self, tick, side):
        if self.status == "IDLE" and self.side == 0:
            self.status = "ORDER_SUBMITTED"
        else:
            print("Error: In trade or on cooldown")

    def exit_trade(self, tick):
        if self.side != 0 and self.status == "IN_TRADE":
            self.status = "COOLDOWN"
            self.pnl += self.position_size * self.side * (tick["close"] - self.entry_price)
            self.commission += self.COST_PER_TRADE
            self.entry_price = 0.0
            self.position_size = 0
            self.side = 0
            self.cooldown_ticks = 0
        else:
            print("Error: No trade to exit")

    def on_tick(self, tick):
        # Cooldown timing
        if self.status == "COOLDOWN":
            self.cooldown_ticks += 1
            if self.cooldown_ticks >= self.TRADE_COOLDOWN_TICKS:
                self.status = "IDLE"
                self.cooldown_ticks = 0
        
        # Order latency simulation
        if self.status == "ORDER_SUBMITTED":
            self.ticks_since_submission += 1
            if self.ticks_since_submission >= self.TICK_LATENCY_SLIPPAGE:
                if self.side != 0 and self.position_size > 0:
                    self.status = "IN_TRADE"
                    self.entry_price = tick["close"]
                    self.ticks_since_submission = 0
                    print(f"Trade executed - {self.side * self.position_size} @ {self.entry_price}")
                else:
                    print("Error: size or side not set")

        # Trade monitering
        if self.status == "IN_TRADE":
            self.balance = (self.STARTING_ACCOUNT_SIZE + self.pnl) + (self.position_size * self.side * (tick["close"] - self.entry_price)) - self.commission
            # balance    = realized pnl +  unrealized pnl - commission

            self.ruin_level = max(self.ruin_level, self.balance - self.TRAILING_DRAWDOWN)
            if self.balance <= self.ruin_level:
                self.ACCOUNT_BLOWN = True
                self.exit_trade(tick)
                print("Account blown")