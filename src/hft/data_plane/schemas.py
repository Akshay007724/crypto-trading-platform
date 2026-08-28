"""Normalized market-data schema shared by every source (Kraken, Finnhub).

This is the contract between the deterministic data plane and everything
above it (tools, agents, UI). Sources normalize into this shape at the edge —
nothing downstream should know Kraken and Finnhub have different field names.
"""

from __future__ import annotations

from pydantic import BaseModel


class Quote(BaseModel):
    symbol: str
    price: float
    ts: float  # unix seconds
    source: str  # "kraken" | "finnhub"
    bid: float | None = None
    ask: float | None = None
    open: float | None = None
    high: float | None = None
    low: float | None = None
    change: float | None = None
    pct_change: float | None = None
    volume: float | None = None  # not available for Finnhub free tier


class Candle(BaseModel):
    symbol: str
    ts: float
    open: float
    high: float
    low: float
    close: float
    volume: float


class OrderBookLevel(BaseModel):
    price: float
    size: float


class OrderBookSnapshot(BaseModel):
    symbol: str
    ts: float
    bids: list[OrderBookLevel]
    asks: list[OrderBookLevel]


class NewsItem(BaseModel):
    symbol: str
    headline: str
    url: str
    source: str
    ts: float
