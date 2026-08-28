"""Shared agent scaffolding: tool allowlist enforcement, max-step limit,
timeout, cost ceiling, structured-output validation, and a JSONL trace log
(a lightweight stand-in for OpenTelemetry/LangSmith — swap `AgentRun.trace()`
for a real exporter without touching agent logic)."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import ClassVar

from pydantic import BaseModel, ValidationError

from hft import config
from hft.agents.llm_client import LLMClient, LLMUnavailableError
from hft.tools.market_tools import MarketTools

_TRACE_PATH = Path("agent_traces.jsonl")


class GuardrailViolation(Exception):
    pass


@dataclass
class AgentRun:
    agent_name: str
    started_at: float = field(default_factory=time.monotonic)
    steps: int = 0
    cost_usd: float = 0.0
    tool_calls_made: list[str] = field(default_factory=list)

    def check_guardrails(self, max_steps: int, timeout_s: float, cost_ceiling_usd: float) -> None:
        if self.steps > max_steps:
            raise GuardrailViolation(f"{self.agent_name}: exceeded max_steps={max_steps}")
        if time.monotonic() - self.started_at > timeout_s:
            raise GuardrailViolation(f"{self.agent_name}: exceeded timeout_s={timeout_s}")
        if self.cost_usd > cost_ceiling_usd:
            raise GuardrailViolation(f"{self.agent_name}: exceeded cost_ceiling_usd={cost_ceiling_usd}")

    def trace(self, event: str, **fields) -> None:
        record = {"ts": time.time(), "agent": self.agent_name, "event": event, **fields}
        try:
            with _TRACE_PATH.open("a") as f:
                f.write(json.dumps(record, default=str) + "\n")
        except OSError:
            pass  # tracing is best-effort, never blocks an agent run


class BaseAgent:
    """Subclasses set `name`, `system_prompt`, `tool_allowlist`, `output_schema`."""

    name: str
    system_prompt: str
    tool_allowlist: ClassVar[set[str]]
    output_schema: type[BaseModel]

    def __init__(self, llm: LLMClient, tools: MarketTools):
        self._llm = llm
        self._tools = tools

    def _call_tool(self, run: AgentRun, tool_name: str, **kwargs):
        if tool_name not in self.tool_allowlist:
            raise GuardrailViolation(f"{self.name}: tool '{tool_name}' not in allowlist {self.tool_allowlist}")
        run.steps += 1
        run.check_guardrails(config.AGENT_MAX_STEPS, config.AGENT_TIMEOUT_S, config.AGENT_COST_CEILING_USD)
        run.tool_calls_made.append(tool_name)
        method = getattr(self._tools, tool_name)
        result = method(**kwargs)
        run.trace("tool_call", tool=tool_name, args=kwargs)
        return result

    def validate_output(self, raw: dict) -> BaseModel:
        try:
            return self.output_schema(**raw)
        except ValidationError as exc:
            raise GuardrailViolation(f"{self.name}: output failed schema validation: {exc}") from exc

    @property
    def available(self) -> bool:
        """Graceful degradation: UI checks this before invoking — if False,
        the deterministic terminal still works, only the agent console
        shows an unavailable notice."""
        return self._llm.available


__all__ = ["AgentRun", "BaseAgent", "GuardrailViolation", "LLMUnavailableError"]
