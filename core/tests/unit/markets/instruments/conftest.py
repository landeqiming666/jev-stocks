import json
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

import pytest

from sentinel.markets.instruments import InstrumentRepository, TickerRow
from sentinel.storage import Database

FIXTURES = Path(__file__).resolve().parents[3] / "fixtures" / "instruments"
NOW = datetime(2026, 11, 3, tzinfo=UTC)


@pytest.fixture(autouse=True)
def isolated(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("SENTINEL_OFFLINE", "1")
    monkeypatch.setenv("SENTINEL_DATA_DIR", str(tmp_path))
    from sentinel.http import client

    monkeypatch.setattr(client, "_shared_sources", {})


@pytest.fixture
def db(tmp_path: Path) -> Iterator[Database]:
    database = Database(tmp_path / "test.duckdb")
    database.open()
    database.migrate()
    yield database
    database.close()


@pytest.fixture
def alias_path(tmp_path: Path) -> Path:
    target = tmp_path / "resources space 中文" / "aliases" / "us_zh.json"
    target.parent.mkdir(parents=True)
    target.write_bytes((FIXTURES / "us_zh.sample.json").read_bytes())
    return target


@pytest.fixture
def repo(db: Database, alias_path: Path) -> InstrumentRepository:
    return InstrumentRepository(db, resource_dir=alias_path.parent.parent)


@pytest.fixture
def rows() -> list[TickerRow]:
    payload = json.loads((FIXTURES / "company_tickers_exchange.sample.json").read_text())
    return [
        TickerRow(str(cik), name, ticker, exchange)
        for cik, name, ticker, exchange in payload["data"]
    ]
