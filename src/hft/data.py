import csv
from pathlib import Path
from typing import Iterator, Protocol

from hft.types import Trade


class TradeSource(Protocol):
    def trades(self) -> Iterator[Trade]: ...


class CsvTradeSource:
    """Fixture-based trade source for v1 backtesting.

    Same shape as the `trades` hypertable in the ingestion service's
    TimescaleDB schema, so a TimescaleDbTradeSource can later implement
    the same TradeSource protocol without changing callers.
    """

    def __init__(self, path: Path):
        self._path = path

    def trades(self) -> Iterator[Trade]:
        with open(self._path, newline="") as f:
            rows = list(csv.DictReader(f))
        rows.sort(key=lambda r: int(r["ts"]))
        for row in rows:
            yield Trade(
                exchange=row["exchange"],
                symbol=row["symbol"],
                price=float(row["price"]),
                size=float(row["size"]),
                side=row["side"],
                ts=int(row["ts"]),
            )
