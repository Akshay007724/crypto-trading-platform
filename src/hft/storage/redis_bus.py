import dataclasses
import json
from typing import AsyncIterator

import redis.asyncio as redis

from hft.types import Trade


def _channel(exchange: str, symbol: str) -> str:
    return f"ticks:{exchange}:{symbol}"


class RedisTickBus:
    def __init__(self, client: "redis.Redis"):
        self._client = client

    @classmethod
    def connect(cls, redis_url: str) -> "RedisTickBus":
        return cls(redis.from_url(redis_url))

    async def publish(self, trade: Trade) -> None:
        channel = _channel(trade.exchange, trade.symbol)
        await self._client.publish(channel, json.dumps(dataclasses.asdict(trade)))

    async def subscribe(self, exchange: str, symbol: str) -> AsyncIterator[Trade]:
        pubsub = self._client.pubsub()
        await pubsub.subscribe(_channel(exchange, symbol))
        try:
            async for message in pubsub.listen():
                if message["type"] != "message":
                    continue
                yield Trade(**json.loads(message["data"]))
        finally:
            await pubsub.unsubscribe()

    async def close(self) -> None:
        await self._client.aclose()
