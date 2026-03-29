from datetime import datetime

class Strategy:
    def __init__(self):
        self.TP_COEFF = 1
        self.SL_COEFF = 1
        self.PRESSURE_SWITCH_THRESHOLD = 0.5
        self.QUALITY_FILTER_THRESHOLD = 0.65
        self.TRADE_COOLDOWN_TICKS = 100
        self.TICK_LATENCY_SLIPPAGE = 1
        self.STARTING_ACCOUNT_SIZE = 10000
        self.TRAILING_DRAWDOWN = 1000
        self.ACCOUNT_BLOWN = False
        self.COST_PER_TRADE = 10
        self.CONTRACT_MULTIPLIER = 20
        self.PROFIT_TARGET = 600
        self.LOSS_LIMIT = 300

        self.status = "WARMING_UP" # IDLE, IN_TRADE, COOLDOWN, ORDER_SUBMITTED, EXIT_ORDER_SUBMITTED
        self.side = 0 # 1, -1, 0
        self.position_size = 0
        self.sl = 0
        self.tp = 0
        self.pnl = 0.0
        self.entry_price = 0.0
        self.commission = 0.0
        self.trade_count = 0
        self.cooldown_ticks = 0
        self.ticks_since_submission = 0
        self.ticks_since_exit_submission = 0
        self._pending_exit_reason = None  # str when exit is queued
        self.ruin_level = self.STARTING_ACCOUNT_SIZE - self.TRAILING_DRAWDOWN
        self.balance = self.STARTING_ACCOUNT_SIZE

        self.tradable = True

    def handle_signal(self, side, sl, tp, risk):
        if self.status == "IDLE" and self.side == 0 and self.tradable:
            risk_num = (self.balance - self.ruin_level) * risk
            self.side = side
            self.position_size = max(1, int(risk_num / (sl * self.CONTRACT_MULTIPLIER)))
            self.sl = -sl
            self.tp = tp
            self.status = "ORDER_SUBMITTED"
            return True
        else:
            return False
            #print("Error: In trade or on cooldown")

    def queue_exit(self, reason):
        if self.status != "IN_TRADE" or self.side == 0:
            return
        self.status = "EXIT_ORDER_SUBMITTED"
        self.ticks_since_exit_submission = 0
        self._pending_exit_reason = reason

    def exit_trade(self, tick):
        if self.side != 0 and self.status in ("IN_TRADE", "EXIT_ORDER_SUBMITTED"):
            self.status = "COOLDOWN"
            self.pnl += self.position_size * self.side * self.CONTRACT_MULTIPLIER * (tick["close"] - self.entry_price)
            print(self.position_size * self.side * self.CONTRACT_MULTIPLIER * (tick["close"] - self.entry_price))
            self.commission += self.COST_PER_TRADE * self.position_size
            self.balance -= self.COST_PER_TRADE * self.position_size
            self.entry_price = 0.0
            self.position_size = 0
            self.side = 0
            self.cooldown_ticks = 0
            if self.pnl - self.commission > self.PROFIT_TARGET:
                self.tradable = False
                print("Profit target hit")
            elif self.pnl - self.commission < -self.LOSS_LIMIT:
                self.tradable = False
                print("Loss limit hit")
            if self._pending_exit_reason:
                print(self._pending_exit_reason)
                self._pending_exit_reason = None
        else:
            pass
            # print("Error: No trade to exit")

    def on_tick(self, tick):
        if self.status == "WARMING_UP":
            dt = datetime.fromtimestamp(tick["time"])
            if dt.minute == 30:
                print("Warming up complete")
                self.status = "IDLE"

        # Cooldown timing
        if self.status == "COOLDOWN":
            self.cooldown_ticks += 1
            if self.cooldown_ticks >= self.TRADE_COOLDOWN_TICKS:
                self.status = "IDLE"
                self.cooldown_ticks = 0

        # Exit fill latency: runs on ticks *after* queue_exit (same pattern as entry after handle_signal)
        if self.status == "EXIT_ORDER_SUBMITTED":
            self.balance = (self.STARTING_ACCOUNT_SIZE + self.pnl) + (self.position_size * self.side * self.CONTRACT_MULTIPLIER * (tick["close"] - self.entry_price)) - self.commission
            self.ruin_level = max(self.ruin_level, self.balance - self.TRAILING_DRAWDOWN)
            self.ticks_since_exit_submission += 1
            if self.ticks_since_exit_submission >= self.TICK_LATENCY_SLIPPAGE:
                self.exit_trade(tick)
                self.ticks_since_exit_submission = 0
        
        # Order latency simulation
        if self.status == "ORDER_SUBMITTED":
            self.ticks_since_submission += 1
            if self.ticks_since_submission >= self.TICK_LATENCY_SLIPPAGE:
                if self.side != 0 and self.position_size > 0:
                    self.status = "IN_TRADE"
                    self.entry_price = tick["close"]
                    self.ticks_since_submission = 0
                    self.trade_count += 1
                    print(f"Trade executed - {self.side * self.position_size} @ {self.entry_price}")
                else:
                    print("Error: size or side not set")

        # Trade monitering (EXIT_ORDER_SUBMITTED mark-to-market handled at start of tick)
        if self.status == "IN_TRADE":
            unrealized_pnl = self.position_size * self.side * self.CONTRACT_MULTIPLIER * (tick["close"] - self.entry_price)
            tp = self.tp * self.position_size * self.CONTRACT_MULTIPLIER
            sl = self.sl * self.position_size * self.CONTRACT_MULTIPLIER
            self.balance = (self.STARTING_ACCOUNT_SIZE + self.pnl) + unrealized_pnl - self.commission
            # balance    = realized pnl +  unrealized pnl - commission
            self.ruin_level = max(self.ruin_level, self.balance - self.TRAILING_DRAWDOWN)

            if unrealized_pnl > tp:
                self.queue_exit("Take profit hit")
            elif unrealized_pnl < sl or self.balance - self.STARTING_ACCOUNT_SIZE < -self.LOSS_LIMIT:
                self.queue_exit("Stop loss hit")

            if self.balance <= self.ruin_level:
                self.ACCOUNT_BLOWN = True
                self.tradable = False
                self.queue_exit("Account blown")