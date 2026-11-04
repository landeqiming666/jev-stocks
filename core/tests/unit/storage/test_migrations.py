import hashlib
import os
from pathlib import Path
from typing import BinaryIO

import duckdb
import pytest

from sentinel.errors import InternalError
from sentinel.storage import Database
from sentinel.storage import backup as backup_module
from sentinel.storage.migrations import MAX_MIGRATION_BYTES, _restore_file, split_sql

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures" / "storage" / "migrations"


def copy_fixture(directory: Path, filename: str) -> Path:
    target = directory / filename
    target.write_bytes((FIXTURES / filename).read_bytes())
    return target


def test_migrate_applies_001_and_reports_version(db: Database) -> None:
    report = db.migrate()
    assert report.applied == (1,)
    assert report.current_version == db.schema_version == 1
    assert report.backup_path is None
    with db.read() as reader:
        assert reader.execute("SELECT * FROM setting").fetchall() == []
    root = Path(__file__).resolve().parents[4]
    document = (root / "docs" / "04-数据模型.md").read_text(encoding="utf-8")
    ddl = document.split("### 3.1 `001_core.sql`")[1].split("```sql\n")[1].split("```")[0]
    assert (root / "core/sentinel/storage/migrations/001_core.sql").read_bytes() == ddl.encode()


def test_migrate_second_time_is_noop(db: Database) -> None:
    db.migrate()
    assert db.migrate().applied == ()
    assert db.schema_version == 1


@pytest.mark.parametrize("change", ["modified", "missing", "renamed"])
def test_checksum_mismatch_refuses_startup(db: Database, migrations_dir: Path, change: str) -> None:
    file = copy_fixture(migrations_dir, "001_ok.sql")
    db.migrate(migrations_dir)
    if change == "modified":
        file.write_text("CREATE TABLE other (id INTEGER);\n")
    elif change == "missing":
        file.unlink()
    else:
        file.rename(migrations_dir / "001_renamed.sql")
    with pytest.raises(InternalError) as exc:
        db.migrate(migrations_dir)
    assert "001_ok.sql" in (exc.value.detail or "")
    assert db.schema_version == 1


def test_lower_number_is_applied_after_higher(db: Database, migrations_dir: Path) -> None:
    copy_fixture(migrations_dir, "002_ok.sql")
    assert db.migrate(migrations_dir).applied == (2,)
    copy_fixture(migrations_dir, "001_ok.sql")
    report = db.migrate(migrations_dir)
    assert report.applied == (1,)
    assert report.current_version == 2


@pytest.mark.parametrize(
    "files",
    [
        ["bad.sql"],
        ["01_name.sql"],
        ["001_UPPER.sql"],
        ["001_a.sql", "001_b.sql"],
        ["000_zero.sql"],
    ],
)
def test_invalid_discovery_does_not_apply(
    db: Database, migrations_dir: Path, files: list[str]
) -> None:
    for filename in files:
        (migrations_dir / filename).write_text("CREATE TABLE unwanted (id INTEGER);")
    with pytest.raises(InternalError):
        db.migrate(migrations_dir)
    assert db.schema_version == 0


def test_missing_directory_and_size_limit(db: Database, migrations_dir: Path) -> None:
    with pytest.raises(InternalError):
        db.migrate(migrations_dir / "absent")
    file = migrations_dir / "001_big.sql"
    file.write_bytes(b" " * (MAX_MIGRATION_BYTES + 1))
    with pytest.raises(InternalError) as exc:
        db.migrate(migrations_dir)
    assert file.name in (exc.value.detail or "")
    file.write_bytes(b"--" + b" " * (MAX_MIGRATION_BYTES - 3) + b"\n")
    assert db.migrate(migrations_dir).applied == (1,)


def test_checksum_normalizes_lf(db: Database, migrations_dir: Path) -> None:
    file = migrations_dir / "001_ok.sql"
    lf = b"CREATE TABLE sample (id INTEGER);\n-- comment\n"
    file.write_bytes(lf.replace(b"\n", b"\r\n"))
    db.migrate(migrations_dir)
    with db.read() as reader:
        assert reader.execute("SELECT checksum FROM schema_version").fetchone() == (
            hashlib.sha256(lf).hexdigest(),
        )
    file.write_bytes(lf.replace(b"\n", b"\r"))
    assert db.migrate(migrations_dir).applied == ()


