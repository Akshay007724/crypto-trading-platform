# Session Memory — crypto-trading-platform

Written 2026-08-27 to preserve context before clearing the session.

## What this project is

Crypto (+ stocks) trading platform, started from a design-spec-only repo.
Built up in this session: v1 backtest engine, a live Kraken data pipeline
(FastAPI + TimescaleDB + Redis), a plain-HTML dashboard, and a separate
Streamlit Community Cloud app covering crypto + stocks.

## Repo layout

- `src/hft/` — Python package (installed via `pyproject.toml`, `pythonpath = ["src"]` for pytest)
  - `types.py` — `Trade`, `Signal`, `Fill` dataclasses/enum
  - `strategy.py`, `strategies/moving_average.py` — `MovingAverageCrossover(fast, slow)` SMA strategy
  - `execution.py` — `PaperBroker`, zero-slippage paper fills
  - `data.py` — `CsvTradeSource` (fixture-based `TradeSource`)
  - `backtest.py` — `BacktestEngine` wiring source → strategy → broker
  - `connectors/kraken.py` — live Kraken WS v2 connector (`wss://ws.kraken.com/v2`), reconnect+backoff
  - `ingestion.py` — `IngestionCore`/`TradeBatcher`, 100ms DB flush, best-effort Redis publish
  - `storage/timescale.py`, `storage/redis_bus.py` — asyncpg + redis.asyncio wrappers
  - `marketdata/kraken_rest.py`, `marketdata/finnhub.py` — REST clients used by the Streamlit app
  - `config.py` — env-var config (`DATABASE_URL`, `REDIS_URL`, `KRAKEN_SYMBOL`)
  - `main.py` — ingestion service entrypoint (`python -m hft.main`)
  - `api.py` — FastAPI app (`hft.api:app`), REST `/api/trades/{exchange}/{symbol}` + WS `/ws/ticks/{exchange}/{symbol}`, serves `web/index.html`
- `web/index.html` — plain HTML/JS dashboard ("Signal Deck"), fetches from the FastAPI backend above
- `streamlit_app.py` — separate single-file Streamlit app (crypto via Kraken REST, stocks via Finnhub REST), deployed to Streamlit Community Cloud
- `db/schema.sql` — TimescaleDB `trades` hypertable, mounted into the `timescaledb` container's init dir
- `docker-compose.yml` — `timescaledb` + `redis` services
- `docs/superpowers/specs/` — design docs: `2026-08-22-data-ingestion-design.md` (original spec) and `2026-08-22-hft-platform-plan.md` (v1–v4 phased plan)
- `tests/` — 17 tests, all passing, TDD'd throughout (`pytest` from repo root)

## Key decisions / non-obvious facts

- **Binance.com is geo-blocked** from this dev machine (HTTP 451) — Kraken used instead for the live connector (Coinbase/Binance.US reachable too, not wired).
- **Kraken WS v2** trade schema confirmed live: `{"channel":"trade","type":"update","data":[{"symbol":"BTC/USD","side":"buy","price":...,"qty":...,"timestamp":"ISO8601"}]}`.
- **Kraken REST ticker** result keys are inconsistent: `XBTUSD`→`XXBTZUSD`, `ETHUSD`→`XETHZUSD`, but `SOLUSD`/`ADAUSD` map to themselves. Hardcoded in `CRYPTO_PAIRS` in `streamlit_app.py`.
- **Finnhub free `/quote` endpoint has no volume field** — Streamlit app shows "not available" for stocks rather than fabricating it. Crypto volume is real (Kraken ticker `v[1]`, 24h rolling, not per-trade).
- **Streamlit Community Cloud can't run background WS/Docker** — the Streamlit app polls REST on each rerun/button click; it does NOT share infrastructure with the FastAPI/Docker pipeline. Two independent live paths to the same idea.
- User's Finnhub key is in local `.streamlit/secrets.toml` (gitignored, confirmed via `git check-ignore`) — was also pasted in plain chat at one point, so it's technically exposed in conversation history (free tier, low stakes, user was told to consider rotating it).
- `ecc:planner` agent has no Write tool — twice returned "saved earlier" without ever outputting the content when asked to plan the HFT doc. Ended up writing `docs/superpowers/specs/2026-08-22-hft-platform-plan.md` directly instead.

## Live/deployed state as of last check

