# High-Frequency Trading Platform — Plan

## Purpose

Evolve the paper-trading platform beyond passive market-data ingestion
into a real HFT system: strategy engine, low-latency execution, risk
controls, and (eventually) live order placement. Builds directly on
top of `2026-08-22-data-ingestion-design.md` — that service remains
the warm-path market-data foundation; this plan adds the hot path and
everything execution-related on top of it.

## Why the existing ingestion service is NOT sufficient for HFT as-is
/se
The ingestion spec's cadence is fine for paper trading / research, not
for HFT decision-making:

- Trades batched to TimescaleDB on a **100ms flush window** — too
  coarse for a strategy that needs to react tick-by-tick.
- Order book snapshotted to Postgres **every 5s** — a strategy reading
  book state from Postgres is looking at data up to 5s stale.
- Redis pub/sub tick stream is real-time and **is** usable as a signal
  source, but Redis pub/sub is fire-and-forget/best-effort (per the
  existing spec) — acceptable for a UI, not for something that must
  never miss a fill signal.

Conclusion: keep Redis ticks as the *signal* feed into the strategy
engine, but the execution decision loop must hold its own in-memory
order book state (fed directly from the exchange WS connectors, not
via a persistence layer) rather than depending on the DB or even
Redis for anything on the hot path.

## Candidate public APIs (from github.com/public-apis/public-apis)

Evaluated from the `Cryptocurrency` and `Finance` categories. Native
exchange WS/REST beats every aggregator on the hot path — an
aggregator (CoinAPI, CoinGecko, CryptoCompare) adds a hop of latency
and a second point of failure between you and the exchange's matching
engine, so those are reference/backup only, never execution-path.

| Function | Choice | Why |
|---|---|---|
| Primary market data + execution | **Binance** (`apiKey`, WS+REST, spot+futures) | Deepest liquidity, lowest latency public WS, already the primary connector in the ingestion spec — reuse it. |
| Secondary market data + execution | **Coinbase**, **Kraken** (`apiKey`) | Already integrated in ingestion spec; keep as the multi-venue set for cross-exchange arb signals and redundancy. |
| Derivatives / algo-trading venue | **Bybit** (`apiKey`) | Purpose-built algo-trading REST/WS, useful if the strategy set expands to perps/futures. |
| Decentralized reference venue | **dYdX** (`apiKey`) | On-chain settlement — note explicitly: chain finality latency makes it unsuitable for the sub-ms hot path; only useful as a slower reference/arb leg, never as the primary execution venue. |
| Cross-exchange reference pricing | **CoinAPI** (`apiKey`) | Aggregates many exchanges under one API — good for a background arb-signal/sanity-check feed, not for order placement. |
| On-chain fee-aware strategies | **Mempool** (No auth) | Bitcoin mempool/fee data, useful if any strategy needs on-chain fee-timing awareness. |
| Fundamentals / backup pricing | **CoinGecko**, **CryptoCompare**, **Messari** (No auth) | Free, no key needed, but slow/aggregated — reference and backtesting only. |
| TA indicators | **Technical Analysis API** (`apiKey`) | Optional signal input; not required for v1. |
| Cross-asset benchmarking (optional) | **Alpaca** (`apiKey`) | Real US equities trading API with a well-documented execution model — useful as a design reference for the order-execution module even if equities aren't in scope. |

Do not use CoinGecko/CryptoCompare/Messari/CoinAPI on the execution
hot path — no-auth/aggregator APIs are rate-limited and latency-
unpredictable by design.

## Architecture

```
                         ┌── existing warm path (ingestion spec) ──┐
 Binance WS ──┐          │                                          │
 Coinbase WS ─┼─> [Connectors] --normalize--> [Ingestion Core] ──┬──> Redis pub/sub (ticks) ──> UI / non-latency-critical consumers
 Kraken WS ───┘          │                                       └──> TimescaleDB (history)   │
                         └──────────────────────────────────────────────────────────────────────┘
                                                                                                  │ (signal only, best-effort)
                                                                                                  v
 Binance WS (2nd conn) ─┐                                                              ┌──────────────────┐
 Coinbase WS (2nd conn)─┼──> [Hot-Path Book Cache] --in-memory, no DB, no Redis──────> │  Strategy Engine  │
 Kraken WS (2nd conn) ──┘    (per-exchange order book, sub-ms updates)                 └─────────┬────────┘
                                                                                                    │ signal
                                                                                          ┌─────────v────────┐
                                                                                          │  Risk Manager    │  <- kill switch, position/loss limits
                                                                                          └─────────┬────────┘
                                                                                                    │ approved order
                                                                                          ┌─────────v────────┐
                                                                                          │ Execution Engine │ --REST/WS order API--> Exchange
                                                                                          └──────────────────┘
```

