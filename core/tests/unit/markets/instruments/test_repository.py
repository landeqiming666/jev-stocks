import json
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from pathlib import Path
from time import perf_counter

import duckdb
import pytest

from sentinel.errors import InternalError, SourceError, UserError
from sentinel.markets.instruments import InstrumentRepository, TickerRow
from sentinel.storage import Database
from sentinel.storage.db import WriteTx

from .conftest import NOW


def snapshot(db: Database) -> list[object]:
    with db.read() as reader:
        reader.execute("SELECT * FROM instrument ORDER BY instrument_id")
        instruments = reader.fetchall()
        reader.execute("SELECT * FROM instrument_alias ORDER BY instrument_id, alias")
        aliases = reader.fetchall()
        reader.execute("SELECT * FROM setting ORDER BY key")
        return [instruments, aliases, reader.fetchall()]


def test_import_keeps_smallest_cik_on_duplicate(
    repo: InstrumentRepository, rows: list[TickerRow]
) -> None:
    stats = repo.replace_from_sec(rows, fetched_at=NOW)
    assert (
        stats.total,
        stats.kept,
        stats.skipped_exchange,
        stats.skipped_symbol,
        stats.duplicates,
        stats.deactivated,
    ) == (25, 13, 2, 9, 1, 0)
    assert (
        stats.total == stats.kept + stats.skipped_exchange + stats.skipped_symbol + stats.duplicates
    )
    instrument = repo.get("us:BRK.B")
    assert instrument and instrument.cik == "0000000001" and instrument.symbol == "BRK.B"
    assert repo.get("us:AAPL").exchange == "NASDAQ"
    assert repo.get("us:OTCX") is None
    assert repo.get("us:MAXCIK").cik == "9999999999"
    assert repo.last_refresh_at() == NOW
    with repo._db.read() as reader:
        reader.execute("SELECT value_json FROM setting WHERE key = ?", ["lastTickerRefreshAt"])
        assert json.loads(reader.fetchone()[0]) == "2026-11-03T00:00:00Z"


@pytest.mark.parametrize(
    "cik",
    [
        True,
        False,
        0,
        -1,
        10000000000,
        1.0,
        float("nan"),
        float("inf"),
        "0",
        "-1",
        "1.0",
        "1e4",
        "+1",
        "",
        "١٢٣",
        " 1",
        "1 ",
        "00000000001",
    ],
)
def test_invalid_cik_counted(repo: InstrumentRepository, cik: object) -> None:
    stats = repo.replace_from_sec([TickerRow(cik, "X", "X", "NYSE")], fetched_at=NOW)
    assert stats.skipped_symbol == 1 and stats.kept == 0


@pytest.mark.parametrize(
    "cik,expected", [(1, "0000000001"), ("0000000001", "0000000001"), (9999999999, "9999999999")]
)
def test_valid_cik(repo: InstrumentRepository, cik: object, expected: str) -> None:
    repo.replace_from_sec([TickerRow(cik, "X", "X", "NYSE")], fetched_at=NOW)
    assert repo.get("us:X").cik == expected


def test_import_deactivates_and_rolls_back(repo: InstrumentRepository, db: Database) -> None:
    rows = [TickerRow("1", "Apple", "AAPL", "Nasdaq"), TickerRow("2", "Other", "OLD", "NYSE")]
    repo.replace_from_sec(rows, fetched_at=NOW)
    with db.write() as tx:
        tx.execute("CREATE TABLE holding_fixture (instrument_id VARCHAR)")
        tx.execute("INSERT INTO holding_fixture VALUES (?)", ["us:OLD"])
    stats = repo.replace_from_sec(rows[:1], fetched_at=NOW + timedelta(days=1))
    assert stats.deactivated == 1 and repo.get("us:OLD").is_active is False
    assert repo.search("old") == []
    assert repo.replace_from_sec(rows[:1], fetched_at=NOW + timedelta(days=2)).deactivated == 0
    with db.read() as reader:
        reader.execute("SELECT instrument_id FROM holding_fixture")
        assert reader.fetchone() == ("us:OLD",)
    before = snapshot(db)
    # 第二行名字 NULL 触发真实约束错误，第一行更新及别名删除也必须回滚。
    with pytest.raises(InternalError):
        repo.replace_from_sec(
            [TickerRow("1", "Changed", "AAPL", "Nasdaq"), TickerRow("3", None, "FAIL", "NYSE")],
            fetched_at=NOW + timedelta(days=3),
        )
    assert snapshot(db) == before
    assert repo.last_refresh_at() == NOW + timedelta(days=2)


