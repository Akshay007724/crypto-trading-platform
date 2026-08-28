"""Streamlit agent-console panel — NL query in, structured+cited answer out.

Invoked on-demand (button click), never on the auto-refresh timer: agents
never sit on the live tick path, per the platform's data/reasoning-plane
separation rule. Builds its own MarketTools/Supervisor from `hft.config`
env vars each render — cheap, and keeps this module free of global state.
"""

from __future__ import annotations

import streamlit as st

from hft import config
from hft.agents.supervisor import Supervisor
from hft.data_plane.cache import QuoteCache
from hft.data_plane.timeseries import TimeseriesStore
from hft.tools.market_tools import MarketTools, build_default_governor


@st.cache_resource
def get_market_tools(finnhub_key: str) -> MarketTools:
    return MarketTools(
        quote_cache=QuoteCache(config.UPSTASH_REDIS_URL, ttl_s=config.QUOTE_CACHE_TTL_S),
        governor=build_default_governor(),
        store=TimeseriesStore(config.LOCAL_TIMESERIES_DB),
        finnhub_api_key=finnhub_key,
    )


@st.cache_resource
def _get_supervisor(finnhub_key: str) -> Supervisor:
    return Supervisor(get_market_tools(finnhub_key))


def render_agent_console(finnhub_key: str = "", show_header: bool = True) -> None:
    if show_header:
        st.subheader("Agent Console")
    supervisor = _get_supervisor(finnhub_key)

    if not supervisor.llm_available:
        st.caption("LLM layer unavailable — set LLM_API_KEY to enable. Quotes/charts above are unaffected.")
        return

    question = st.text_input("Ask about a symbol", placeholder="What's BTC/USD doing right now?", key="agent_console_question")
    if st.button("Ask", key="agent_console_ask") and question:
        with st.spinner("Agent thinking..."):
            result = supervisor.handle_nl_query(question)
        if not result.ok:
            st.error(result.error)
        else:
            output = result.output
            st.write(output["answer"])
            if output["citations"]:
                st.caption("Sources: " + ", ".join(c["label"] for c in output["citations"]))
