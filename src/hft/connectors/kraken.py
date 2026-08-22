import asyncio
import json
import logging
from datetime import datetime

import websockets

from hft.types import Trade

logger = logging.getLogger(__name__)

WS_URL = "wss://ws.kraken.com/v2"
MAX_BACKOFF_SECONDS = 60


def parse_trade_message(raw: str) -> list[Trade]:
    """Normalize a Kraken WS v2 message into zero or more Trade objects.

    Only "trade" channel updates carry trades — heartbeats and
    subscribe/ack messages normalize to an empty list. Malformed input
    is logged and dropped, never raised past this boundary.
    """
    try:
        msg = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        logger.warning("dropping malformed message: %r", raw)
        return []

    if not isinstance(msg, dict) or msg.get("channel") != "trade":
        return []

    trades = []
    for entry in msg.get("data", []):
        try:
            ts = int(datetime.fromisoformat(entry["timestamp"].replace("Z", "+00:00")).timestamp())
            trades.append(
                Trade(
                    exchange="kraken",
                    symbol=entry["symbol"],
                    price=float(entry["price"]),
                    size=float(entry["qty"]),
                    side=entry["side"],
                    ts=ts,
                )
            )
        except (KeyError, ValueError, TypeError):
            logger.warning("dropping malformed trade entry: %r", entry)
    return trades


class KrakenConnector:
    """Subscribes to Kraken's public trade channel for one symbol and
    pushes normalized Trade objects onto an asyncio queue. No business
    logic beyond protocol translation — reconnects with exponential
    backoff and resubscribes on drop, per the ingestion design spec.
    """

    def __init__(self, symbol: str, queue: asyncio.Queue):
        self._symbol = symbol
        self._queue = queue

    async def run(self):
        backoff = 1
        while True:
            try:
                async with websockets.connect(WS_URL, open_timeout=10) as ws:
                    await ws.send(
                        json.dumps({"method": "subscribe", "params": {"channel": "trade", "symbol": [self._symbol]}})
                    )
                    backoff = 1
                    async for raw in ws:
                        for trade in parse_trade_message(raw):
                            await self._queue.put(trade)
            except (websockets.exceptions.WebSocketException, OSError) as exc:
                logger.warning("kraken connector dropped (%s), reconnecting in %ss", exc, backoff)
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, MAX_BACKOFF_SECONDS)
