# Crypto/Stocks Market Intelligence Platform

Streamlit terminal over Kraken (crypto) + Finnhub (equities), with an
agentic reasoning layer on top of the deterministic data plane.

## Architecture

```
                    ┌────────────────────────────────────────┐
                    │              Streamlit UI               │
                    │  live quotes/charts   │  Agent Console   │
                    │  (auto-refresh)       │  (on-demand only)│
                    └──────────┬─────────────────────┬────────┘
                               │                      │
                               ▼                      ▼
                    ┌─────────────────┐   ┌──────────────────────┐
                    │   DATA PLANE     │   │  ORCHESTRATION LAYER │
                    │  (deterministic) │◄──┤   Supervisor (custom) │
                    │                  │   │  routes intent →      │
                    │ tools/market_    │   │  subagent              │
                    │   tools.py       │   └──────────┬────────────┘
                    │  get_quote            │            │
                    │  get_candles          │   ┌────────┴─────────┐
                    │  get_orderbook        │   │  6 subagents      │
                    │  get_news             │   │  (Pydantic output, │
                    │  query_timeseries     │   │   tool allowlist,  │
                    │                        │   │   guardrails)      │
                    │ data_plane/            │   │  NL Query — REAL   │
                    │  cache.py (Redis TTL)  │   │  Research — stub   │
                    │  ratelimit.py (token   │   │  Technical — stub  │
                    │   bucket + circuit     │   │  AlertTriage — stub│
                    │   breaker)             │   │  Screener — stub   │
                    │  timeseries.py         │   │  Portfolio — stub  │
                    │   (SQLite / Supabase)  │   └────────┬───────────┘
                    │  schemas.py (Quote,    │            │
                    │   Candle, OrderBook,   │            ▼
                    │   NewsItem)            │   LLM (OpenRouter,
                    └──────────┬─────────────┘    API) via agents/llm_client.py
                               │
                    ┌──────────┴──────────┐
                    │ Kraken REST/WS       │
                    │ Finnhub REST         │
                    └──────────────────────┘
```

**Data plane vs. reasoning plane.** Live tick rendering never touches an
LLM — `streamlit_app.py`'s quote/chart panels call `hft.marketdata.*`
directly (as before this build) and stay on the auto-refresh timer. The
Agent Console is a separate, on-demand panel: it calls the same
`tools/market_tools.py` functions, but only when the user clicks "Ask." If
`LLM_API_KEY` is unset, the console shows an "unavailable" notice and
the rest of the app is unaffected — this is enforced in
`hft.agents.supervisor.Supervisor.llm_available`.

**What's fully wired vs. stubbed** (see [Build scope](#build-scope) below).

## Repo layout

