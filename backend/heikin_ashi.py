class HeikinAshi:
    def __init__(self):
        self.last_ha = None

    def ohlc_to_ha(self, ohlc):
        o, h, l, c = ohlc["open"], ohlc["high"], ohlc["low"], ohlc["close"]
        ha_close = (o + h + l + c) / 4
        if self.last_ha is None:
            ha_open = (o + c) / 2
        else:
            ha_open = (self.last_ha["open"] + self.last_ha["close"]) / 2
        ha_high = max(h, ha_open, ha_close)
        ha_low = min(l, ha_open, ha_close)
        ha = {
            "time": ohlc["time"],
            "open": ha_open,
            "high": ha_high,
            "low": ha_low,
            "close": ha_close,
        }
        self.last_ha = ha
        return ha