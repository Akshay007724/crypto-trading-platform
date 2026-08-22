import asyncio
import logging
from typing import Awaitable, Callable

from hft.types import Trade

logger = logging.getLogger(__name__)

DEFAULT_FLUSH_INTERVAL = 0.1  # 100ms, per the ingestion design spec


class TradeBatcher:
    """In-memory buffer flushed on a timer by IngestionCore."""

    def __init__(self):
        self._buffer: list[Trade] = []

    def add(self, trade: Trade) -> None:
        self._buffer.append(trade)

    def flush(self) -> list[Trade]:
        batch, self._buffer = self._buffer, []
        return batch


class IngestionCore:
    """Consumes normalized trades from a connector queue: publishes each
    immediately (best-effort, per spec — a missed publish is acceptable),
    and batches DB writes on a flush_interval timer. DB write failures
    are retried by the caller-supplied write_batch; a batch that still
    fails is dropped and logged rather than crashing the service.
    """

    def __init__(
        self,
        queue: asyncio.Queue[Trade],
        publish: Callable[[Trade], Awaitable[None]],
        write_batch: Callable[[list[Trade]], Awaitable[None]],
        flush_interval: float = DEFAULT_FLUSH_INTERVAL,
    ):
        self._queue = queue
        self._publish = publish
        self._write_batch = write_batch
        self._flush_interval = flush_interval
        self._batcher = TradeBatcher()

    async def run(self):
        await asyncio.gather(self._consume(), self._flush_loop())

    async def _consume(self):
        while True:
            trade = await self._queue.get()
            self._batcher.add(trade)
            try:
                await self._publish(trade)
            except Exception:
                logger.warning("redis publish failed for trade %s (best-effort, continuing)", trade, exc_info=True)

    async def _flush_loop(self):
        while True:
            await asyncio.sleep(self._flush_interval)
            batch = self._batcher.flush()
            if not batch:
                continue
            try:
                await self._write_batch(batch)
            except Exception:
                logger.error("db write failed for batch of %d trades, dropping", len(batch), exc_info=True)
