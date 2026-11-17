from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

import pytest

from sentinel.demo import DemoService
from sentinel.storage import Database

ROOT = Path(__file__).resolve().parents[4]
RESOURCES = ROOT / "resources" / "demo"
NOW = datetime(2026, 11, 3, 12, 0, tzinfo=UTC)


@pytest.fixture
def db(tmp_path: Path) -> Iterator[Database]:
    database = Database(tmp_path / "sentinel.duckdb")
    database.open()
    database.migrate()
    try:
        yield database
    finally:
        database.close()


@pytest.fixture
def service(db: Database) -> DemoService:
    return DemoService(db, RESOURCES, lambda: NOW)
