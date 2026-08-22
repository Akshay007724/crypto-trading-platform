from typing import Protocol

from hft.types import Signal, Trade


class Strategy(Protocol):
    def on_trade(self, trade: Trade) -> Signal: ...
