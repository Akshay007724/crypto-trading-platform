"""Deterministic tool interface exposed to agents.

Every function here is a plain typed call — no LLM involved — wrapping the
existing marketdata clients + data-plane cache/governor/store. Agents only
ever call these, never the raw HTTP clients, so rate limiting, caching, and
circuit breaking apply uniformly regardless of which agent is asking.

Crypto (Kraken) and equities (Finnhub) have different free-tier coverage —
where a data type genuinely isn't available (equity order book, equity
candles beyond what we've cached locally, crypto news) this returns None /
an empty list rather than fabricating data, per the platform's data
provenance rule.
"""

from __future__ import annotations

import time

import requests

from hft.data_plane.cache import QuoteCache
from hft.data_plane.ratelimit import CircuitOpenError, RateGovernor, RateLimitExceeded
from hft.data_plane.schemas import Candle, NewsItem, OrderBookLevel, OrderBookSnapshot, Quote
from hft.data_plane.timeseries import TimeseriesStore
from hft.marketdata import finnhub, kraken_rest

KRAKEN_OHLC_URL = "https://api.kraken.com/0/public/OHLC"
KRAKEN_DEPTH_URL = "https://api.kraken.com/0/public/Depth"
FINNHUB_NEWS_URL = "https://finnhub.io/api/v1/company-news"

CRYPTO_PAIRS = {
    "BTC/USD": ("XBTUSD", "XXBTZUSD"),
    "ETH/USD": ("ETHUSD", "XETHZUSD"),
    "SOL/USD": ("SOLUSD", "SOLUSD"),
    "ADA/USD": ("ADAUSD", "ADAUSD"),
}