def test_repeated_import_alias_priority_and_reactivation(
    repo: InstrumentRepository, db: Database, alias_path: Path
) -> None:
    alias_path.write_text(
        json.dumps(
            [{"symbol": "AAPL", "name_zh": "AAPL", "aliases": ["aapl", "Apple", "apple!", "苹果"]}]
        )
    )
    rows = [TickerRow("1", "Apple", "AAPL", "Nasdaq")]
    repo.replace_from_sec(rows, fetched_at=NOW)
    repo.replace_from_sec(rows, fetched_at=NOW)
    with db.read() as reader:
        reader.execute("SELECT alias, kind FROM instrument_alias ORDER BY alias")
        assert reader.fetchall() == [("aapl", "symbol"), ("apple", "name_en"), ("苹果", "alias")]
    assert repo.replace_from_sec([], fetched_at=NOW).deactivated == 1
    assert repo.get("us:AAPL").is_active is False
    assert repo.last_refresh_at() == NOW
    repo.replace_from_sec(rows, fetched_at=NOW)
    assert repo.get("us:AAPL").is_active is True


@pytest.mark.parametrize(
    "payload",
    [
        None,
        {},
        [None],
        [{"symbol": "AAPL", "name_zh": "苹果"}],
        [{"symbol": "AAPL", "name_zh": "苹果", "aliases": [], "extra": 1}],
        [{"symbol": ".X", "name_zh": "X", "aliases": []}],
        [{"symbol": "X", "name_zh": "", "aliases": []}],
        [{"symbol": "X", "name_zh": "X", "aliases": "x"}],
        [{"symbol": "X", "name_zh": "X", "aliases": [1]}],
        [{"symbol": "X", "name_zh": "X", "aliases": ["!_%"]}],
        [
            {"symbol": "brk-b", "name_zh": "X", "aliases": []},
            {"symbol": "BRK.B", "name_zh": "X", "aliases": []},
        ],
    ],
)
def test_bad_alias_shape_is_internal(db: Database, alias_path: Path, payload: object) -> None:
    alias_path.write_text(json.dumps(payload))
    with pytest.raises(InternalError):
        InstrumentRepository(db, alias_path=alias_path)


@pytest.mark.parametrize("contents", [b"{", b"\xff", b"[NaN]"])
def test_bad_json_and_missing(db: Database, alias_path: Path, contents: bytes) -> None:
    alias_path.write_bytes(contents)
    with pytest.raises(InternalError):
        InstrumentRepository(db, alias_path=alias_path)
    alias_path.unlink()
    with pytest.raises(InternalError):
        InstrumentRepository(db, alias_path=alias_path)


def test_resources_reload_failure_preserves_everything(
    repo: InstrumentRepository, db: Database, alias_path: Path
) -> None:
    rows = [TickerRow("1", "Apple", "AAPL", "Nasdaq")]
    repo.replace_from_sec(rows, fetched_at=NOW)
    before = snapshot(db)
    alias_path.write_text("broken")
    with pytest.raises(InternalError):
        repo.replace_from_sec(rows, fetched_at=NOW + timedelta(days=9))
    assert snapshot(db) == before


