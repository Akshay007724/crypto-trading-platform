from collections import deque

from hft.types import Signal, Trade


class MovingAverageCrossover:
    """Buys when the fast SMA crosses above the slow SMA, sells on the
    reverse cross. Holds while either window isn't full yet, or while
    no cross has happened since the last signal.
    """

    def __init__(self, fast: int, slow: int):
        if fast >= slow:
            raise ValueError("fast window must be smaller than slow window")
        self._fast_prices: deque[float] = deque(maxlen=fast)
        self._slow_prices: deque[float] = deque(maxlen=slow)
        self._was_fast_above_slow: bool | None = None

    def on_trade(self, trade: Trade) -> Signal:
        self._fast_prices.append(trade.price)
        self._slow_prices.append(trade.price)

        if len(self._slow_prices) < self._slow_prices.maxlen:
            return Signal.HOLD

        fast_avg = sum(self._fast_prices) / len(self._fast_prices)
        slow_avg = sum(self._slow_prices) / len(self._slow_prices)

        if fast_avg == slow_avg:
            return Signal.HOLD

        is_fast_above_slow = fast_avg > slow_avg
        signal = Signal.HOLD
        if is_fast_above_slow != self._was_fast_above_slow:
            signal = Signal.BUY if is_fast_above_slow else Signal.SELL

        self._was_fast_above_slow = is_fast_above_slow
        return signal
