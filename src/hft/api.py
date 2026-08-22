import dataclasses
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from hft.config import DATABASE_URL, REDIS_URL
from hft.storage.redis_bus import RedisTickBus
from hft.storage.timescale import TimescaleTradeStore

logger = logging.getLogger(__name__)
WEB_DIR = Path(__file__).resolve().parent.parent.parent / "web"


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.store = await TimescaleTradeStore.connect(DATABASE_URL)
    app.state.bus = RedisTickBus.connect(REDIS_URL)
    yield
    await app.state.store.close()
    await app.state.bus.close()


app = FastAPI(lifespan=lifespan)


@app.get("/api/trades/{exchange}/{symbol}")
async def get_recent_trades(exchange: str, symbol: str, limit: int = 200):
    trades = await app.state.store.recent_trades(exchange, symbol.replace("-", "/"), limit=limit)
    return [dataclasses.asdict(t) for t in trades]


@app.websocket("/ws/ticks/{exchange}/{symbol}")
async def stream_ticks(websocket: WebSocket, exchange: str, symbol: str):
    await websocket.accept()
    try:
        async for trade in app.state.bus.subscribe(exchange, symbol.replace("-", "/")):
            await websocket.send_json(dataclasses.asdict(trade))
    except WebSocketDisconnect:
        pass


if WEB_DIR.is_dir():
    app.mount("/assets", StaticFiles(directory=WEB_DIR), name="assets")

    @app.get("/")
    async def index():
        return FileResponse(WEB_DIR / "index.html")
