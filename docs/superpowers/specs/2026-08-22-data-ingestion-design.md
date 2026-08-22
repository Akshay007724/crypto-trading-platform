# Data Ingestion Service — Design Spec

## Purpose

Foundation layer of the crypto paper-trading platform. Connects to live
exchange market data, normalizes it into a common schema, persists
history, and broadcasts live ticks to downstream consumers (paper
trading engine, frontend). No order placement, no research/fundamentals
— pure market data plumbing.

## Scope (v1)

- Exchanges: Binance, Coinbase, Kraken (spot only)
- Pairs: top ~20 by volume per exchange, configurable via YAML
- Data types: trades (tick-level), order book top-N (depth 20), OHLCV
  candles (1m, 5m, 1h, 1d — aggregated server-side from trades)
- No auth/multi-tenant concerns (single user)

## Out of scope (later sub-projects)

- Paper trading engine (portfolio, order sim, strategies)
- Research/fundamentals ingestion (CoinGecko, Fear&Greed, etc.)
- Frontend

## Architecture

```
 Binance WS ──┐
 Coinbase WS ─┼──> [Exchange Connectors] --normalize--> [Ingestion Core] ──┬──> Redis (pub/sub: live ticks/book)
 Kraken WS ───┘                                                            └──> TimescaleDB (trades, candles)
```

**Exchange Connectors** — one process/module per exchange, each a thin
adapter using the exchange's native WS client (`python-binance`,
`coinbase-advanced-py`, `krakenex` + `pykrakenapi` or raw `websockets`
for Kraken's public WS). No `ccxt.pro` (paid license) — REST-only
`ccxt` may still be used for one-time symbol/precision metadata.

Each connector:
- Subscribes to trade + order-book-diff channels for configured pairs
- Emits a normalized `NormalizedTrade` / `NormalizedBookUpdate` (internal dataclass) onto an asyncio queue
- Reconnects with exponential backoff on WS drop; resubscribes on reconnect
- No business logic — just protocol translation

**Ingestion Core** — single asyncio process that:
- Consumes from all connector queues
- Writes trades to TimescaleDB hypertable (`trades`), batched (100ms flush window)
- Maintains in-memory order book per (exchange, pair), applies diffs, snapshots to `orderbook_snapshots` table every 5s
- Aggregates trades into OHLCV candles per interval, upserts into `candles` hypertable
- Publishes every normalized event immediately to Redis pub/sub channel `ticks:{exchange}:{pair}` for live consumers

**Storage:**
- Postgres + TimescaleDB extension. Hypertables: `trades`, `candles`, `orderbook_snapshots`. Retention policy: raw trades 30 days, candles indefinite.
- Redis: pub/sub only for this service (no persistence needs here beyond Postgres).

## Data Schema (core tables)

```sql
trades(id, exchange, symbol, price, size, side, ts, PRIMARY KEY(exchange, symbol, ts, id))
candles(exchange, symbol, interval, open, high, low, close, volume, ts, PRIMARY KEY(exchange, symbol, interval, ts))
orderbook_snapshots(exchange, symbol, bids JSONB, asks JSONB, ts)
```

## Error Handling

- Connector WS disconnect → log, backoff (1s, 2s, 4s... capped 60s), reconnect, resubscribe. No crash of whole service.
- Malformed message from exchange → log + drop, counter metric, never raises past connector boundary.
- DB write failure → retry 3x with backoff, then drop batch + log error (data gap acceptable over service crash for v1).
- Redis publish is best-effort/fire-and-forget (data loss on a missed live tick is acceptable — Postgres is source of truth for history).

## Testing

- Unit: normalization logic per connector (given raw exchange JSON fixture → expect `NormalizedTrade`)
- Unit: candle aggregation logic (given trade stream → expect correct OHLCV)
- Integration: connector against exchange testnet/sandbox WS where available (Binance testnet); otherwise record/replay fixture WS sessions
- No live-money paths exist in this service, so no financial-risk testing needed here

## Deployment

- Single Docker Compose stack: `ingestion` service (Python), `timescaledb`, `redis`
- Runs on the target cloud VPS alongside future services (paper-trading engine, frontend) as additional compose services in later sub-projects

## Config

`config/exchanges.yaml` — per-exchange enabled pairs, intervals list. No secrets needed (public market data only, no API keys required for public WS feeds).
