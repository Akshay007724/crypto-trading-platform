"""Research / Technical / Alert-Triage / Screener / Portfolio agents.

Scoped out of this build's "fully wired" set (see README) — each has its
real system prompt, tool allowlist, and output schema already defined so
the supervisor can route to them and the contract tests can validate their
schemas, but `run()` raises NotImplementedError instead of calling the LLM.
Wiring one up is: copy NLQueryAgent's `run()` shape, swap the tool spec list
and system prompt for the ones below.
"""

from __future__ import annotations

from typing import ClassVar

from hft.agents.base import BaseAgent
from hft.agents.schemas import AlertTriageOutput, PortfolioOutput, ResearchOutput, ScreenerOutput, TechnicalOutput


class ResearchAgent(BaseAgent):
    name = "research"
    system_prompt = "Summarize a security using Finnhub fundamentals + news, citing every source. Never state a fact without a citation."
    tool_allowlist: ClassVar[set[str]] = {"get_quote", "get_news"}
    output_schema = ResearchOutput

    def run(self, symbol: str) -> ResearchOutput:
        raise NotImplementedError("research agent: TODO — wire up like NLQueryAgent.run()")


class TechnicalAnalysisAgent(BaseAgent):
    name = "technical"
    system_prompt = "Compute RSI/MACD/MA crossovers over stored candles and flag setups. Indicators must be computed from get_candles output, never estimated."
    tool_allowlist: ClassVar[set[str]] = {"get_candles"}
    output_schema = TechnicalOutput

    def run(self, symbol: str) -> TechnicalOutput:
        raise NotImplementedError("technical agent: TODO — indicator math can be pure-Python (no LLM needed for the numbers), LLM only for the setup/rationale narrative")


class AlertTriageAgent(BaseAgent):
    name = "alert_triage"
    system_prompt = "Evaluate a fired price/volume alert, rank its significance, draft a notification."
    tool_allowlist: ClassVar[set[str]] = {"get_quote", "query_timeseries"}
    output_schema = AlertTriageOutput

    def run(self, alert_id: int) -> AlertTriageOutput:
        raise NotImplementedError("alert_triage agent: TODO — read alert via query_timeseries('alerts', ...), compare against current get_quote")


class MarketScreenerAgent(BaseAgent):
    name = "screener"
    system_prompt = "Translate a natural-language screen (e.g. 'large-cap tech down >3% today') into a scan over the watchlist via query_timeseries + get_quote."
    tool_allowlist: ClassVar[set[str]] = {"get_quote", "query_timeseries"}
    output_schema = ScreenerOutput

    def run(self, query: str) -> ScreenerOutput:
        raise NotImplementedError("screener agent: TODO — needs a symbol universe; current watchlist table is a reasonable starting scan set")


class PortfolioAgent(BaseAgent):
    name = "portfolio"
    system_prompt = "Compute exposure, P&L, and correlation across the user's watchlist using get_quote + query_timeseries."
    tool_allowlist: ClassVar[set[str]] = {"get_quote", "query_timeseries"}
    output_schema = PortfolioOutput

    def run(self) -> PortfolioOutput:
        raise NotImplementedError("portfolio agent: TODO — needs a positions/cost-basis table (not yet in TimeseriesStore) before P&L is meaningful")
