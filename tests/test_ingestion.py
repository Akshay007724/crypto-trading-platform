import asyncio

import pytest

from hft.ingestion import IngestionCore, TradeBatcher
from hft.types import Trade


def _trade(price: float, ts: int) -> Trade:
    return Trade(exchange="kraken", symbol="BTC/USD", price=price, size=0.1, side="buy", ts=ts)


def test_batcher_accumulates_trades_and_flush_clears_it():
    # Arrange
    batcher = TradeBatcher()
    batcher.add(_trade(100, 1))
    batcher.add(_trade(101, 2))

    # Act
    flushed = batcher.flush()

    # Assert
    assert flushed == [_trade(100, 1), _trade(101, 2)]
    assert batcher.flush() == []  # buffer cleared


@pytest.mark.asyncio
async def test_ingestion_core_publishes_every_trade_and_batches_db_writes():
    # Arrange: fake queue with two trades, fake db writer and publisher
    queue: asyncio.Queue = asyncio.Queue()
    await queue.put(_trade(100, 1))
    await queue.put(_trade(101, 2))

    published = []
    written_batches = []

    async def fake_publish(trade):
        published.append(trade)

    async def fake_write_batch(trades):
        written_batches.append(list(trades))

    core = IngestionCore(queue, publish=fake_publish, write_batch=fake_write_batch, flush_interval=0.01)

    # Act: run the core briefly, long enough for one flush cycle
    task = asyncio.create_task(core.run())
    await asyncio.sleep(0.05)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    # Assert
    assert published == [_trade(100, 1), _trade(101, 2)]
    assert written_batches and written_batches[0] == [_trade(100, 1), _trade(101, 2)]
