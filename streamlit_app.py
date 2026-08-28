import sys
import textwrap
import time
from pathlib import Path

import altair as alt
import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).parent / "src"))

from hft.marketdata.finnhub import get_quote
from hft.marketdata.kraken_rest import get_ticker
from hft.strategies.moving_average import MovingAverageCrossover
from hft.types import Signal, Trade
from hft.ui.agent_console import render_agent_console

st.set_page_config(page_title="Signal Deck", page_icon="📈", layout="wide")

CRYPTO_PAIRS = {
    "BTC/USD": ("XBTUSD", "XXBTZUSD"),
    "ETH/USD": ("ETHUSD", "XETHZUSD"),
    "SOL/USD": ("SOLUSD", "SOLUSD"),
    "ADA/USD": ("ADAUSD", "ADAUSD"),
}
STOCK_SYMBOLS = ["AAPL", "MSFT", "GOOGL", "TSLA", "AMZN", "NVDA"]

# "Focus mode" visual language — warm dark palette, Calistoga display face for
# numbers, generous rounded cards. Colors mirror .streamlit/config.toml's
# [theme] so custom HTML blocks and native Streamlit widgets read as one
# surface rather than two competing themes.
st.markdown(
    textwrap.dedent(
        """\
        <link rel="preconnect" href="https://fonts.googleapis.com">
        <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
        <link href="https://fonts.googleapis.com/css2?family=Calistoga&family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
        <style>
        html, body, [class*="css"] { font-family: 'Inter', sans-serif; }
        .pulse-eyebrow { display:flex; align-items:center; gap:8px; font-size:13px; color:#a89bb0; margin-bottom:4px; }
        .pulse-dot { width:7px; height:7px; border-radius:50%; background:#7ee8b8; box-shadow:0 0 8px #7ee8b8; }
        .pulse-hero-row { display:flex; align-items:flex-end; gap:16px; flex-wrap:wrap; margin-bottom:18px; }
        .pulse-hero-price { font-family:'Calistoga', Georgia, serif; font-size:56px; line-height:1; letter-spacing:-0.01em; }
        .pulse-change-pill { font-size:14px; font-weight:600; padding:5px 12px; border-radius:999px; margin-bottom:9px; }
        .pulse-change-pill.up { color:#7ee8b8; background:rgba(126,232,184,0.14); }
        .pulse-change-pill.down { color:#ff98a3; background:rgba(255,152,163,0.14); }
        .pulse-stat-row { display:flex; gap:22px; flex-wrap:wrap; margin:16px 0 8px; }
        .pulse-stat-label { font-size:11px; color:#6b5f75; margin-bottom:3px; }
        .pulse-stat-val { font-family:'JetBrains Mono', ui-monospace, monospace; font-size:14px; color:#f6f2f5; }
        [data-testid="stExpander"] { border-radius:20px; overflow:hidden; }
        </style>
        """
    ),
    unsafe_allow_html=True,
)

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

    source_label = "Kraken · Spot" if asset_class == "Crypto" else "Finnhub · Equity"
    has_volume = "volume" in quote
    if "change" in quote:
        change, pct_change = quote["change"], quote["pct_change"]
    else:
        change = quote["price"] - quote["open"]
        pct_change = (change / quote["open"] * 100) if quote["open"] else 0.0
    direction = "up" if change >= 0 else "down"
    arrow = "▲" if change >= 0 else "▼"

    volume_chip = f'<div><div class="pulse-stat-label">VOLUME</div><div class="pulse-stat-val">{quote["volume"]:,.2f}</div></div>' if has_volume else ""
    hero_html = textwrap.dedent(
        f"""\
        <div class="pulse-eyebrow"><span class="pulse-dot"></span>{symbol} · {source_label}</div>
        <div class="pulse-hero-row">
        <span class="pulse-hero-price">{quote['price']:,.2f}</span>
        <span class="pulse-change-pill {direction}">{arrow} {change:+,.2f} ({pct_change:+.2f}%)</span>
        </div>
        <div class="pulse-stat-row">
        <div><div class="pulse-stat-label">OPEN</div><div class="pulse-stat-val">{quote['open']:,.2f}</div></div>
        <div><div class="pulse-stat-label">HIGH</div><div class="pulse-stat-val">{quote['high']:,.2f}</div></div>
        <div><div class="pulse-stat-label">LOW</div><div class="pulse-stat-val">{quote['low']:,.2f}</div></div>
        {volume_chip}
        </div>
        """
    )
    st.markdown(hero_html, unsafe_allow_html=True)

    history = st.session_state.history[symbol]
    if len(history) >= 2:
        # Streamlit's native charts force a zero baseline, which flattens a
        # price series into an unreadable line near the top — build the
        # y-scale explicitly instead of relying on st.line_chart/area_chart.
        chart_df = pd.DataFrame({"i": range(len(history)), "price": history})
        pad = (max(history) - min(history)) * 0.15 or max(history) * 0.002
        line = (
            alt.Chart(chart_df)
            .mark_line(color="#7ee8b8", strokeWidth=2.5)
            .encode(
                x=alt.X("i:Q", axis=None),
                y=alt.Y("price:Q", scale=alt.Scale(domain=[min(history) - pad, max(history) + pad]), axis=alt.Axis(title=None)),
            )
            .properties(height=280)
        )
        st.altair_chart(line, use_container_width=True)
    else:
        st.caption("Collecting price history — refresh a few times to see the chart.")

    with st.expander(f"💬  Ask Pulse about {symbol}", expanded=True):
        render_agent_console(finnhub_key=finnhub_key if asset_class == "Stocks" else "", show_header=False)

    with st.expander("Volume & strategy signals"):
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