- **GitHub**: https://github.com/Akshay007724/crypto-trading-platform (public, `main` branch, latest commit `18ff2a2`)
- **Streamlit Cloud**: https://crypto-trading-platform-eg82chkchgfliwe357g9sh.streamlit.app/ — deployed, verified working (crypto tab confirmed live with real Kraken data + volume chart; stocks tab renders correctly, needs `FINNHUB_API_KEY` set in the app's Settings → Secrets)
- **Local processes** (still running on this machine as of last check — PIDs will be stale after a reboot):
  - `pid 64501` — `python -m hft.main` (ingestion service, writing to local TimescaleDB)
  - `pid 64974` — `uvicorn hft.api:app --port 8000` (local dashboard backend, http://localhost:8000/)
  - Docker: `timescaledb` + `redis` containers up via `docker compose up -d` (5+ days uptime)
- To restart everything cleanly: `docker compose up -d`, then `PYTHONPATH=src .venv/bin/python -m hft.main &` and `PYTHONPATH=src .venv/bin/python -m uvicorn hft.api:app --port 8000 &`.

## What's NOT built yet (per the phased plan doc)

- v2: dedicated hot-path in-memory book cache (current ingestion still goes through the 100ms-batch warm path)
- v3: real order execution, risk manager enforcement (the risk panel in both frontends is illustrative/static)
- Real order-book depth (both frontends currently fake the book around the live mid price)
- Coinbase/Binance connectors (code path not written, only Kraken)

## User preferences observed this session

- Wants things actually verified live (ran real WS probes, browser-tested both frontends via chrome-devtools MCP) rather than taking claims on faith — catch this pattern for future work here.
- Caveman mode + ponytail mode active — terse responses, lazy/minimal-diff implementations preferred throughout this session.

## Agentic layer added (second session, continued after `memory.md` was written)

Built the agentic market-intelligence layer requested on top of the base platform above.
Scoped down from the full spec via `AskUserQuestion`: "Scaffold + 1 real agent", DeepSeek as
LLM backend (not Anthropic/LangGraph), infra stubbed via env vars (no live Supabase/Upstash
provisioning). Full rationale and file-by-file breakdown is in `README.md` (new).

- New code lives under `src/hft/{data_plane,tools,agents,ui}/`, not the spec's literal
  top-level `data_plane/`/`agents/`/`tools/` dirs — reused the existing `src/hft` package
  convention (`pyproject.toml`'s `pythonpath = ["src"]`) instead.
- **NL Query Agent is the only fully-wired agent** (`src/hft/agents/nl_query_agent.py`) —
  real DeepSeek function-calling, cited answers from `MarketTools`. Research/Technical/
  AlertTriage/Screener/Portfolio are stubs in `src/hft/agents/stubs.py`: real system
  prompt + tool allowlist + Pydantic schema each, `run()` raises `NotImplementedError`
  with a TODO. Supervisor treats that as a clean, expected outcome.
- `hft.data_plane.timeseries.TimeseriesStore` falls back to local SQLite when
  `SUPABASE_URL` is unset — no Supabase account was ever created for this build.
  `hft.data_plane.cache.QuoteCache` falls back to an in-process dict if Redis is
  unreachable. Both interfaces are designed to swap in the real backend later without
  changing callers (see docstrings in those two files).
- Orchestrator is a small hand-rolled `Supervisor` class (`agents/supervisor.py`), not
  LangGraph — proportionate to one wired agent; explicitly called out as the seam to
  swap in LangGraph later.
- 24 new tests added (`test_ratelimit.py`, `test_tools.py`, `test_agent_schemas.py`,
  `test_supervisor.py`) — all mock the LLM client, no `DEEPSEEK_API_KEY` needed to run
  the suite. Full suite verified green: 41/41 passing, `ruff check` clean on all new
  files, `streamlit_app.py` import-smoke-tested successfully.
- `mypy` currently errors on an unrelated numpy-stub/Python-version mismatch in this
  venv (Python 3.14, numpy stubs expect 3.12+ `type` statement support) — pre-existing
  environment issue, not caused by this build's code; CI pins Python 3.11 so shouldn't
  hit it there. Not yet independently verified in CI.
- Switched LLM backend from DeepSeek-direct to **OpenRouter as default** (user request,
  same session): renamed `DEEPSEEK_API_KEY`/`DEEPSEEK_BASE_URL`/`DEEPSEEK_MODEL` →
  `LLM_API_KEY`/`LLM_BASE_URL`/`LLM_MODEL` (default `https://openrouter.ai/api/v1`,
  `deepseek/deepseek-chat`), renamed `DeepSeekClient` → `LLMClient` everywhere (no
  back-compat alias kept — internal-only rename, no external callers). Still
  OpenAI-compatible under the hood, so DeepSeek-direct still works by pointing
  `LLM_BASE_URL` back at `api.deepseek.com`.
- **Live-verified end-to-end** with a real OpenRouter key the user pasted in chat
  (free-tier balance) — real `LLMClient` → `NLQueryAgent` → `Supervisor` call, real
  Kraken quote, correct citation. `gpt-4o` 402'd on this account's balance (its default
  `max_tokens` of 16384 exceeds what the free credits cover) — `deepseek/deepseek-chat`
  (the app's default model) works fine with no `max_tokens` cap needed. Worth remembering
  if the user ever wants to switch `LLM_MODEL` to a pricier model: may need to also set a
  smaller max_tokens or add credits.
  **The pasted key was never written to any file** (not `.env`, not committed) — used
  only as an inline env var for one verification call, then discarded from this
  process. User was told to rotate it at openrouter.ai/keys since it's now in chat
  history, same pattern as the earlier Finnhub-key exposure noted above.
- Added `.github/workflows/ci.yml` (ruff+mypy+pytest) and `README.md` — neither existed
  before this session.
- GateGuard hook (fact-forcing gate) fires on every first Write/Edit per file this
  session — required restating "who calls this / does it duplicate something / user's
  verbatim instruction" before each new file. Batch-presenting facts once before several
  Write calls in the same tool-batch worked for that batch, but the next unrelated batch
  needed its own restatement. Expect this every session until GateGuard's session-level
  cache behavior is better understood.
