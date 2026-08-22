from dataclasses import dataclass, field

from hft.data import TradeSource
from hft.execution import PaperBroker
from hft.strategy import Strategy
from hft.types import Fill


@dataclass
class BacktestResult:
    fills: list[Fill] = field(default_factory=list)
    final_position: float = 0.0


class BacktestEngine:
    def __init__(self, source: TradeSource, strategy: Strategy, broker: PaperBroker):
        self._source = source
        self._strategy = strategy
        self._broker = broker

    def run(self) -> BacktestResult:
        fills: list[Fill] = []
        for trade in self._source.trades():
            signal = self._strategy.on_trade(trade)
            fill = self._broker.execute(signal, trade)
            if fill is not None:
                fills.append(fill)
        return BacktestResult(fills=fills, final_position=self._broker.position)