Hot path (Hot-Path Book Cache → Strategy Engine → Risk Manager →
Execution Engine) runs as its own process(es), with a dedicated WS
connection per exchange separate from the ingestion service's
connections — it must never block on, or depend on the availability
of, TimescaleDB or Redis. The warm path (existing ingestion service)
continues to serve history, backtesting, and UI unchanged.

## Phased breakdown

**v1 — Backtesting + paper strategy loop**
- Historical replay engine reading TimescaleDB `trades`/`candles` (warm path, already exists).
- Strategy interface (given book/trade state → emit buy/sell/hold).
- Paper order simulator (fills against historical/replayed book, no real exchange contact).
- No real money, no live order API calls yet.

**v2 — Live signal, paper execution**
- Hot-Path Book Cache: dedicated low-latency WS connectors (Binance first) maintaining in-memory order book, bypassing Redis/DB entirely.
- Strategy Engine runs against live book state, emits paper orders (simulated fills, logged, not sent to exchange).
- Risk Manager stub: position/exposure tracking even in paper mode, to validate limits logic before real money is involved.

**v3 — Live execution (real capital)**
- Execution Engine: real order placement via exchange REST/WS trading API (start with Binance spot).
- Risk Manager enforced for real: kill switch, max position size, max daily loss, per-symbol rate limits against exchange API limits.
- Idempotent order placement — client order IDs, dedupe on reconnect so a WS drop never causes a duplicate order.

**v4 — Multi-venue / cross-exchange**
- Add Coinbase, Kraken, Bybit execution.
- Cross-exchange arb signal using CoinAPI as a reference feed (signal only, execution still goes through native per-exchange APIs).

## Error Handling

- Hot-path WS disconnect: reconnect with backoff, but until resubscribed and book resynced, Strategy Engine must treat that exchange's book as **stale and refuse to trade on it** (fail closed, not fail open).
- Order placement failure/timeout: never blind-retry a possibly-already-placed order — always use a client order ID and query order status before retrying.
- Risk Manager failure or unreachable: Execution Engine refuses to place orders (fail closed) — no order path may bypass risk checks even under failure.
- Any exception in the Strategy Engine trips the kill switch for that strategy instance, does not crash the process silently.

## Testing

- Unit: strategy logic against fixture book/trade sequences with known expected signals.
- Unit: risk manager limit enforcement (position size, daily loss, rate limit) with boundary-condition tests.
- Integration: full v1 backtest loop against recorded historical data with known expected P&L, as a regression check.
- Integration: v3 execution engine against exchange **testnet only** (Binance testnet) — never test order placement against production venues.
- No live-capital paths are exercised in CI, ever.

## Deployment

- v1/v2 add to the existing Docker Compose stack as additional services (`strategy-engine`, `hot-path-cache`) alongside `ingestion`, `timescaledb`, `redis`.
- v3 execution engine deployed as its own isolated service/container with tightly scoped exchange API key permissions (trade-only, no withdrawal permission, ever).
- Colocation/hosting latency: for v1–v2 a standard VPS is fine; if v3 sub-100ms execution latency becomes a real requirement, revisit hosting region relative to exchange matching-engine location as a later infra task — not a v1–v3 blocker.

## Config

- `config/strategies.yaml` — enabled strategies, per-strategy risk limits (max position, max daily loss).
- `config/execution.yaml` — per-exchange execution enablement flag (defaults all to paper/off), API key env var names (never in the file itself), rate limit budgets.
- Real exchange API keys: environment variables only, trade-scoped permissions, no withdrawal rights — this is a hard requirement before any v3 work starts.
