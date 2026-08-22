from hft.marketdata.finnhub import parse_quote
from hft.marketdata.kraken_rest import parse_ticker


def test_parses_finnhub_quote_response():
    # Arrange: documented Finnhub /quote response shape
    raw = {"c": 233.15, "d": 1.42, "dp": 0.6112, "h": 234.0, "l": 231.2, "o": 232.0, "pc": 231.73, "t": 1755000000}

    # Act
    quote = parse_quote(raw)

    # Assert
    assert quote == {
        "price": 233.15,
        "change": 1.42,
        "pct_change": 0.6112,
        "high": 234.0,
        "low": 231.2,
        "open": 232.0,
        "prev_close": 231.73,
    }


def test_finnhub_quote_with_no_data_returns_none():
    # Arrange: Finnhub returns all-zero fields for an invalid/unknown symbol
    raw = {"c": 0, "d": 0, "dp": 0, "h": 0, "l": 0, "o": 0, "pc": 0, "t": 0}

    # Act / Assert
    assert parse_quote(raw) is None


def test_parses_kraken_ticker_response():
    # Arrange: real response shape captured live from api.kraken.com/0/public/Ticker?pair=XBTUSD
    raw = {
        "error": [],
        "result": {
            "XXBTZUSD": {
                "a": ["77285.80000", "1", "1.000"],
                "b": ["77285.70000", "2", "2.000"],
                "c": ["77285.70000", "0.00044573"],
                "v": ["3103.72914602", "4339.93849337"],
                "p": ["77635.74685", "77686.78915"],
                "t": [61805, 91752],
                "l": ["76016.30000", "76016.30000"],
                "h": ["78800.00000", "78800.00000"],
                "o": "78327.70000",
            }
        },
    }

    # Act
    ticker = parse_ticker(raw, "XXBTZUSD")

    # Assert
    assert ticker == {"price": 77285.7, "high": 78800.0, "low": 76016.3, "open": 78327.7}


def test_kraken_ticker_error_response_returns_none():
    # Arrange: Kraken returns a non-empty "error" array on a bad pair
    raw = {"error": ["EQuery:Unknown asset pair"], "result": {}}

    # Act / Assert
    assert parse_ticker(raw, "XXBTZUSD") is None
