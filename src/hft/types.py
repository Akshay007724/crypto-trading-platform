from dataclasses import dataclass
from enum import Enum


@dataclass(frozen=True)
class Trade:
    exchange: str
    symbol: str
    price: float
    size: float
    side: str
    ts: int


class Signal(Enum):
    BUY = "buy"
    SELL = "sell"
    HOLD = "hold"


@dataclass(frozen=True)
class Fill:
    symbol: str
    signal: Signal
    price: float
    size: float
    ts: int