def test_default_resource_path_and_ddl(
    db: Database, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.chdir(tmp_path)
    repo = InstrumentRepository(db)
    repo.replace_from_sec([TickerRow("320193", "Apple Inc.", "AAPL", "Nasdaq")], fetched_at=NOW)
    assert repo.get("us:AAPL").name_zh == "苹果"
    root = Path(__file__).resolve().parents[5]
    doc = (root / "docs/04-数据模型.md").read_text()
    ddl = doc.split("### 3.2 ", 1)[1].split("```sql\n", 1)[1].split("```", 1)[0]
    assert (root / "core/sentinel/storage/migrations/002_instrument.sql").read_text() == ddl


def test_repository_invalid_search_never_reads(
    repo: InstrumentRepository, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fail() -> None:
        pytest.fail("invalid search touched database")

    monkeypatch.setattr(repo._db, "read", fail)
    for query, limit in [("", 20), ("!_%", 20), ("a" * 65, 20), ("a", True), ("a", 51)]:
        with pytest.raises(UserError):
            repo.search(query, limit=limit)


def test_thread_safe_access(repo: InstrumentRepository) -> None:
    rows = [TickerRow("1", "Apple", "AAPL", "Nasdaq")]

    def work(index: int) -> str:
        repo.replace_from_sec(rows, fetched_at=NOW)
        assert repo.search("aapl")[0].score == 120
        return repo.get("us:AAPL").symbol

    with ThreadPoolExecutor(max_workers=4) as executor:
        assert list(executor.map(work, range(12))) == ["AAPL"] * 12


def test_search_budget_10000(repo: InstrumentRepository, db: Database) -> None:
    with db.write() as tx:
        tx.execute(
            "INSERT INTO instrument SELECT 'us:X' || lpad(i::VARCHAR,5,'0'), 'us', "
            "'X' || lpad(i::VARCHAR,5,'0'), 'NYSE', 'Example ' || i, NULL, 'USD', "
            "'0000000001', TRUE, 'sec_company_tickers', ? FROM range(10000) t(i)",
            [NOW],
        )
        tx.execute(
            "INSERT INTO instrument_alias "
            "SELECT instrument_id, lower(symbol), 'symbol' FROM instrument"
        )
        tx.execute(
            "INSERT INTO instrument_alias "
            "SELECT instrument_id, 'example' || symbol, 'name_en' FROM instrument"
        )
    started = perf_counter()
    hits = repo.search("x", limit=50)
    elapsed = perf_counter() - started
    assert len(hits) == 50 and hits[0].instrument.symbol == "X00000"
    assert elapsed < 0.3
    print(f"search 10000 instruments / 20000 aliases: {elapsed * 1000:.2f} ms")
    assert len(repo.search("x")) == 20
    assert len(repo.search("x", limit=50)) == 50
    assert repo.search("z" * 64) == []


@pytest.mark.parametrize("stage", ["alias", "watermark"])
def test_failure_after_writes_rolls_back_all(
    repo: InstrumentRepository, db: Database, monkeypatch: pytest.MonkeyPatch, stage: str
) -> None:
    rows = [TickerRow("1", "Apple", "AAPL", "Nasdaq")]
    repo.replace_from_sec(rows, fetched_at=NOW)
    before = snapshot(db)
    if stage == "alias":
        original_many = WriteTx.executemany

        def fail_alias(tx, sql, parameters):
            original_many(tx, sql, parameters)
            if sql.startswith("INSERT INTO instrument_alias"):
                # 别名写完后再写同键，让真实 DuckDB PK 约束触发回滚。
                original_many(tx, sql, parameters[:1])

        monkeypatch.setattr(WriteTx, "executemany", fail_alias)
    else:
        original_execute = WriteTx.execute

        def fail_watermark(tx, sql, parameters=None):
            result = original_execute(tx, sql, parameters)
            if sql.startswith("INSERT INTO setting"):
                raise duckdb.IOException("injected failure after watermark write")
            return result

        monkeypatch.setattr(WriteTx, "execute", fail_watermark)
    with pytest.raises(InternalError):
        repo.replace_from_sec(
            [TickerRow("1", "Changed Apple", "AAPL", "NYSE")],
            fetched_at=NOW + timedelta(days=8),
        )
    assert snapshot(db) == before


@pytest.mark.parametrize("value_json", ["{", "true", '"2026-11-03T00:00:00"', '"bad"'])
def test_bad_watermark_is_internal(
    repo: InstrumentRepository, db: Database, value_json: str
) -> None:
    with db.write() as tx:
        tx.execute("INSERT INTO setting VALUES (?, ?, ?)", ["lastTickerRefreshAt", value_json, NOW])
    with pytest.raises(InternalError):
        repo.last_refresh_at()


def test_null_watermark_is_unset(repo: InstrumentRepository, db: Database) -> None:
    with db.write() as tx:
        tx.execute("INSERT INTO setting VALUES (?, ?, ?)", ["lastTickerRefreshAt", "null", NOW])
    assert repo.last_refresh_at() is None


def test_other_markets_and_get_bindings_preserved(repo: InstrumentRepository, db: Database) -> None:
    with db.write() as tx:
        tx.execute(
            "INSERT INTO instrument VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            ["hk:00700", "hk", "00700", "HKEX", "Fixture", None, "HKD", None, True, "demo", NOW],
        )
        tx.execute(
            "INSERT INTO instrument_alias VALUES (?, ?, ?)", ["hk:00700", "fixture", "name_en"]
        )
    repo.replace_from_sec([], fetched_at=NOW)
    assert repo.get("hk:00700").is_active is True
    assert repo.get("us:AAPL' OR 1=1 --") is None


def test_alias_name_zh_wins_name_en(
    repo: InstrumentRepository, db: Database, alias_path: Path
) -> None:
    alias_path.write_text(json.dumps([{"symbol": "X", "name_zh": "Apple", "aliases": ["APPLE!"]}]))
    repo.replace_from_sec([TickerRow("1", "Apple", "X", "NYSE")], fetched_at=NOW)
    with db.read() as reader:
        reader.execute("SELECT kind FROM instrument_alias WHERE alias = ?", ["apple"])
        assert reader.fetchone() == ("name_zh",)


@pytest.mark.parametrize("old", [False, True])
@pytest.mark.parametrize("rows", [[], [TickerRow("bad", "Invalid CIK", "X", "NYSE")]])
def test_require_nonempty_rejects_before_transaction(
    repo: InstrumentRepository,
    db: Database,
    monkeypatch: pytest.MonkeyPatch,
    old: bool,
    rows: list[TickerRow],
) -> None:
    if old:
        repo.replace_from_sec([TickerRow("1", "Apple", "AAPL", "Nasdaq")], fetched_at=NOW)
    before = snapshot(db)

    def fail_write():
        pytest.fail("all-filtered protected import entered a transaction")

    monkeypatch.setattr(db, "write", fail_write)
    with pytest.raises(SourceError) as error:
        repo.replace_from_sec(rows, fetched_at=NOW + timedelta(days=8), require_nonempty=True)
    assert error.value.code == "SOURCE_UNAVAILABLE" and error.value.reason == "TICKER_SCHEMA"
    assert snapshot(db) == before


def test_explicit_all_filtered_import_keeps_default_semantics(
    repo: InstrumentRepository,
) -> None:
    repo.replace_from_sec([TickerRow("1", "Apple", "AAPL", "Nasdaq")], fetched_at=NOW)
    later = NOW + timedelta(days=8)
    stats = repo.replace_from_sec([TickerRow("bad", "Invalid CIK", "X", "NYSE")], fetched_at=later)
    assert stats.total == 1 and stats.skipped_symbol == 1 and stats.deactivated == 1
    assert repo.get("us:AAPL").is_active is False
    assert repo.last_refresh_at() == later


@pytest.mark.parametrize("flag", [None, 0, 1, "true"])
def test_require_nonempty_requires_bool(repo: InstrumentRepository, flag: object) -> None:
    with pytest.raises(UserError) as error:
        repo.replace_from_sec([], fetched_at=NOW, require_nonempty=flag)
    assert error.value.field == "require_nonempty"
