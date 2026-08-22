from hft.execution import PaperBroker
from hft.types import Signal, Trade


def _trade(price: float, ts: int) -> Trade:
    return Trade(exchange="binance", symbol="BTC-USD", price=price, size=1, side="buy", ts=ts)


def test_hold_signal_produces_no_fill():
    # Arrange
    broker = PaperBroker()

    # Act
    fill = broker.execute(Signal.HOLD, _trade(100, 1))

    # Assert
    assert fill is None


def test_buy_signal_fills_at_trade_price_and_opens_long_position():
    # Arrange
    broker = PaperBroker(order_size=0.5)

    # Act
    fill = broker.execute(Signal.BUY, _trade(100, 1))

    # Assert
    assert fill.signal == Signal.BUY
    assert fill.price == 100
    assert fill.size == 0.5
    assert broker.position == 0.5


def test_sell_signal_fills_and_reduces_position():
    # Arrange
    broker = PaperBroker(order_size=0.5)
    broker.execute(Signal.BUY, _trade(100, 1))

    # Act
    broker.execute(Signal.SELL, _trade(110, 2))

    # Assert
    assert broker.position == 0.0
