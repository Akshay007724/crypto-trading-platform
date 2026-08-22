from hft.types import Fill, Signal, Trade


class PaperBroker:
    """Simulates fills against replayed trades — no real exchange
    contact. Fills a BUY/SELL immediately at the trade's price, i.e.
    assumes zero slippage (acceptable for a v1 backtest).
    """

    def __init__(self, order_size: float = 1.0):
        self._order_size = order_size
        self.position = 0.0

    def execute(self, signal: Signal, trade: Trade) -> Fill | None:
        if signal == Signal.HOLD:
            return None

        if signal == Signal.BUY:
            self.position += self._order_size
        else:
            self.position -= self._order_size

        return Fill(
            symbol=trade.symbol,
            signal=signal,
            price=trade.price,
            size=self._order_size,
            ts=trade.ts,
        )
