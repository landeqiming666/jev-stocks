import os
import subprocess
import sys
import textwrap
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import BinaryIO

import duckdb
import pytest

from sentinel.storage import Database
from sentinel.storage import backup as backup_module
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


def test_backup_is_synced_and_complete_before_atomic_publication(
    db: Database, monkeypatch: pytest.MonkeyPatch
) -> None:
    db.migrate()
    with db.write() as tx:
        tx.execute("INSERT INTO setting VALUES ('x', '1', TIMESTAMP '2026-11-02')")
    synced = False
    native_sync, native_link = os.fsync, os.link

    def sync(descriptor: int) -> None:
        nonlocal synced
        assert os.fstat(descriptor).st_size == db.path.stat().st_size
        native_sync(descriptor)
        synced = True

    def publish(source: Path, target: Path) -> None:
        assert synced
        assert source.parent == target.parent
        assert source.suffix != ".duckdb"
        assert not target.exists()
        assert not list(target.parent.glob("*.duckdb"))
        with duckdb.connect(str(source), read_only=True) as raw:
            assert raw.execute("SELECT key FROM setting").fetchall() == [("x",)]
        native_link(source, target)

    monkeypatch.setattr(os, "fsync", sync)
    monkeypatch.setattr(os, "link", publish)
    backup = db.backup("durable")
    assert backup.exists()
    assert synced
    assert not list(backup.parent.glob("*.tmp"))


@pytest.mark.parametrize("failure", ["copy", "fsync", "publish"])
def test_failed_backup_never_exposes_partial_file_or_prunes_old_backups(
    db: Database, monkeypatch: pytest.MonkeyPatch, failure: str
) -> None:
    previous = [db.backup(label) for label in ["old1", "old2", "old3"]]
    before = {path: path.read_bytes() for path in previous}
    directory = previous[0].parent

    def partial_copy(source: BinaryIO, destination: BinaryIO) -> None:
        destination.write(source.read(64))
        destination.flush()
        assert set(directory.glob("*.duckdb")) == set(previous)
        raise OSError("interrupted copy")

    def fail(*args: object) -> None:
        raise OSError("interrupted " + failure)

    if failure == "copy":
        monkeypatch.setattr(backup_module.shutil, "copyfileobj", partial_copy)
    else:
        monkeypatch.setattr(os, "fsync" if failure == "fsync" else "link", fail)
    with pytest.raises(OSError, match="interrupted"):
        db.backup("failed")
    assert set(directory.iterdir()) == set(previous)
    assert {path: path.read_bytes() for path in previous} == before
    assert db.schema_version == 0


def test_atomic_publish_collision_preserves_existing_complete_backup(
    db: Database, monkeypatch: pytest.MonkeyPatch
) -> None:
    native_link = os.link
    raced: Path | None = None
    other = db.path.parent / "existing-backup.duckdb"
    with duckdb.connect(str(other)) as raw:
        raw.execute("CREATE TABLE marker(value INTEGER); INSERT INTO marker VALUES(7)")
    existing_bytes = other.read_bytes()

    def publish(source: Path, target: Path) -> None:
        nonlocal raced
        if raced is None:
            raced = target
            native_link(other, target)
        native_link(source, target)

    monkeypatch.setattr(os, "link", publish)
    backup = db.backup("race")
    assert raced is not None
    assert raced != backup
    assert backup.name.endswith("-2.duckdb")
    assert raced.read_bytes() == existing_bytes
    assert backup.read_bytes() != existing_bytes
    assert not list(backup.parent.glob("*.tmp"))


def test_killed_backup_process_leaves_only_unpublished_temporary_file(db: Database) -> None:
    db.migrate()
    previous = [db.backup(label) for label in ["old1", "old2", "old3"]]
    directory = previous[0].parent
    marker = db.path.parent / "copy-started"
    db.close()
    code = textwrap.dedent("""
        import sys
        from pathlib import Path
        from threading import Event
        from sentinel.storage import Database
        from sentinel.storage import backup
        def interrupted(source, destination):
            destination.write(source.read(64))
            destination.flush()
            Path(sys.argv[2]).write_text('started')
            Event().wait()
        backup.shutil.copyfileobj = interrupted
        db = Database(Path(sys.argv[1]))
        db.open()
        db.backup('killed')
    """)
    process = subprocess.Popen(
        [sys.executable, "-c", code, str(db.path), str(marker)],
        cwd=Path(__file__).resolve().parents[4],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    try:
        deadline = time.monotonic() + 5
        while not marker.exists() and process.poll() is None and time.monotonic() < deadline:
            time.sleep(0.01)
        assert marker.exists(), "backup subprocess failed to reach the interrupted copy"
        assert set(directory.glob("*.duckdb")) == set(previous)
        process.kill()
        process.wait(timeout=5)
    finally:
        if process.poll() is None:
            process.kill()
        process.communicate(timeout=5)
    assert process.returncode != 0
    assert set(directory.glob("*.duckdb")) == set(previous)
    temporary = list(directory.glob("*.tmp"))
    assert len(temporary) == 1
    assert temporary[0].stat().st_size == 64
    db.open()
    published = db.backup("after-kill")
    assert published.exists()
    assert len(list(directory.glob("*.duckdb"))) == 3
    assert temporary[0].exists()
    with duckdb.connect(str(published), read_only=True) as raw:
        assert raw.execute("SELECT version FROM schema_version").fetchall() == [(1,)]
