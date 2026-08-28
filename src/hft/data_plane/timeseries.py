"""Time-series persistence for candles / alerts / watchlists.

Production target is Supabase Postgres (`SUPABASE_URL` set). Per this
build's scope, nothing is provisioned live: when `SUPABASE_URL` is unset,
this falls back to a local SQLite file so `query_timeseries` and the
Alert/Portfolio agents have something real to read/write without any
account setup. Swap `TimeseriesStore.connect()` for a Postgres-backed
implementation when a Supabase project exists — the interface doesn't change.
"""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager

_SCHEMA = """
CREATE TABLE IF NOT EXISTS candles (
    symbol TEXT NOT NULL, ts REAL NOT NULL, open REAL, high REAL, low REAL, close REAL, volume REAL,
    PRIMARY KEY (symbol, ts)
);
CREATE TABLE IF NOT EXISTS alerts (
    id INTEGER PRIMARY KEY AUTOINCREMENT, symbol TEXT NOT NULL, kind TEXT NOT NULL,
    threshold REAL NOT NULL, fired_at REAL, value_at_fire REAL
);
CREATE TABLE IF NOT EXISTS watchlist (
    symbol TEXT PRIMARY KEY, added_at REAL NOT NULL
);
"""


class TimeseriesStore:
    def __init__(self, db_path: str):
        self._db_path = db_path
        with self._conn() as conn:
            conn.executescript(_SCHEMA)

    @contextmanager
    def _conn(self):
        conn = sqlite3.connect(self._db_path)
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def upsert_candle(self, symbol: str, ts: float, open_: float, high: float, low: float, close: float, volume: float) -> None:
        with self._conn() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO candles (symbol, ts, open, high, low, close, volume) VALUES (?,?,?,?,?,?,?)",
                (symbol, ts, open_, high, low, close, volume),
            )

    def get_candles(self, symbol: str, limit: int = 200) -> list[dict]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT symbol, ts, open, high, low, close, volume FROM candles WHERE symbol = ? ORDER BY ts DESC LIMIT ?",
                (symbol, limit),
            ).fetchall()
        cols = ["symbol", "ts", "open", "high", "low", "close", "volume"]
        return [dict(zip(cols, row)) for row in reversed(rows)]

    def add_watchlist_symbol(self, symbol: str, added_at: float) -> None:
        with self._conn() as conn:
            conn.execute("INSERT OR IGNORE INTO watchlist (symbol, added_at) VALUES (?, ?)", (symbol, added_at))

    def get_watchlist(self) -> list[str]:
        with self._conn() as conn:
            rows = conn.execute("SELECT symbol FROM watchlist ORDER BY added_at").fetchall()
        return [r[0] for r in rows]

    def record_alert(self, symbol: str, kind: str, threshold: float, fired_at: float, value_at_fire: float) -> int:
        with self._conn() as conn:
            cur = conn.execute(
                "INSERT INTO alerts (symbol, kind, threshold, fired_at, value_at_fire) VALUES (?,?,?,?,?)",
                (symbol, kind, threshold, fired_at, value_at_fire),
            )
            return cur.lastrowid

    def get_recent_alerts(self, limit: int = 50) -> list[dict]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT id, symbol, kind, threshold, fired_at, value_at_fire FROM alerts ORDER BY fired_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        cols = ["id", "symbol", "kind", "threshold", "fired_at", "value_at_fire"]
        return [dict(zip(cols, row)) for row in rows]
