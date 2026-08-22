import requests

QUOTE_URL = "https://finnhub.io/api/v1/quote"


def parse_quote(raw: dict) -> dict | None:
    """Normalize a Finnhub /quote response. Finnhub returns all-zero
    fields for an unknown symbol rather than an error status, so that
    shape is treated as "no data" here.
    """
    if raw.get("c") == 0 and raw.get("t") == 0:
        return None
    return {
        "price": raw["c"],
        "change": raw["d"],
        "pct_change": raw["dp"],
        "high": raw["h"],
        "low": raw["l"],
        "open": raw["o"],
        "prev_close": raw["pc"],
    }


def get_quote(symbol: str, api_key: str) -> dict | None:
    resp = requests.get(QUOTE_URL, params={"symbol": symbol, "token": api_key}, timeout=8)
    resp.raise_for_status()
    return parse_quote(resp.json())
