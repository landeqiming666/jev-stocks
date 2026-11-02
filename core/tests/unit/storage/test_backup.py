from datetime import UTC, datetime, timedelta
from pathlib import Path

import duckdb
import pytest

from sentinel.storage import Database
from sentinel.storage.backup import backup_database


def test_backup_keeps_latest_three(tmp_path: Path) -> None:
    path = tmp_path / "sentinel.duckdb"
    duckdb.connect(str(path)).close()
    moment = datetime(2026, 11, 2, tzinfo=UTC)
    backups = [
        backup_database(path, tmp_path / "backups", version, moment + timedelta(seconds=n))
        for n, version in enumerate([999, 99, 9, 1])
    ]
    assert not backups[0].exists()
    assert all(path.exists() for path in backups[1:])


@pytest.mark.parametrize("label", ["../x", "A", "", "a/b", "a\\b", "a" * 33, "a\n", "a!", "中文"])
def test_backup_api_rejects_unsafe_label(db: Database, label: str) -> None:
    with pytest.raises(ValueError):
        db.backup(label)
    assert not (db.path.parent / "backups").exists()


def test_backup_same_second_collision_and_numeric_suffix(db: Database) -> None:
    db.migrate()
    paths = [db.backup("reset") for _ in range(12)]
    assert len(set(paths)) == 12
    assert paths[0].name == "sentinel-v1-reset-20261102T003500Z.duckdb"
    assert paths[-1].name.endswith("-12.duckdb")
    assert all(path.is_absolute() for path in paths)
    assert sorted(db.path.parent.joinpath("backups").glob("*.duckdb")) == sorted(paths[-3:])


def test_wal_backup_is_consistent_and_can_restore(db: Database) -> None:
    db.migrate()
    with db.write() as tx:
        tx.execute("INSERT INTO setting VALUES ('x', '1', TIMESTAMP '2026-11-02')")
    assert Path(str(db.path) + ".wal").exists()
    backup = db.backup("before-reset")
    assert not Path(str(backup) + ".wal").exists()
    with duckdb.connect(str(backup), read_only=True) as raw:
        assert raw.execute("SELECT key, value_json FROM setting").fetchall() == [("x", "1")]
    with db.write() as tx:
        tx.execute("INSERT INTO setting VALUES ('y', '2', TIMESTAMP '2026-11-02')")
    with db.read() as reader:
        assert reader.execute("SELECT count(*) FROM setting").fetchone() == (2,)


def test_standalone_backup_checkpoints_wal(tmp_path: Path) -> None:
    path = tmp_path / "sentinel.duckdb"
    with duckdb.connect(str(path)) as raw:
        raw.execute("CREATE TABLE sample (id INTEGER); INSERT INTO sample VALUES(7)")
        assert Path(str(path) + ".wal").exists()
        backup = backup_database(path, tmp_path / "backups", 0, datetime(2026, 11, 2, tzinfo=UTC))
        with duckdb.connect(str(backup), read_only=True) as restored:
            assert restored.execute("SELECT * FROM sample").fetchall() == [(7,)]


def test_backup_unavailable_or_inside_transaction(db: Database, tmp_path: Path) -> None:
    with db.write(), pytest.raises(RuntimeError):
        db.backup("inside")
    with pytest.raises(ValueError):
        backup_database(tmp_path / "absent.duckdb", tmp_path / "backups", 0, datetime.now(UTC))


def test_standalone_backup_cannot_ignore_active_transaction(tmp_path: Path) -> None:
    path = tmp_path / "sentinel.duckdb"
    with duckdb.connect(str(path)) as raw:
        raw.execute("CREATE TABLE sample (id INTEGER)")
        raw.execute("BEGIN; INSERT INTO sample VALUES(1)")
        with pytest.raises(duckdb.Error):
            backup_database(path, tmp_path / "backups", 0, datetime.now(UTC))
        raw.execute("ROLLBACK")
    assert not list(tmp_path.glob("backups/*.duckdb"))


def test_same_second_different_labels_keep_creation_order(db: Database) -> None:
    paths = [db.backup(label) for label in ["z", "y", "x", "a"]]
    assert not paths[0].exists()
    assert all(path.exists() for path in paths[1:])


def test_backup_restores_multiple_open_handles(db: Database) -> None:
    other = Database(db.path)
    other.open()
    try:
        with other.write() as tx:
            tx.execute("CREATE TABLE sample (id INTEGER); INSERT INTO sample VALUES (9)")
        backup = db.backup("multi")
        with duckdb.connect(str(backup), read_only=True) as raw:
            assert raw.execute("SELECT * FROM sample").fetchall() == [(9,)]
        with other.read() as reader:
            assert reader.execute("SELECT * FROM sample").fetchall() == [(9,)]
    finally:
        other.close()


def test_backdated_backup_cannot_return_a_deleted_recovery_file(tmp_path: Path) -> None:
    path = tmp_path / "sentinel.duckdb"
    duckdb.connect(str(path)).close()
    moment = datetime(2026, 11, 2, tzinfo=UTC)
    directory = tmp_path / "backups"
    for day in range(1, 4):
        backup_database(path, directory, day, moment + timedelta(days=day))
    before = set(directory.iterdir())
    with pytest.raises(ValueError):
        backup_database(path, directory, 0, moment)
    assert set(directory.iterdir()) == before