def test_split_sql_matches_duckdb_with_quotes_comments(db: Database, migrations_dir: Path) -> None:
    sql = (FIXTURES / "003_semicolon.sql").read_text()
    statements = split_sql(sql)
    with duckdb.connect() as raw:
        assert len(statements) == len(raw.extract_statements(sql)) == 3
        for statement in statements:
            raw.execute(statement)
        expected = raw.execute('SELECT * FROM "a;b"').fetchall()
    (migrations_dir / "003_semicolon.sql").write_text(sql)
    db.migrate(migrations_dir)
    with db.read() as reader:
        assert reader.execute('SELECT * FROM "a;b"').fetchall() == expected


def test_failed_migration_restores_backup(db: Database, migrations_dir: Path) -> None:
    copy_fixture(migrations_dir, "001_ok.sql")
    db.migrate(migrations_dir)
    with db.write() as tx:
        tx.execute("INSERT INTO sample VALUES (42)")
    assert Path(str(db.path) + ".wal").exists()
    copy_fixture(migrations_dir, "002_ok.sql")
    (migrations_dir / "003_bad.sql").write_text(
        "CREATE TABLE gone (id INTEGER);\nINSERT INTO absent VALUES(1);"
    )
    with pytest.raises(InternalError) as exc:
        db.migrate(migrations_dir)
    assert "003_bad.sql" in (exc.value.detail or "")
    assert "2" in (exc.value.detail or "")
    with pytest.raises(RuntimeError), db.read():
        pass
    db.open()
    assert db.schema_version == 1
    with db.read() as reader:
        assert reader.execute("SELECT * FROM sample").fetchall() == [(42,)]
        assert reader.execute("SHOW TABLES").fetchall() == [("sample",), ("schema_version",)]


def test_new_database_failure_removes_only_created_files(
    db: Database, migrations_dir: Path
) -> None:
    copy_fixture(migrations_dir, "001_ok.sql")
    copy_fixture(migrations_dir, "002_bad.sql")
    marker = db.path.parent / "unrelated.txt"
    marker.write_text("keep")
    with pytest.raises(InternalError):
        db.migrate(migrations_dir)
    assert not db.path.exists()
    assert not Path(str(db.path) + ".wal").exists()
    assert marker.read_text() == "keep"


def test_existing_empty_database_is_restored_not_deleted(
    tmp_path: Path, migrations_dir: Path
) -> None:
    path = tmp_path / "existing.duckdb"
    duckdb.connect(str(path)).close()
    db = Database(path)
    db.open()
    copy_fixture(migrations_dir, "001_ok.sql")
    copy_fixture(migrations_dir, "002_bad.sql")
    with pytest.raises(InternalError):
        db.migrate(migrations_dir)
    assert path.exists()
    with duckdb.connect(str(path)) as raw:
        assert raw.execute("SHOW TABLES").fetchall() == [("schema_version",)]


@pytest.mark.parametrize(
    "sql",
    [
        "DELETE FROM sample;",
        "DROP TABLE sample;",
        "BEGIN;",
        "UPDATE sample SET id=2;",
        "ALTER TABLE sample DROP id;",
    ],
)
def test_forbidden_migration_sql_is_rejected(db: Database, migrations_dir: Path, sql: str) -> None:
    copy_fixture(migrations_dir, "001_ok.sql")
    db.migrate(migrations_dir)
    (migrations_dir / "002_forbidden.sql").write_text(sql)
    with pytest.raises(InternalError):
        db.migrate(migrations_dir)


def test_ddl_rolls_back_in_real_duckdb() -> None:
    with duckdb.connect() as raw:
        raw.execute("BEGIN")
        raw.execute("CREATE TABLE rolled_back (id INTEGER)")
        with pytest.raises(duckdb.Error):
            raw.execute("INSERT INTO absent VALUES (1)")
        raw.execute("ROLLBACK")
        assert raw.execute("SHOW TABLES").fetchall() == []


def test_failed_migration_closes_all_handles_before_restore(
    db: Database, migrations_dir: Path
) -> None:
    copy_fixture(migrations_dir, "001_ok.sql")
    db.migrate(migrations_dir)
    other = Database(db.path)
    other.open()
    copy_fixture(migrations_dir, "002_bad.sql")
    try:
        with pytest.raises(InternalError):
            db.migrate(migrations_dir)
        with pytest.raises(RuntimeError), other.read():
            pass
        other.open()
        assert other.schema_version == 1
    finally:
        other.close()


def test_failed_batch_restores_exact_starting_file(db: Database, migrations_dir: Path) -> None:
    copy_fixture(migrations_dir, "001_ok.sql")
    db.migrate(migrations_dir)
    backup = db.backup("start")
    before = backup.read_bytes()
    copy_fixture(migrations_dir, "002_ok.sql")
    (migrations_dir / "003_bad.sql").write_text("INVALID SQL;")
    with pytest.raises(InternalError):
        db.migrate(migrations_dir)
    assert db.path.read_bytes() == before


