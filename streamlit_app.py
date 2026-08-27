import sys
import time
from pathlib import Path

import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).parent / "src"))

from hft.marketdata.finnhub import get_quote
from hft.marketdata.kraken_rest import get_ticker
from hft.strategies.moving_average import MovingAverageCrossover
from hft.types import Signal, Trade

st.set_page_config(page_title="Signal Deck", page_icon="📈", layout="wide")

CRYPTO_PAIRS = {
    "BTC/USD": ("XBTUSD", "XXBTZUSD"),
    "ETH/USD": ("ETHUSD", "XETHZUSD"),
    "SOL/USD": ("SOLUSD", "SOLUSD"),
    "ADA/USD": ("ADAUSD", "ADAUSD"),
}
STOCK_SYMBOLS = ["AAPL", "MSFT", "GOOGL", "TSLA", "AMZN", "NVDA"]

if "history" not in st.session_state:
    st.session_state.history = {}  # symbol -> list[float]
if "volume_history" not in st.session_state:
    st.session_state.volume_history = {}  # symbol -> list[float], crypto only (Kraken ticker has it, Finnhub free quote doesn't)
if "strategy" not in st.session_state:
    st.session_state.strategy = {}  # symbol -> MovingAverageCrossover
if "signals" not in st.session_state:
    st.session_state.signals = {}  # symbol -> list of (time, Signal)

st.sidebar.title("Signal Deck")
st.sidebar.caption("Polling-based market view — built for Streamlit Community Cloud, no background WS service.")

asset_class = st.sidebar.radio("Asset class", ["Crypto", "Stocks"])

if asset_class == "Crypto":
    symbol = st.sidebar.selectbox("Pair", list(CRYPTO_PAIRS.keys()))
else:
    symbol = st.sidebar.selectbox("Symbol", STOCK_SYMBOLS)
    try:
        default_key = st.secrets.get("FINNHUB_API_KEY", "")
    except Exception:
        default_key = ""  # no secrets.toml configured — user enters a key manually
    finnhub_key = st.sidebar.text_input(
        "Finnhub API key",
        value=default_key,
        type="password",
        help="Free key from finnhub.io — stored only in this session, never committed.",
    )

auto_refresh = st.sidebar.checkbox("Auto-refresh (every 10s)", value=False)
refresh_clicked = st.sidebar.button("Refresh now")

st.title(f"{symbol} — live signal")


def fetch_price(symbol: str) -> dict | None:
    if asset_class == "Crypto":
        api_pair, result_key = CRYPTO_PAIRS[symbol]
        return get_ticker(api_pair, result_key)
    if not finnhub_key:
        return None
    return get_quote(symbol, finnhub_key)


def update(symbol: str, quote: dict) -> None:
    history = st.session_state.history.setdefault(symbol, [])
    history.append(quote["price"])
    if len(history) > 300:
        history.pop(0)

    if "volume" in quote:
        volume_history = st.session_state.volume_history.setdefault(symbol, [])
        volume_history.append(quote["volume"])
        if len(volume_history) > 300:
            volume_history.pop(0)

    strategy = st.session_state.strategy.setdefault(symbol, MovingAverageCrossover(fast=3, slow=8))
    trade = Trade(exchange="poll", symbol=symbol, price=quote["price"], size=0, side="n/a", ts=int(time.time()))
    signal = strategy.on_trade(trade)
    if signal != Signal.HOLD:
        signals = st.session_state.signals.setdefault(symbol, [])
        signals.append((time.strftime("%H:%M:%S"), signal))


quote = fetch_price(symbol)

if quote is None:
    if asset_class == "Stocks" and not finnhub_key:
        st.info("Enter a Finnhub API key in the sidebar to load stock data. Free key: finnhub.io/register")
    else:
        st.error(f"No data returned for {symbol}.")
else:
    update(symbol, quote)

    has_volume = "volume" in quote
    cols = st.columns(5 if has_volume else 4)
    cols[0].metric("Price", f"{quote['price']:,.2f}")
    if "change" in quote:
        cols[1].metric("Change", f"{quote['change']:+,.2f}", f"{quote['pct_change']:+.2f}%")
    cols[2].metric("High", f"{quote['high']:,.2f}")
    cols[3].metric("Low", f"{quote['low']:,.2f}")
    if has_volume:
        cols[4].metric("24h Volume", f"{quote['volume']:,.2f}")

    history = st.session_state.history[symbol]
    if len(history) >= 2:
        st.subheader("Price")
        df = pd.DataFrame({"price": history})
        df["sma_fast"] = df["price"].rolling(3).mean()
        df["sma_slow"] = df["price"].rolling(8).mean()
        st.line_chart(df)
    else:
        st.caption("Collecting price history — refresh a few times to see the chart and SMA crossover.")

    st.subheader("Volume")
    if has_volume:
        volume_history = st.session_state.volume_history.get(symbol, [])
        if len(volume_history) >= 2:
            st.bar_chart(pd.DataFrame({"24h volume": volume_history}))
            st.caption("Kraken's rolling 24h volume, sampled on each refresh — not per-trade volume.")
        else:
            st.caption("Collecting volume history — refresh a few more times.")
    else:
        st.caption("Not available — Finnhub's free /quote endpoint doesn't return volume.")

    signals = st.session_state.signals.get(symbol, [])
    st.subheader("Strategy signals")
    st.caption("MovingAverageCrossover(3, 8) — same strategy class as the backtest engine, run on polled prices.")
    if signals:
        st.dataframe(
            pd.DataFrame(signals[::-1], columns=["time", "signal"]).assign(signal=lambda d: d["signal"].map(lambda s: s.value)),
            use_container_width=True,
            hide_index=True,
        )
    else:
        st.caption("No crossover yet.")

st.sidebar.divider()
st.sidebar.caption("Crypto: Kraken public REST. Stocks: Finnhub REST. Polled on each refresh — not a live WebSocket feed.")

if auto_refresh:
    time.sleep(10)
    st.rerun()
