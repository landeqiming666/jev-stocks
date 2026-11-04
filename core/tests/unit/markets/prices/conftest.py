import json
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest

from sentinel.http.client import HttpClient
from sentinel.storage.db import Database

ROOT = Path(__file__).resolve().parents[5]
FIXTURES = ROOT / "core/tests/fixtures/prices"
NOW = datetime(2026, 11, 3, 12, tzinfo=UTC)


def payload(name):
    return json.loads((FIXTURES / name).read_text())


def client(data):
    return HttpClient(transport=httpx.MockTransport(lambda _: httpx.Response(200, json=data)))


class FakeSource:
    def __init__(self, name, rows=None, error=None):
        self.name, self.rows, self.error = name, rows or [], error
        self.calls = []

    def fetch_daily(self, symbol, start, end):
        self.calls.append((symbol, start, end))
        if self.error:
            raise self.error
        return self.rows


@pytest.fixture
def db(tmp_path):
    database = Database(tmp_path / "prices.duckdb")
    database.open()
    database.migrate()
    with database.write() as tx:
        for symbol in ("ZZAR", "ZZFD", "ZZCL"):
            tx.execute(
                "INSERT INTO instrument VALUES (?, 'us', ?, 'NASDAQ', ?, NULL, "
                "'USD', NULL, TRUE, 'demo', ?)",
                [f"us:{symbol}", symbol, symbol, NOW],
            )
    yield database
    database.close()


def prices(db):
    with db.read() as reader:
        reader.execute(
            "SELECT instrument_id, trade_date, close, source FROM price_daily ORDER BY 1,2"
        )
        return reader.fetchall()


def seed(db, day):
    with db.write() as tx:
        tx.execute(
            "INSERT INTO price_daily (instrument_id, trade_date, close, source, fetched_at) "
            "VALUES ('us:ZZAR', ?, 10, 'demo', ?)",
            [day, NOW],
        )
