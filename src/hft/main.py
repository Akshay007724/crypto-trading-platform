import asyncio
import logging

from hft.config import DATABASE_URL, KRAKEN_SYMBOL, REDIS_URL
from hft.connectors.kraken import KrakenConnector
from hft.ingestion import IngestionCore
from hft.storage.redis_bus import RedisTickBus
from hft.storage.timescale import TimescaleTradeStore

logging.basicConfig(level=logging.INFO)


async def main():
    store = await TimescaleTradeStore.connect(DATABASE_URL)
    bus = RedisTickBus.connect(REDIS_URL)

    queue: asyncio.Queue = asyncio.Queue()
    connector = KrakenConnector(KRAKEN_SYMBOL, queue)
    core = IngestionCore(queue, publish=bus.publish, write_batch=store.write_batch)

    await asyncio.gather(connector.run(), core.run())


if __name__ == "__main__":
    asyncio.run(main())
