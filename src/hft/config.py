import os

DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql://hft:hft@localhost:5432/hft")
REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379")
KRAKEN_SYMBOL = os.environ.get("KRAKEN_SYMBOL", "BTC/USD")
