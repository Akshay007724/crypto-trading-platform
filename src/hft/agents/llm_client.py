"""Thin OpenAI-compatible LLM client. Defaults to OpenRouter, but works with
any OpenAI-compatible provider by swapping LLM_BASE_URL/LLM_MODEL — no
provider-specific SDK dependency needed."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass

from hft import config

# Rough per-1M-token cost used only to estimate spend against
# AGENT_COST_CEILING_USD (a soft guardrail, not billing) — OpenRouter serves
# many models at different prices, so this is deliberately a conservative
# placeholder (roughly DeepSeek-tier pricing) rather than per-model exact.
# OpenRouter's response includes real cost accounting on their dashboard.
_INPUT_USD_PER_M = 0.5
_OUTPUT_USD_PER_M = 1.5


@dataclass
class LLMResponse:
    content: str
    tool_calls: list[dict]
    estimated_cost_usd: float
    latency_s: float


class LLMUnavailableError(Exception):
    """Raised when no API key is configured — callers must degrade gracefully."""


class LLMClient:
    def __init__(self, api_key: str = "", base_url: str = "", model: str = ""):
        self._api_key = api_key or config.LLM_API_KEY
        self._base_url = base_url or config.LLM_BASE_URL
        self._model = model or config.LLM_MODEL
        self._client = None

    @property
    def available(self) -> bool:
        return bool(self._api_key)

    def _ensure_client(self):
        if self._client is None:
            if not self._api_key:
                raise LLMUnavailableError("LLM_API_KEY not configured")
            from openai import OpenAI  # imported lazily so the package is optional until an agent actually runs

            self._client = OpenAI(api_key=self._api_key, base_url=self._base_url)
        return self._client

    def chat(self, system_prompt: str, user_prompt: str, tools: list[dict] | None = None, tool_choice: str = "auto") -> LLMResponse:
        client = self._ensure_client()
        start = time.monotonic()
        kwargs = {}
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = tool_choice
        resp = client.chat.completions.create(
            model=self._model,
            messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}],
            **kwargs,
        )
        latency = time.monotonic() - start
        choice = resp.choices[0].message
        tool_calls = []
        if choice.tool_calls:
            for tc in choice.tool_calls:
                tool_calls.append({"name": tc.function.name, "arguments": json.loads(tc.function.arguments)})
        usage = resp.usage
        cost = 0.0
        if usage:
            cost = (usage.prompt_tokens / 1_000_000) * _INPUT_USD_PER_M + (usage.completion_tokens / 1_000_000) * _OUTPUT_USD_PER_M
        return LLMResponse(content=choice.content or "", tool_calls=tool_calls, estimated_cost_usd=cost, latency_s=latency)
