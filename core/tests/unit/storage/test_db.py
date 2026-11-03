from concurrent.futures import ThreadPoolExecutor
from contextlib import suppress
from datetime import UTC, datetime
from pathlib import Path
from threading import Event

import duckdb
import pytest

from sentinel.errors import InternalError
from sentinel.storage import Database, SqlExecutor, WriteTx


def test_open_creates_schema_version_table(db: Database) -> None:
    assert duckdb.__version__ == "1.4.3"
    assert db.schema_version == 0
    with db.read() as reader:
        assert reader.execute("SELECT * FROM schema_version").fetchall() == []
        assert reader.execute("SHOW TABLES").fetchall() == [("schema_version",)]
    db.open()


def test_write_rolls_back_on_exception(db: Database) -> None:
    db.migrate()
    with pytest.raises(ValueError, match="cancel"), db.write() as tx:
        tx.execute("INSERT INTO setting VALUES (?, ?, ?)", ["x", "1", datetime.now(UTC)])
        raise ValueError("cancel")
    with db.read() as reader:
        assert reader.execute("SELECT count(*) FROM setting").fetchone() == (0,)


def test_read_uses_independent_cursor(db: Database) -> None:
    with db.read() as first:
        first.execute("SELECT 1 UNION ALL SELECT 2 ORDER BY 1")
        with db.read() as second:
            assert first is not second
            assert second.execute("SELECT 3").fetchone() == (3,)
        assert first.fetchall() == [(1,), (2,)]
    with ThreadPoolExecutor(2) as pool:

        def query() -> object:
            with db.read() as reader:
                assert reader.execute("SELECT 4").fetchone() == (4,)
                return reader

        readers = list(pool.map(lambda _: query(), range(2)))
        assert readers[0] is not readers[1]
    with pytest.raises(RuntimeError):
        first.execute("SELECT 1")


@pytest.mark.parametrize("separate_handle", [False, True])
def test_read_lock_blocks_concurrent_write(db: Database, separate_handle: bool) -> None:
    other = Database(db.path) if separate_handle else db
    other.open()
    attempted, entered = Event(), Event()

    def writer() -> None:
        attempted.set()
        with other.write() as tx:
            entered.set()
            tx.execute("CREATE TABLE concurrent (id INTEGER)")

    try:
        with ThreadPoolExecutor(1) as pool:
            with db.read():
                task = pool.submit(writer)
                assert attempted.wait(2)
                assert not entered.wait(0.1)
            task.result(timeout=3)
            assert entered.is_set()
    finally:
        if separate_handle:
            other.close()


def test_parallel_query_waits_for_rollback(db: Database) -> None:
    with db.write() as tx:
        tx.execute("CREATE TABLE sample (id INTEGER)")
    attempted = Event()

    def reader() -> list[tuple[object, ...]]:
        attempted.set()
        with db.read() as cursor:
            return cursor.execute("SELECT * FROM sample").fetchall()

    with ThreadPoolExecutor(1) as pool:
        with pytest.raises(ValueError), db.write() as tx:
            tx.execute("INSERT INTO sample VALUES (1)")
            task = pool.submit(reader)
            assert attempted.wait(2)
            assert not task.done()
            raise ValueError()
        assert task.result(timeout=3) == []


def test_nested_transactions_and_read_to_write_are_rejected(db: Database) -> None:
    with db.read(), pytest.raises(RuntimeError), db.write():
        pass
    with db.write() as tx:
        tx.execute("CREATE TABLE kept (id INTEGER)")
        with pytest.raises(RuntimeError), db.write():
            pass
        tx.execute("INSERT INTO kept VALUES (1)")
    with db.read() as reader:
        assert reader.execute("SELECT * FROM kept").fetchall() == [(1,)]


@pytest.mark.parametrize("sql", ["BEGIN", "COMMIT", "ROLLBACK", "SELECT 1; COMMIT"])
def test_tx_sql_cannot_escape_context(db: Database, sql: str) -> None:
    with db.write() as tx, pytest.raises(RuntimeError):
        tx.execute(sql)


@pytest.mark.parametrize(
    "sql",
    [
        "INSERT INTO sample VALUES (1)",
        "SELECT 1; INSERT INTO sample VALUES (1)",
        "-- SELECT\nDELETE FROM sample",
        "EXPLAIN ANALYZE INSERT INTO sample VALUES (1)",
        "CREATE TEMP TABLE hidden (id INTEGER)",
        "BEGIN; INSERT INTO sample VALUES (1); COMMIT",
        "WITH v AS (SELECT 1) INSERT INTO sample SELECT * FROM v",
        "SELECT nextval('seq')",
    ],
)
def test_read_rejects_write_including_multi_statement(db: Database, sql: str) -> None:
    with db.write() as tx:
        tx.execute("CREATE TABLE sample (id INTEGER); CREATE SEQUENCE seq")
    with pytest.raises((InternalError, duckdb.Error)), db.read() as reader:
        reader.execute(sql)
    with db.read() as reader:
        assert reader.execute("SELECT * FROM sample").fetchall() == []


