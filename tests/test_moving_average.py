from hft.strategies.moving_average import MovingAverageCrossover
from hft.types import Signal, Trade


def _trade(price: float, ts: int) -> Trade:
    return Trade(exchange="binance", symbol="BTC-USD", price=price, size=1, side="buy", ts=ts)


def test_holds_until_both_windows_are_full():
    # Arrange
    strat = MovingAverageCrossover(fast=2, slow=3)

    # Act / Assert
    assert strat.on_trade(_trade(100, 1)) == Signal.HOLD
    assert strat.on_trade(_trade(100, 2)) == Signal.HOLD


def test_buys_when_fast_average_crosses_above_slow_average():
    # Arrange: slow avg drags behind a rising price, fast avg catches up and crosses above it
    strat = MovingAverageCrossover(fast=2, slow=3)
    strat.on_trade(_trade(10, 1))
    strat.on_trade(_trade(10, 2))
    strat.on_trade(_trade(10, 3))  # fast=10, slow=10 -> equal, not yet a cross

    # Act
    signal = strat.on_trade(_trade(40, 4))  # fast=(10+40)/2=25, slow=(10+10+40)/3=20 -> fast > slow

    # Assert
    assert signal == Signal.BUY


def test_sells_when_fast_average_crosses_below_slow_average():
    # Arrange: mirror of the buy case, price falling
    strat = MovingAverageCrossover(fast=2, slow=3)
    strat.on_trade(_trade(40, 1))
    strat.on_trade(_trade(40, 2))
    strat.on_trade(_trade(40, 3))

    # Act
    signal = strat.on_trade(_trade(10, 4))  # fast=(40+10)/2=25, slow=(40+40+10)/3=30 -> fast < slow

    # Assert
    assert signal == Signal.SELL
