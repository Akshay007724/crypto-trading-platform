"""Lightweight custom supervisor (not LangGraph — this build's scope is one
fully-wired agent, a graph framework would be pure overhead right now; the
routing contract below is the seam to swap in LangGraph later without
touching agent code).

Routes a user intent to the right subagent, enforces the "LLM down ->
deterministic terminal still works" rule, and caches outputs by
(intent, symbol, data_version).
"""

from __future__ import annotations

import time
from dataclasses import dataclass

from hft import config
from hft.agents.base import GuardrailViolation
from hft.agents.llm_client import LLMClient, LLMUnavailableError
from hft.agents.nl_query_agent import NLQueryAgent
from hft.agents.output_cache import AgentOutputCache
from hft.agents.stubs import AlertTriageAgent, MarketScreenerAgent, PortfolioAgent, ResearchAgent, TechnicalAnalysisAgent
from hft.tools.market_tools import MarketTools


@dataclass
class SupervisorResult:
    ok: bool
    agent: str
    output: dict | None
    error: str | None = None


class Supervisor:
    def __init__(self, tools: MarketTools, llm: LLMClient | None = None):
        self._tools = tools
        self._llm = llm or LLMClient()
        self._cache = AgentOutputCache(ttl_s=config.AGENT_OUTPUT_CACHE_TTL_S)
        self._agents = {
            "nl_query": NLQueryAgent(self._llm, tools),
            "research": ResearchAgent(self._llm, tools),
            "technical": TechnicalAnalysisAgent(self._llm, tools),
            "alert_triage": AlertTriageAgent(self._llm, tools),
            "screener": MarketScreenerAgent(self._llm, tools),
            "portfolio": PortfolioAgent(self._llm, tools),
        }

    @property
    def llm_available(self) -> bool:
        return self._llm.available

    def handle_nl_query(self, question: str, symbol_hint: str = "") -> SupervisorResult:
        """Only routing path exercised end-to-end in this build — every
        other agent name is registered (for the allowlist/schema contract
        tests) but returns a graceful 'not implemented' result rather than
        crashing the supervisor."""
        if not self.llm_available:
            return SupervisorResult(ok=False, agent="nl_query", output=None, error="LLM layer unavailable (LLM_API_KEY unset) — deterministic quotes/charts below are unaffected.")

        data_version = str(int(time.time() // max(config.QUOTE_CACHE_TTL_S, 1)))
        cache_key_symbol = symbol_hint or "_"
        cached = self._cache.get("nl_query", cache_key_symbol, data_version)
        if cached is not None:
            return SupervisorResult(ok=True, agent="nl_query", output=cached)

        try:
            output = self._agents["nl_query"].run(question)
        except (GuardrailViolation, LLMUnavailableError) as exc:
            return SupervisorResult(ok=False, agent="nl_query", output=None, error=str(exc))

        payload = output.model_dump()
        self._cache.set("nl_query", cache_key_symbol, data_version, payload)
        return SupervisorResult(ok=True, agent="nl_query", output=payload)

    def handle_stub(self, agent_name: str, **kwargs) -> SupervisorResult:
        """Routes to a not-yet-wired agent; always returns a clean
        'not implemented' result instead of raising, so the supervisor
        itself never crashes on an unimplemented intent."""
        if agent_name not in self._agents:
            return SupervisorResult(ok=False, agent=agent_name, output=None, error=f"unknown agent '{agent_name}'")
        try:
            self._agents[agent_name].run(**kwargs)
        except NotImplementedError as exc:
            return SupervisorResult(ok=False, agent=agent_name, output=None, error=str(exc))
        raise AssertionError("stub agent unexpectedly returned a result")  # pragma: no cover