def test_read_executemany_and_fluent_execution_are_guarded(db: Database) -> None:
    db.migrate()
    with db.read() as reader:
        with pytest.raises(InternalError):
            reader.executemany(
                "INSERT INTO setting VALUES (?, ?, ?)", [["x", "1", datetime.now(UTC)]]
            )
        with pytest.raises(InternalError):
            reader.execute("SELECT 1").execute("DELETE FROM setting")


def test_read_only_mode(tmp_path: Path) -> None:
    path = tmp_path / "sentinel.duckdb"
    writable = Database(path)
    writable.open()
    writable.migrate()
    writable.close()
    before = path.read_bytes()
    readonly = Database(path, read_only=True)
    readonly.open()
    assert readonly.schema_version == 1
    with readonly.read() as reader:
        assert reader.execute("SELECT * FROM setting").fetchall() == []
    with pytest.raises(RuntimeError), readonly.write():
        pass
    with pytest.raises(RuntimeError):
        readonly.migrate()
    readonly.close()
    assert path.read_bytes() == before
    missing = tmp_path / "missing" / "no.duckdb"
    with pytest.raises(InternalError):
        Database(missing, read_only=True).open()
    assert not missing.parent.exists()


def test_close_is_idempotent_and_context_lifecycle_is_guarded(db: Database) -> None:
    with db.read():
        for operation in [db.close, lambda: db.backup("test"), db.migrate]:
            with pytest.raises(RuntimeError):
                operation()
    db.close()
    db.close()
    for context in [db.read, db.write]:
        with pytest.raises(RuntimeError), context():
            pass


def test_exclusive_composes_backup_and_write_without_exposing_executor(db: Database) -> None:
    with db.write() as tx:
        tx.execute(
            "CREATE TABLE exclusive_sample (value INTEGER); INSERT INTO exclusive_sample VALUES (1)"
        )
    with db.exclusive() as protected:
        assert protected is None
        backup = db.backup("exclusive")
        with db.read() as reader:
            assert reader.execute("SELECT * FROM exclusive_sample").fetchall() == [(1,)]
        with db.write() as tx:
            tx.execute("DELETE FROM exclusive_sample")
    with duckdb.connect(str(backup), read_only=True) as restored:
        assert restored.execute("SELECT * FROM exclusive_sample").fetchall() == [(1,)]


def test_exclusive_blocks_other_handle_until_entire_sequence_finishes(db: Database) -> None:
    other = Database(db.path)
    other.open()
    attempted, entered = Event(), Event()
    with db.write() as tx:
        tx.execute(
            "CREATE TABLE exclusive_sample (value INTEGER); INSERT INTO exclusive_sample VALUES (1)"
        )

    def writer() -> None:
        attempted.set()
        with other.write() as tx:
            entered.set()
            tx.execute("INSERT INTO exclusive_sample VALUES (2)")

    try:
        with ThreadPoolExecutor(1) as pool:
            with db.exclusive():
                backup = db.backup("exclusive")
                task = pool.submit(writer)
                assert attempted.wait(2)
                assert not entered.wait(0.05)
                with db.write() as tx:
                    tx.execute("DELETE FROM exclusive_sample")
                assert not entered.is_set()
            task.result(timeout=3)
        with db.read() as reader:
            assert reader.execute("SELECT * FROM exclusive_sample").fetchall() == [(2,)]
        with duckdb.connect(str(backup), read_only=True) as restored:
            assert restored.execute("SELECT * FROM exclusive_sample").fetchall() == [(1,)]
    finally:
        other.close()


def test_exclusive_releases_lock_on_failure(db: Database) -> None:
    with pytest.raises(ValueError), db.exclusive():
        raise ValueError("synthetic failure")
    with ThreadPoolExecutor(1) as pool:
        assert pool.submit(lambda: db.schema_version).result(timeout=3) == 0


def test_exclusive_rejects_transaction_and_read_nesting(db: Database) -> None:
    with db.read(), pytest.raises(RuntimeError), db.exclusive():
        pass
    with db.write(), pytest.raises(RuntimeError), db.exclusive():
        pass


def test_exclusive_requires_open_database(db: Database) -> None:
    db.close()
    with pytest.raises(RuntimeError), db.exclusive():
        pass


