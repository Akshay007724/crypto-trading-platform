CREATE EXTENSION IF NOT EXISTS timescaledb;

CREATE TABLE IF NOT EXISTS trades (
    id BIGSERIAL,
    exchange TEXT NOT NULL,
    symbol TEXT NOT NULL,
    price DOUBLE PRECISION NOT NULL,
    size DOUBLE PRECISION NOT NULL,
    side TEXT NOT NULL,
    ts TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (exchange, symbol, ts, id)
);

SELECT create_hypertable('trades', 'ts', if_not_exists => TRUE);

CREATE INDEX IF NOT EXISTS trades_symbol_ts_idx ON trades (exchange, symbol, ts DESC);