New code nests under `src/hft/` (matching the existing package layout,
`pyproject.toml`'s `pythonpath = ["src"]`) rather than the flat
`data_plane/`, `agents/`, `tools/` top-level dirs one might reach for on a
green-field repo — reusing the established import convention.

```
src/hft/
  data_plane/
    schemas.py      # Quote, Candle, OrderBookSnapshot, NewsItem (Pydantic)
    cache.py         # QuoteCache — sync Redis w/ TTL, falls back to in-proc dict
    ratelimit.py      # TokenBucket, CircuitBreaker, RateGovernor, call_with_backoff
    timeseries.py      # TimeseriesStore — SQLite now, Supabase Postgres later (same interface)
  tools/
    market_tools.py   # MarketTools: get_quote/get_candles/get_orderbook/get_news/query_timeseries
  agents/
    schemas.py         # one Pydantic output schema per subagent
    llm_client.py        # LLMClient (OpenAI-compatible SDK, defaults to OpenRouter)
    base.py               # BaseAgent, AgentRun (guardrails: allowlist/steps/timeout/cost, JSONL trace)
    output_cache.py        # AgentOutputCache keyed by (intent, symbol, data_version)
    nl_query_agent.py       # NLQueryAgent — fully wired
    stubs.py                 # Research/Technical/AlertTriage/Screener/Portfolio — schema+prompt only
    supervisor.py              # Supervisor — routes intents, degrades gracefully
  ui/
    agent_console.py           # Streamlit panel, on-demand only
  config.py                     # env-var config (existing file, extended)
  marketdata/, connectors/, storage/, ingestion.py, api.py, main.py   # existing, unchanged
streamlit_app.py    # existing entrypoint, +2 lines to mount the Agent Console
tests/
  test_ratelimit.py, test_tools.py, test_agent_schemas.py, test_supervisor.py   # new
  test_backtest.py, test_data.py, test_execution.py, test_ingestion.py,
  test_kraken_connector.py, test_marketdata.py, test_moving_average.py         # existing
.github/workflows/ci.yml   # ruff + mypy + pytest
.env.example
```

## Build scope (this pass)

Per explicit scoping in this session, this build is **"Scaffold + 1 real
agent"**, not the full 6-agent build:

- **NL Query Agent** — fully wired via LLM function calling (OpenRouter by default), real
  end-to-end path: question → tool calls → cited answer. This is the one
  agent exercised by the integration test (`tests/test_supervisor.py`).
- **Research / Technical Analysis / Alert Triage / Market Screener /
  Portfolio agents** — real system prompt, tool allowlist, and Pydantic
  output schema each (see `agents/stubs.py`), registered with the
  supervisor so allowlist/schema contract tests pass, but `run()` raises
  `NotImplementedError` with a TODO note on how to wire it (copy
  `NLQueryAgent.run()`'s shape). The supervisor treats this as a clean,
  expected outcome — it never crashes on an unimplemented intent.
- **LLM backend**: OpenRouter by default (OpenAI-compatible API — `openai`
  SDK pointed at `https://openrouter.ai/api/v1`, model `deepseek/deepseek-chat`).
  Swap `LLM_BASE_URL`/`LLM_MODEL` for DeepSeek direct or any other
  OpenAI-compatible provider. Not Anthropic/LangGraph as in the
  original spec text — swapped per this session's explicit choice.
- **Orchestrator**: a small hand-rolled `Supervisor` class, not LangGraph —
  proportionate to one real agent; the routing contract (`SupervisorResult`,
  per-agent registration dict) is the seam to swap in LangGraph later
  without touching agent code.
- **Infra**: no live provisioning. `SUPABASE_URL` unset → `TimeseriesStore`
  falls back to a local SQLite file. `UPSTASH_REDIS_URL` unset → falls back
  to `REDIS_URL` (the existing docker-compose Redis), and `QuoteCache`
  further falls back to an in-process dict if even that's unreachable.
  `LLM_API_KEY` unset → Agent Console shows "unavailable",
  deterministic terminal fully functional.
- **Tracing**: a JSONL file (`agent_traces.jsonl`) written by
  `AgentRun.trace()`, not real OpenTelemetry/LangSmith — same interface,
  swap the sink when there's somewhere to export to.

## Data provenance limits

Kraken and Finnhub free tiers don't cover everything the original spec asks
for. `tools/market_tools.py` returns `None`/`[]` rather than fabricating
data for:

- **Equity order book** — not on Finnhub's free tier.
- **Equity candles beyond what's been locally cached** — Finnhub's free
  tier has no candle endpoint for US exchanges; `get_candles` for a stock
  reads back whatever `TimeseriesStore` has persisted, which starts empty.
- **Crypto news** — no news source under the Kraken/Finnhub-only
  constraint.

## Running locally

```bash
pip install -r requirements.txt
cp .env.example .env   # fill in FINNHUB_API_KEY and (optionally) LLM_API_KEY
streamlit run streamlit_app.py
```

No Redis/Supabase account needed to try the Agent Console — it works with
local SQLite + in-process cache fallback. Set `LLM_API_KEY` to enable it —
default provider is OpenRouter (openrouter.ai/keys); swap `LLM_BASE_URL`/
`LLM_MODEL` for DeepSeek direct or any other OpenAI-compatible provider.

## Tests / CI

```bash
pytest              # 41 tests: existing backtest/ingestion/marketdata suite + new data-plane/tools/agent suite
ruff check .
mypy src/hft --ignore-missing-imports
```

`.github/workflows/ci.yml` runs all three on push/PR.

## Deploy / runbook

- **Streamlit Community Cloud** (UI): deploys `streamlit_app.py` directly,
  as before. Add secrets in the app's Settings → Secrets:
  `FINNHUB_API_KEY`, and optionally `LLM_API_KEY` to enable the Agent
  Console. `SUPABASE_URL`/`UPSTASH_REDIS_URL` are optional — omitted, the
  app runs on local SQLite + in-process cache (fine for a single Streamlit
  Cloud instance; the SQLite file resets on redeploy, which is acceptable
  for cached candles/alerts but not for anything that must survive
  restarts).
- **Why a separate worker is still needed for v2+**: Streamlit Community
  Cloud cannot hold a persistent WebSocket connection or run a background
  ingestion loop — this was already true before this build and still is.
  The existing `hft.main` ingestion service (Kraken WS → TimescaleDB +
  Redis pub/sub) needs to run somewhere that supports long-lived
  processes — Render or Railway, per the original design doc
  (`docs/superpowers/specs/2026-08-22-hft-platform-plan.md`). Nothing in
  this agent-layer build changes that; the Agent Console works fine
  against Streamlit Cloud's polling model since it's on-demand REST calls,
  same as the existing quote panels.
- **Provisioning Supabase / Upstash for real** (when ready to move past the
  SQLite/local-Redis fallback): create the project, set `SUPABASE_URL` +
  `SUPABASE_KEY` / `UPSTASH_REDIS_URL` in Streamlit Cloud secrets. No code
  change needed — `TimeseriesStore`/`QuoteCache` read those env vars
  directly; swapping `TimeseriesStore`'s SQLite backend for Postgres is the
  one place that needs an actual code change (the interface is already
  designed for it — see the module docstring in `data_plane/timeseries.py`).
