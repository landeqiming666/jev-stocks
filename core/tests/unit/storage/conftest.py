from collections.abc import Iterator
from pathlib import Path

import pytest

from sentinel.storage import Database

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures" / "storage"


@pytest.fixture(autouse=True)
def isolated_storage(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SENTINEL_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("SENTINEL_CLOCK", "2026-11-02T00:35:00Z")
    monkeypatch.setenv("SENTINEL_OFFLINE", "1")


@pytest.fixture
def db(tmp_path: Path) -> Iterator[Database]:
    database = Database(tmp_path / "sentinel.duckdb")
    database.open()
    yield database
    database.close()


@pytest.fixture
def migrations_dir(tmp_path: Path) -> Path:
    directory = tmp_path / "migrations"
    directory.mkdir()
    return directory


@pytest.fixture
def business_db(db: Database) -> Database:
    with db.write() as tx:
        tx.execute((FIXTURES / "business_schema.sql").read_text(encoding="utf-8"))
        tx.execute((FIXTURES / "seed_integrity.sql").read_text(encoding="utf-8"))
    return db