def test_invalid_utf8_fails_before_changes(db: Database, migrations_dir: Path) -> None:
    (migrations_dir / "001_bad.sql").write_bytes(b"\xff")
    with pytest.raises(InternalError):
        db.migrate(migrations_dir)
    assert db.schema_version == 0


def test_other_handle_data_is_preserved_on_initial_migration_failure(
    db: Database, migrations_dir: Path
) -> None:
    other = Database(db.path)
    other.open()
    with other.write() as tx:
        tx.execute("CREATE TABLE sample (id INTEGER); INSERT INTO sample VALUES (11)")
    copy_fixture(migrations_dir, "002_bad.sql")
    with pytest.raises(InternalError):
        db.migrate(migrations_dir)
    assert db.path.exists()
    db.open()
    with db.read() as reader:
        assert reader.execute("SELECT * FROM sample").fetchall() == [(11,)]
    other.close()


@pytest.mark.parametrize(
    "sql",
    [
        "CREATE SEQUENCE seq;",
        "CREATE MACRO x() AS 1;",
        "CREATE SCHEMA hidden;",
        "CREATE TEMP TABLE hidden (id INTEGER);",
    ],
)
def test_migration_rejects_non_contract_create(
    db: Database, migrations_dir: Path, sql: str
) -> None:
    (migrations_dir / "001_forbidden.sql").write_text(sql)
    with pytest.raises(InternalError):
        db.migrate(migrations_dir)


def test_escape_string_semicolons_match_real_parser(db: Database, migrations_dir: Path) -> None:
    sql = r"CREATE TABLE escaped(value VARCHAR); INSERT INTO escaped VALUES(E'it\';s');"
    with duckdb.connect() as raw:
        assert len(raw.extract_statements(sql)) == 2
        for statement in split_sql(sql):
            raw.execute(statement)
        assert raw.execute("SELECT * FROM escaped").fetchall() == [("it';s",)]
    (migrations_dir / "001_escaped.sql").write_text(sql)
    db.migrate(migrations_dir)
    with db.read() as reader:
        assert reader.execute("SELECT * FROM escaped").fetchall() == [("it';s",)]


def test_restore_syncs_complete_temporary_copy_before_replace(
    db: Database, monkeypatch: pytest.MonkeyPatch
) -> None:
    db.migrate()
    backup = db.backup("restore")
    with db.write() as tx:
        tx.execute("INSERT INTO setting VALUES ('x', '1', TIMESTAMP '2026-11-02')")
    db.close()
    before = db.path.read_bytes()
    synced = False
    native_sync, native_replace = os.fsync, Path.replace

    def sync(descriptor: int) -> None:
        nonlocal synced
        assert os.fstat(descriptor).st_size == backup.stat().st_size
        native_sync(descriptor)
        synced = True

    def replace(source: Path, target: Path) -> Path:
        assert synced
        assert source.parent == target.parent
        assert source.read_bytes() == backup.read_bytes()
        assert target.read_bytes() == before
        return native_replace(source, target)

    monkeypatch.setattr(os, "fsync", sync)
    monkeypatch.setattr(Path, "replace", replace)
    _restore_file(backup, db.path)
    assert synced
    assert db.path.read_bytes() == backup.read_bytes()
    assert not list(db.path.parent.glob(".storage-restore-*"))
    db.open()
    with db.read() as reader:
        assert reader.execute("SELECT * FROM setting").fetchall() == []


@pytest.mark.parametrize("failure", ["copy", "fsync"])
def test_interrupted_restore_keeps_original_database_and_cleans_temporary_file(
    db: Database, monkeypatch: pytest.MonkeyPatch, failure: str
) -> None:
    db.migrate()
    backup = db.backup("restore")
    with db.write() as tx:
        tx.execute("INSERT INTO setting VALUES ('x', '1', TIMESTAMP '2026-11-02')")
    db.close()
    before = db.path.read_bytes()

    def interrupted(source: BinaryIO, destination: BinaryIO) -> None:
        destination.write(source.read(64))
        destination.flush()
        raise OSError("interrupted copy")

    def fail(descriptor: int) -> None:
        raise OSError("interrupted fsync")

    if failure == "copy":
        monkeypatch.setattr(backup_module.shutil, "copyfileobj", interrupted)
    else:
        monkeypatch.setattr(os, "fsync", fail)
    with pytest.raises(OSError, match="interrupted"):
        _restore_file(backup, db.path)
    assert db.path.read_bytes() == before
    assert not list(db.path.parent.glob(".storage-restore-*"))
    db.open()
    with db.read() as reader:
        assert reader.execute("SELECT key FROM setting").fetchall() == [("x",)]
