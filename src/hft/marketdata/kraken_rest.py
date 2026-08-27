import requests

TICKER_URL = "https://api.kraken.com/0/public/Ticker"


def parse_ticker(raw: dict, result_key: str) -> dict | None:
    if raw.get("error"):
        return None
    entry = raw["result"][result_key]
    return {
        "price": float(entry["c"][0]),
        "high": float(entry["h"][1]),
        "low": float(entry["l"][1]),
        "open": float(entry["o"]),
        "volume": float(entry["v"][1]),
    }


def get_ticker(pair: str, result_key: str) -> dict | None:
    resp = requests.get(TICKER_URL, params={"pair": pair}, timeout=8)
    resp.raise_for_status()
    return parse_ticker(resp.json(), result_key)
