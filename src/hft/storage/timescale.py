import asyncpg

from hft.types import Trade


class TimescaleTradeStore:
    def __init__(self, pool: asyncpg.Pool):
        self._pool = pool

    @classmethod
    async def connect(cls, database_url: str) -> "TimescaleTradeStore":
        pool = await asyncpg.create_pool(database_url)
        return cls(pool)

    async def write_batch(self, trades: list[Trade]) -> None:
        if not trades:
            return
        await self._pool.executemany(
            """
            INSERT INTO trades (exchange, symbol, price, size, side, ts)
            VALUES ($1, $2, $3, $4, $5, to_timestamp($6))
            """,
            [(t.exchange, t.symbol, t.price, t.size, t.side, t.ts) for t in trades],
        )

    async def recent_trades(self, exchange: str, symbol: str, limit: int = 200) -> list[Trade]:
        rows = await self._pool.fetch(
            """
            SELECT exchange, symbol, price, size, side, extract(epoch from ts)::bigint AS ts
            FROM trades
            WHERE exchange = $1 AND symbol = $2
            ORDER BY ts DESC
            LIMIT $3
            """,
            exchange,
            symbol,
            limit,
        )
        return [Trade(**dict(row)) for row in reversed(rows)]

    async def close(self) -> None:
        await self._pool.close()
