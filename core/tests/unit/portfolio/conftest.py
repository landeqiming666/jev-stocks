from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

import pytest

from sentinel import clock
from sentinel.portfolio import PortfolioService
from sentinel.storage import Database

NOW = datetime(2026, 11, 2, 0, 35, tzinfo=UTC)
ROOT = Path(__file__).resolve().parents[4]


@pytest.fixture(autouse=True)
def isolated(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("SENTINEL_OFFLINE", "1")
    monkeypatch.setenv("SENTINEL_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("SENTINEL_CLOCK", clock.to_iso(NOW))


@pytest.fixture
def db(tmp_path: Path) -> Iterator[Database]:
    database = Database(tmp_path / "portfolio.duckdb")
    database.open()
    # 单元 fixture 故意补造缺失的下游表；新交付迁移不应改变这些前置假设。
    migrations = tmp_path / "portfolio-migrations"
    migrations.mkdir()
    for source in (ROOT / "core/sentinel/storage/migrations").glob("*.sql"):
        if int(source.name.split("_", 1)[0]) <= 3:
            (migrations / source.name).write_bytes(source.read_bytes())
    database.migrate(migrations)
    with database.write() as tx:
        tx.executemany(
            "INSERT INTO instrument VALUES (?, ?, ?, 'NASDAQ', ?, NULL, ?, NULL, ?, 'demo', ?)",
            [
                [f"us:{symbol}", "us", symbol, name, "USD", True, NOW]
                for symbol, name in (
                    ("ZZAR", "Zenith Arc Robotics Inc."),
                    ("ZZFD", "Zephyr Foods Corp."),
                    ("ZZCL", "Zhongzhi Cloud Ltd."),
                    ("ZZEN", "Zeta Energy Partners"),
                    ("ZZMD", "Zenmed Diagnostics Inc."),
                )
            ]
            + [["hk:ZZBK", "hk", "ZZBK", "Zinc Bay Bancorp", "HKD", True, NOW]],
        )
    try:
        yield database
    finally:
        database.close()


@pytest.fixture
def service(db: Database) -> PortfolioService:
    return PortfolioService(db)


def query(db: Database, sql: str, params: list | None = None) -> list[tuple]:
    with db.read() as reader:
        reader.execute(sql, params)
        return reader.fetchall()


def add_downstream(db: Database, sections: tuple[str, ...] = ("3.4", "3.5", "3.6", "3.7")) -> None:
    source = (ROOT / "docs" / "04-数据模型.md").read_text()
    with db.write() as tx:
        for section in sections:
            ddl = source.split(f"### {section} `", 1)[1].split("```sql\n", 1)[1].split("```", 1)[0]
            tx.execute(ddl)


def add_decision(
    db: Database,
    thesis_id: str,
    relation: str,
    key: str = "d1",
    version: int = 1,
    event_id: str = "us:0009990001-26-000001",
    seq: int = 0,
) -> None:
    with db.write() as tx:
        tx.execute(
            "INSERT INTO event_doc VALUES (?, 'us:ZZAR', 'us', '8-K', ?, ?, ?, "
            "'https://example.com/filing', NULL, 'full_text', ?, 'demo') "
            "ON CONFLICT DO NOTHING",
            [event_id, "Synthetic event " + event_id, NOW, NOW.date(), NOW],
        )
        tx.execute(
            "INSERT INTO event_passage VALUES (?, ?, 0, ?, 'Synthetic passage', 0, 17, ?)",
            [key, event_id, seq, key],
        )
        tx.execute(
            "INSERT INTO decision VALUES (?, ?, ?, ?, ?, 'us:ZZAR', ?, .8, .7, .6, NULL, .2, .7, "
            "'passage', NULL, NULL, 'jev_direct', 'jev-1.14.0', 'test.1', ?, "
            "10, FALSE, 1, 'full_text', ?)",
            [key, thesis_id, version, key, event_id, relation, key, NOW],
        )
