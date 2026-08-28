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
from hft.ui.agent_console import get_market_tools, render_agent_console

st.set_page_config(page_title="Signal Deck", page_icon="📈", layout="wide")

CRYPTO_PAIRS = {
    "BTC/USD": ("XBTUSD", "XXBTZUSD"),
    "ETH/USD": ("ETHUSD", "XETHZUSD"),
    "SOL/USD": ("SOLUSD", "SOLUSD"),
    "ADA/USD": ("ADAUSD", "ADAUSD"),
}
STOCK_SYMBOLS = ["AAPL", "MSFT", "GOOGL", "TSLA", "AMZN", "NVDA"]

# Dense dashboard visual language — slate/blue-black fintech palette (matches
# .streamlit/config.toml's [theme]), Inter throughout, tight spacing. Chosen
# after two rejected directions (retro-terminal, then an overly sparse warm
# "Focus mode") — this one mirrors TradingView/Robinhood's density.
st.markdown(
    textwrap.dedent(
        """\
        <link rel="preconnect" href="https://fonts.googleapis.com">
        <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
        <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap" rel="stylesheet">
        <style>
        html, body, [class*="css"] { font-family: 'Inter', sans-serif; }
        .sd-stat-row { display:flex; gap:24px; flex-wrap:wrap; align-items:baseline; margin-bottom:10px; }
        .sd-price-block { display:flex; align-items:baseline; gap:10px; margin-right:8px; }
        .sd-px { font-size:26px; font-weight:700; }
        .sd-chg { font-size:13px; font-weight:700; padding:2px 9px; border-radius:5px; }
        .sd-chg.up { color:#22c55e; background:rgba(34,197,94,0.12); }
        .sd-chg.down { color:#ef4444; background:rgba(239,68,68,0.12); }
        .sd-mini-label { font-size:9.5px; color:#5b6b85; text-transform:uppercase; letter-spacing:0.04em; }
        .sd-mini-val { font-size:12.5px; font-weight:600; color:#f8fafc; }
        .sd-wrow { display:flex; align-items:center; gap:6px; padding:5px 2px; font-size:12.5px; border-left:2px solid transparent; }
        .sd-wrow.active { border-left-color:#3b82f6; background:rgba(59,130,246,0.08); }
        .sd-wsym { font-weight:600; flex:1; }
        .sd-wpx { color:#94a3b8; font-size:11.5px; margin-right:4px; }
        .sd-wchg { font-weight:700; font-size:11.5px; min-width:52px; text-align:right; }
        .sd-wchg.up { color:#22c55e; } .sd-wchg.down { color:#ef4444; }
        .sd-book-row { display:grid; grid-template-columns:1fr 1fr 1fr; font-size:11.5px; padding:2px 0; }
        .sd-book-price.a { color:#ef4444; } .sd-book-price.b { color:#22c55e; }
        .sd-book-mid { display:flex; justify-content:space-between; font-size:11px; color:#94a3b8; padding:5px 0; margin:2px 0; border-top:1px solid #1a2236; border-bottom:1px solid #1a2236; }
        [data-testid="stExpander"] { border-radius:8px; }
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
    finnhub_key = ""
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


@st.cache_data(ttl=5)
def fetch_watchlist() -> list[tuple[str, dict | None]]:
    """Crypto-only quick-glance watchlist — Kraken's public REST needs no key,
    so this always works without asking the user for anything."""
    return [(pair, get_ticker(api_pair, result_key)) for pair, (api_pair, result_key) in CRYPTO_PAIRS.items()]


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

    col_watch, col_center, col_right = st.columns([1, 3, 1.3], gap="medium")

    with col_watch:
        st.caption("WATCHLIST")
        for pair, wq in fetch_watchlist():
            if wq is None:
                continue
            w_change = wq["price"] - wq["open"]
            w_pct = (w_change / wq["open"] * 100) if wq["open"] else 0.0
            w_dir = "up" if w_change >= 0 else "down"
            active_cls = "active" if asset_class == "Crypto" and pair == symbol else ""
            st.markdown(
                f'<div class="sd-wrow {active_cls}"><span class="sd-wsym">{pair}</span>'
                f'<span class="sd-wpx">{wq["price"]:,.2f}</span>'
                f'<span class="sd-wchg {w_dir}">{w_pct:+.2f}%</span></div>',
                unsafe_allow_html=True,
            )

    with col_center:
        volume_chip = f'<div><div class="sd-mini-label">VOLUME</div><div class="sd-mini-val">{quote["volume"]:,.2f}</div></div>' if has_volume else ""
        stat_html = textwrap.dedent(
            f"""\
            <div class="sd-stat-row">
            <div class="sd-price-block"><span class="sd-px">{quote['price']:,.2f}</span><span class="sd-chg {direction}">{arrow} {change:+,.2f} ({pct_change:+.2f}%)</span></div>
            <div><div class="sd-mini-label">{symbol} · {source_label}</div></div>
            </div>
            <div class="sd-stat-row">
            <div><div class="sd-mini-label">OPEN</div><div class="sd-mini-val">{quote['open']:,.2f}</div></div>
            <div><div class="sd-mini-label">HIGH</div><div class="sd-mini-val">{quote['high']:,.2f}</div></div>
            <div><div class="sd-mini-label">LOW</div><div class="sd-mini-val">{quote['low']:,.2f}</div></div>
            {volume_chip}
            </div>
            """
        )
        st.markdown(stat_html, unsafe_allow_html=True)

        history = st.session_state.history[symbol]
        if len(history) >= 2:
            # Streamlit's native charts force a zero baseline, which flattens a
            # price series into an unreadable line near the top — build the
            # y-scale explicitly instead of relying on st.line_chart/area_chart.
            chart_df = pd.DataFrame({"i": range(len(history)), "price": history})
            pad = (max(history) - min(history)) * 0.15 or max(history) * 0.002
            line = (
                alt.Chart(chart_df)
                .mark_line(color="#22c55e" if direction == "up" else "#ef4444", strokeWidth=2)
                .encode(
                    x=alt.X("i:Q", axis=None),
                    y=alt.Y("price:Q", scale=alt.Scale(domain=[min(history) - pad, max(history) + pad]), axis=alt.Axis(title=None)),
                )
                .properties(height=280)
            )
            st.altair_chart(line, use_container_width=True)
        else:
            st.caption("Collecting price history — refresh a few times to see the chart.")

        if has_volume:
            volume_history = st.session_state.volume_history.get(symbol, [])
            if len(volume_history) >= 2:
                st.bar_chart(pd.DataFrame({"24h volume": volume_history}), height=90)

    with col_right:
        st.caption("ORDER BOOK")
        tools = get_market_tools(finnhub_key)
        book = tools.get_orderbook(symbol) if asset_class == "Crypto" else None
        if book is None:
            st.caption("Not available for equities on Finnhub's free tier." if asset_class == "Stocks" else "Order book temporarily unavailable.")
        else:
            for level in reversed(book.asks[:3]):
                st.markdown(f'<div class="sd-book-row"><span></span><span class="sd-book-price a" style="text-align:center;">{level.price:,.2f}</span><span style="text-align:right;">{level.size:.4f}</span></div>', unsafe_allow_html=True)
            spread = book.asks[0].price - book.bids[0].price if book.asks and book.bids else 0.0
            st.markdown(f'<div class="sd-book-mid"><span>Spread</span><span>{spread:,.2f}</span></div>', unsafe_allow_html=True)
            for level in book.bids[:3]:
                st.markdown(f'<div class="sd-book-row"><span>{level.size:.4f}</span><span class="sd-book-price b" style="text-align:center;">{level.price:,.2f}</span><span></span></div>', unsafe_allow_html=True)

        st.divider()
        st.caption("ASK THE AGENT")
        render_agent_console(finnhub_key=finnhub_key, show_header=False)

    with st.expander("Strategy signals"):
        signals = st.session_state.signals.get(symbol, [])
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
