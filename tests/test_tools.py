from hft.data_plane.cache import QuoteCache
from hft.data_plane.timeseries import TimeseriesStore
from hft.tools.market_tools import MarketTools, build_default_governor


def _tools(tmp_path) -> MarketTools:
    return MarketTools(
        quote_cache=QuoteCache("redis://localhost:1", ttl_s=5),  # unreachable on purpose -> exercises fallback mode
        governor=build_default_governor(),
        store=TimeseriesStore(str(tmp_path / "test.db")),
        finnhub_api_key="",
    )


def test_get_quote_returns_none_for_stocks_without_finnhub_key(tmp_path):
    tools = _tools(tmp_path)
    assert tools.get_quote("AAPL") is None


def test_get_orderbook_returns_none_for_equities(tmp_path):
    tools = _tools(tmp_path)
    assert tools.get_orderbook("AAPL") is None


def test_get_news_returns_empty_for_crypto(tmp_path):
    tools = _tools(tmp_path)
    assert tools.get_news("BTC/USD") == []


def test_query_timeseries_watchlist_empty_by_default(tmp_path):
    tools = _tools(tmp_path)
    assert tools.query_timeseries("watchlist", "BTC/USD") == []


def test_query_timeseries_rejects_unknown_kind(tmp_path):
    tools = _tools(tmp_path)
    try:
        tools.query_timeseries("bogus", "BTC/USD")
        assert False, "expected ValueError"
    except ValueError:
        pass


def test_quote_cache_roundtrip_falls_back_without_redis():
    cache = QuoteCache("redis://localhost:1", ttl_s=5)
    assert cache.get("quote", "BTC/USD") is None
    cache.set("quote", "BTC/USD", {"symbol": "BTC/USD", "price": 100.0, "ts": 1.0, "source": "kraken"})
    assert cache.get("quote", "BTC/USD")["price"] == 100.0
