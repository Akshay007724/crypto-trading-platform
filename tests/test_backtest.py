from hft.backtest import BacktestEngine, BacktestResult
from hft.execution import PaperBroker
from hft.strategies.moving_average import MovingAverageCrossover
from hft.types import Trade


class _FixedTradeSource:
    """In-memory TradeSource stand-in — same protocol CsvTradeSource implements."""

    def __init__(self, trades: list[Trade]):
        self._trades = trades

    def trades(self):
        return iter(self._trades)


def _trade(price: float, ts: int) -> Trade:
    return Trade(exchange="binance", symbol="BTC-USD", price=price, size=1, side="buy", ts=ts)


def test_backtest_runs_strategy_and_broker_over_every_trade_in_order():
    # Arrange: known price path -> known fast(2)/slow(3) crossover -> known fills
    prices = [10, 10, 10, 40, 40, 10]
    source = _FixedTradeSource([_trade(p, ts) for ts, p in enumerate(prices, start=1)])
    strategy = MovingAverageCrossover(fast=2, slow=3)
    broker = PaperBroker(order_size=1)
    engine = BacktestEngine(source, strategy, broker)

    # Act
    result: BacktestResult = engine.run()

    # Assert: BUY at ts=4 (fast crosses above), SELL at ts=6 (fast crosses back below)
    assert [f.signal.value for f in result.fills] == ["buy", "sell"]
    assert [f.ts for f in result.fills] == [4, 6]
    assert result.final_position == 0.0
