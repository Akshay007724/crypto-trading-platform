"""Structured output schemas — one per agent. Every agent run is validated
against its schema before it's allowed to reach the UI (see base.py)."""

from __future__ import annotations

from pydantic import BaseModel


class Citation(BaseModel):
    label: str  # e.g. "Kraken OHLC(BTC/USD)" or "Finnhub news: <headline>"
    tool: str  # which deterministic tool produced this fact


class NLQueryOutput(BaseModel):
    question: str
    answer: str
    citations: list[Citation]
    tool_calls_made: list[str]


class ResearchOutput(BaseModel):
    symbol: str
    summary: str
    citations: list[Citation]


class TechnicalOutput(BaseModel):
    symbol: str
    rsi: float | None
    macd: float | None
    macd_signal: float | None
    sma_fast: float | None
    sma_slow: float | None
    setup: str  # e.g. "bullish crossover", "overbought", "no setup"
    rationale: str


class AlertTriageOutput(BaseModel):
    symbol: str
    alert_id: int
    significance: str  # "low" | "medium" | "high"
    draft_notification: str


class ScreenerOutput(BaseModel):
    query: str
    matches: list[str]  # symbols
    rationale: str


class PortfolioOutput(BaseModel):
    total_exposure: float
    pnl: float
    correlations: dict[str, float]
    notes: str


AGENT_SCHEMAS: dict[str, type[BaseModel]] = {
    "nl_query": NLQueryOutput,
    "research": ResearchOutput,
    "technical": TechnicalOutput,
    "alert_triage": AlertTriageOutput,
    "screener": ScreenerOutput,
    "portfolio": PortfolioOutput,
}
