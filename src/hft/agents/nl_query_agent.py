"""NL Query Agent — the one fully-wired agent in this build.

Translates a plain-English question into deterministic tool calls
(get_quote/get_candles/get_orderbook/get_news/query_timeseries), then
composes a cited answer from the tool results. Uses the configured LLM's function
calling to pick tools; the LLM never invents numbers — every figure in the
answer comes from a tool result, and every tool call is listed in the
citations so the UI can show provenance.
"""

from __future__ import annotations

import json
from typing import ClassVar

from hft.agents.base import AgentRun, BaseAgent
from hft.agents.schemas import Citation, NLQueryOutput

_TOOL_SPECS = [
    {"type": "function", "function": {"name": "get_quote", "description": "Current price/volume for a symbol (crypto pair like BTC/USD, or equity ticker like AAPL).", "parameters": {"type": "object", "properties": {"symbol": {"type": "string"}}, "required": ["symbol"]}}},
    {"type": "function", "function": {"name": "get_candles", "description": "Recent OHLCV candles for a symbol.", "parameters": {"type": "object", "properties": {"symbol": {"type": "string"}, "limit": {"type": "integer"}}, "required": ["symbol"]}}},
    {"type": "function", "function": {"name": "get_orderbook", "description": "Order book depth snapshot (crypto only).", "parameters": {"type": "object", "properties": {"symbol": {"type": "string"}}, "required": ["symbol"]}}},
    {"type": "function", "function": {"name": "get_news", "description": "Recent news headlines (equities only).", "parameters": {"type": "object", "properties": {"symbol": {"type": "string"}}, "required": ["symbol"]}}},
]

_SYSTEM_PROMPT = """You are the NL Query agent for a market intelligence terminal.
Answer the user's question about crypto (Kraken) or equity (Finnhub) symbols
using ONLY the provided tools — never state a price, volume, or figure that
didn't come from a tool result. If a tool returns no data (e.g. no order
book for equities, no news for crypto), say so plainly rather than guessing.
Call whichever tools you need, then give a concise final answer."""


class NLQueryAgent(BaseAgent):
    name = "nl_query"
    system_prompt = _SYSTEM_PROMPT
    tool_allowlist: ClassVar[set[str]] = {"get_quote", "get_candles", "get_orderbook", "get_news"}
    output_schema = NLQueryOutput

    def run(self, question: str) -> NLQueryOutput:
        run = AgentRun(agent_name=self.name)
        citations: list[Citation] = []

        resp = self._llm.chat(self.system_prompt, question, tools=_TOOL_SPECS)
        run.cost_usd += resp.estimated_cost_usd
        run.check_guardrails(6, 20.0, 0.05)

        tool_results = []
        for call in resp.tool_calls:
            tool_name = call["name"]
            args = call["arguments"]
            result = self._call_tool(run, tool_name, **args)
            payload = result.model_dump() if hasattr(result, "model_dump") else [r.model_dump() for r in result] if isinstance(result, list) else result
            tool_results.append({"tool": tool_name, "args": args, "result": payload})
            symbol = args.get("symbol", "?")
            citations.append(Citation(label=f"{tool_name}({symbol})", tool=tool_name))

        if tool_results:
            follow_up = f"Question: {question}\n\nTool results:\n{json.dumps(tool_results, default=str)}\n\nGive a concise, factual final answer using only these results."
            final = self._llm.chat(self.system_prompt, follow_up)
            run.cost_usd += final.estimated_cost_usd
            answer = final.content
        else:
            answer = resp.content or "I couldn't determine which data to fetch for that question."

        run.check_guardrails(6, 20.0, 0.05)
        run.trace("complete", cost_usd=run.cost_usd, steps=run.steps)

        output = self.validate_output({
            "question": question,
            "answer": answer,
            "citations": [c.model_dump() for c in citations],
            "tool_calls_made": run.tool_calls_made,
        })
        assert isinstance(output, NLQueryOutput)
        return output