class MarketTools:
    """Bundles the cache/governor/store dependencies each tool call needs.

    One instance is shared per process (see hft.agents.base for how agents
    receive it) — cheap to construct, holds no per-request state.
    """

    def __init__(self, quote_cache: QuoteCache, governor: RateGovernor, store: TimeseriesStore, finnhub_api_key: str = ""):
        self._cache = quote_cache
        self._governor = governor
        self._store = store
        self._finnhub_key = finnhub_api_key

    def _is_crypto(self, symbol: str) -> bool:
        return symbol.upper() in CRYPTO_PAIRS

    def get_quote(self, symbol: str) -> Quote | None:
        """Cached, rate-limited, circuit-broken current price for a symbol."""
        symbol = symbol.upper()
        cached = self._cache.get("quote", symbol)
        if cached is not None:
            return Quote(**cached)

        source = "kraken" if self._is_crypto(symbol) else "finnhub"
        try:
            self._governor.guard(source)
        except (RateLimitExceeded, CircuitOpenError):
            return None

        try:
            if self._is_crypto(symbol):
                api_pair, result_key = CRYPTO_PAIRS[symbol]
                raw = kraken_rest.get_ticker(api_pair, result_key)
                quote = None if raw is None else Quote(symbol=symbol, price=raw["price"], ts=time.time(), source="kraken", open=raw["open"], high=raw["high"], low=raw["low"], volume=raw["volume"])
            else:
                if not self._finnhub_key:
                    return None
                raw = finnhub.get_quote(symbol, self._finnhub_key)
                quote = None if raw is None else Quote(symbol=symbol, price=raw["price"], ts=time.time(), source="finnhub", open=raw["open"], high=raw["high"], low=raw["low"], change=raw["change"], pct_change=raw["pct_change"])
        except requests.RequestException:
            self._governor.record_failure(source)
            return None

        self._governor.record_success(source)
        if quote is not None:
            self._cache.set("quote", symbol, quote.model_dump())
        return quote

    def get_candles(self, symbol: str, limit: int = 100) -> list[Candle]:
        """Kraken OHLC for crypto (free public endpoint). For equities,
        Finnhub's free tier has no candle endpoint for US exchanges — this
        reads back whatever has been persisted locally via record_candle(),
        which may be empty."""
        symbol = symbol.upper()
        if self._is_crypto(symbol):
            api_pair, _ = CRYPTO_PAIRS[symbol]
            try:
                self._governor.guard("kraken")
                resp = requests.get(KRAKEN_OHLC_URL, params={"pair": api_pair, "interval": 1}, timeout=8)
                resp.raise_for_status()
                data = resp.json()
            except (requests.RequestException, RateLimitExceeded, CircuitOpenError):
                self._governor.record_failure("kraken")
                return [Candle(**c) for c in self._store.get_candles(symbol, limit)]
            self._governor.record_success("kraken")
            if data.get("error"):
                return []
            (_pair_key, rows) = next(iter([(k, v) for k, v in data["result"].items() if k != "last"]), (None, []))
            candles = [Candle(symbol=symbol, ts=float(row[0]), open=float(row[1]), high=float(row[2]), low=float(row[3]), close=float(row[4]), volume=float(row[6])) for row in rows[-limit:]]
            for c in candles:
                self._store.upsert_candle(symbol, c.ts, c.open, c.high, c.low, c.close, c.volume)
            return candles
        return [Candle(**c) for c in self._store.get_candles(symbol, limit)]

    def get_orderbook(self, symbol: str, depth: int = 10) -> OrderBookSnapshot | None:
        """Kraken public depth for crypto. Not available for equities on
        Finnhub's free tier — returns None rather than a fake book."""
        symbol = symbol.upper()
        if not self._is_crypto(symbol):
            return None
        api_pair, _ = CRYPTO_PAIRS[symbol]
        try:
            self._governor.guard("kraken")
            resp = requests.get(KRAKEN_DEPTH_URL, params={"pair": api_pair, "count": depth}, timeout=8)
            resp.raise_for_status()
            data = resp.json()
        except (requests.RequestException, RateLimitExceeded, CircuitOpenError):
            self._governor.record_failure("kraken")
            return None
        self._governor.record_success("kraken")
        if data.get("error"):
            return None
        book = next(iter(data["result"].values()))
        return OrderBookSnapshot(
            symbol=symbol,
            ts=time.time(),
            bids=[OrderBookLevel(price=float(p), size=float(s)) for p, s, _ in book["bids"]],
            asks=[OrderBookLevel(price=float(p), size=float(s)) for p, s, _ in book["asks"]],
        )

    def get_news(self, symbol: str, days_back: int = 7) -> list[NewsItem]:
        """Finnhub company news for equities. No news source for crypto
        under this platform's data constraints — returns empty."""
        symbol = symbol.upper()
        if self._is_crypto(symbol) or not self._finnhub_key:
            return []
        try:
            self._governor.guard("finnhub")
            now = time.time()
            resp = requests.get(FINNHUB_NEWS_URL, params={"symbol": symbol, "from": time.strftime("%Y-%m-%d", time.gmtime(now - days_back * 86400)), "to": time.strftime("%Y-%m-%d", time.gmtime(now)), "token": self._finnhub_key}, timeout=8)
            resp.raise_for_status()
            data = resp.json()
        except (requests.RequestException, RateLimitExceeded, CircuitOpenError):
            self._governor.record_failure("finnhub")
            return []
        self._governor.record_success("finnhub")
        return [NewsItem(symbol=symbol, headline=item["headline"], url=item["url"], source=item.get("source", "finnhub"), ts=float(item["datetime"])) for item in data[:20]]

    def query_timeseries(self, kind: str, symbol: str, limit: int = 50) -> list[dict]:
        """Reads persisted candles/alerts/watchlist — the one tool that hits
        the timeseries store directly rather than a live upstream API."""
        if kind == "candles":
            return self._store.get_candles(symbol, limit)
        if kind == "alerts":
            return [a for a in self._store.get_recent_alerts(limit) if a["symbol"] == symbol]
        if kind == "watchlist":
            return [{"symbol": s} for s in self._store.get_watchlist()]
        raise ValueError(f"unknown timeseries kind: {kind}")


def build_default_governor() -> RateGovernor:
    governor = RateGovernor()
    governor.register("kraken", rate_per_s=1.0, capacity=3)
    governor.register("finnhub", rate_per_s=0.5, capacity=2)
    return governor