def test_real_duckdb_cursor_transaction_is_independent() -> None:
    with duckdb.connect() as connection:
        connection.execute("CREATE TABLE sample (id INTEGER)")
        writer, reader = connection.cursor(), connection.cursor()
        try:
            writer.execute("BEGIN")
            writer.execute("INSERT INTO sample VALUES (1)")
            assert writer.execute("SELECT * FROM sample").fetchall() == [(1,)]
            assert reader.execute("SELECT * FROM sample").fetchall() == []
            writer.execute("ROLLBACK")
        finally:
            reader.close()
            writer.close()


def test_read_inside_write_has_independent_committed_snapshot(db: Database) -> None:
    with db.write() as tx:
        tx.execute("CREATE TABLE sample (id INTEGER)")
    with db.write() as tx:
        tx.execute("INSERT INTO sample VALUES (1)")
        with db.read() as reader:
            assert reader.execute("SELECT * FROM sample").fetchall() == []
        assert tx.execute("SELECT * FROM sample").fetchall() == [(1,)]


def test_caught_sql_failure_still_rolls_back_entire_transaction(db: Database) -> None:
    with db.write() as tx:
        tx.execute("CREATE TABLE sample (id INTEGER PRIMARY KEY)")
    with pytest.raises(duckdb.Error), db.write() as tx:
        tx.execute("INSERT INTO sample VALUES (1)")
        with suppress(duckdb.Error):
            tx.execute("INSERT INTO sample VALUES (1)")
    with db.read() as reader:
        assert reader.execute("SELECT * FROM sample").fetchall() == []


def test_utc_fetch_and_executemany(db: Database) -> None:
    instant = datetime(2026, 11, 2, tzinfo=UTC)
    db.migrate()
    with db.write() as tx:
        assert tx.executemany("INSERT INTO setting VALUES (?, ?, ?)", [["x", "1", instant]]) is None
        tx.execute("SELECT updated_at FROM setting")
        assert tx.fetchone() == (instant,)
    with db.read() as reader:
        assert reader.execute("SELECT updated_at FROM setting").fetchall() == [(instant,)]


def test_rolled_back_new_file_must_preserve_existing_wal(db: Database) -> None:
    with db.write() as tx:
        tx.execute("CREATE TABLE sample (id INTEGER)")
    with pytest.raises(ValueError), db.write() as tx:
        tx.execute("INSERT INTO sample VALUES (1)")
        raise ValueError()
    with db.read() as reader:
        assert reader.execute("SELECT * FROM sample").fetchall() == []


def test_existing_tx_cannot_write_inside_read_context(db: Database) -> None:
    db.migrate()
    with db.write() as tx, db.read(), pytest.raises(RuntimeError):
        tx.execute("INSERT INTO setting VALUES ('x', '1', TIMESTAMP '2026-11-02')")


def test_write_execute_returns_guarded_tx_and_cannot_commit_or_rollback(db: Database) -> None:
    with db.write() as tx:
        result = tx.execute("SELECT 1")
        assert result is tx
        assert isinstance(result, WriteTx)
        assert not isinstance(result, duckdb.DuckDBPyConnection)
        for method in ["commit", "rollback", "cursor", "connection"]:
            with pytest.raises(AttributeError):
                getattr(result, method)
        for sql in ["COMMIT", "ROLLBACK", "SELECT 1; BEGIN"]:
            with pytest.raises(RuntimeError):
                result.execute(sql)
        assert result.execute("SELECT 2").fetchone() == (2,)
    with pytest.raises(RuntimeError):
        result.execute("SELECT 3")


def test_write_fluent_fetches_use_utc_and_read_uncommitted_data(db: Database) -> None:
    instant = datetime(2026, 11, 2, tzinfo=UTC)
    db.migrate()

    def read_setting(executor: SqlExecutor) -> list[tuple[object, ...]]:
        executor.execute("SELECT key, updated_at FROM setting")
        return executor.fetchall()

    with db.write() as tx:
        tx.execute("INSERT INTO setting VALUES (?, ?, ?)", ["x", "1", instant])
        assert tx.execute("SELECT updated_at FROM setting").fetchone() == (instant,)
        assert tx.execute("SELECT updated_at FROM setting").fetchall() == [(instant,)]
        assert read_setting(tx) == [("x", instant)]
        with db.read() as reader:
            assert read_setting(reader) == []


def test_write_fluent_return_cannot_escape_rollback(db: Database) -> None:
    db.migrate()
    with pytest.raises(ValueError), db.write() as tx:
        result = tx.execute("INSERT INTO setting VALUES ('x', '1', TIMESTAMP '2026-11-02')")
        assert result is tx
        with pytest.raises(RuntimeError):
            result.execute("COMMIT")
        raise ValueError()
    with db.read() as reader:
        assert reader.execute("SELECT * FROM setting").fetchall() == []
