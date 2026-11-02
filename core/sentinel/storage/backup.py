"""Checkpointed file backups ordered by UTC timestamp and collision number."""

from __future__ import annotations

import os
import re
import shutil
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

import duckdb

BACKUP_KEEP = 3
_BACKUP_RE = re.compile(
    r"sentinel-v\d+-(?:[a-z][a-z0-9_.-]{0,31}-)?"
    r"(?P<time>\d{8}T\d{6}Z)(?:-(?P<serial>\d+))?\.duckdb"
)


def _order(path: Path) -> tuple[str, int, int, str]:
    match = _BACKUP_RE.fullmatch(path.name)
    assert match is not None
    return match["time"], path.stat().st_mtime_ns, int(match["serial"] or 1), path.name


def _published_backups(directory: Path) -> list[Path]:
    return [
        path
        for path in directory.glob("*.duckdb")
        if _BACKUP_RE.fullmatch(path.name) and path.is_file() and not path.is_symlink()
    ]


@contextmanager
def _synced_copy(source: Path, directory: Path, prefix: str) -> Iterator[Path]:
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            dir=directory, prefix=prefix, suffix=".tmp", delete=False
        ) as destination:
            temporary = Path(destination.name)
            with source.open("rb") as incoming:
                shutil.copyfileobj(incoming, destination)
            destination.flush()
            os.fsync(destination.fileno())
        yield temporary
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def _backup_file(
    db_path: Path, backup_dir: Path, version: int, now: datetime, label: str | None = None
) -> Path:
    if not db_path.is_file() or db_path.stat().st_size == 0:
        raise ValueError("database is missing or empty")
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("backup time must include a timezone")
    stamp = now.astimezone(UTC).strftime("%Y%m%dT%H%M%SZ")
    prefix = f"sentinel-v{version}-" + (f"{label}-" if label is not None else "") + stamp
    backup_dir = backup_dir.resolve()
    backup_dir.mkdir(parents=True, exist_ok=True)
    existing = _published_backups(backup_dir)
    if (
        len(existing) >= BACKUP_KEEP
        and stamp < _order(sorted(existing, key=_order)[-BACKUP_KEEP])[0]
    ):
        raise ValueError("backup timestamp predates the retained snapshots")
    serials = [
        int(match[1] or 1)
        for path in existing
        if (match := re.fullmatch(re.escape(prefix) + r"(?:-(\d+))?\.duckdb", path.name))
    ]
    serial = max(serials, default=0) + 1
    with _synced_copy(db_path, backup_dir, ".storage-backup-") as temporary:
        while True:
            suffix = "" if serial == 1 else f"-{serial}"
            target = backup_dir / f"{prefix}{suffix}.duckdb"
            try:
                # 硬链接只发布已同步的完整文件；目标已存在时原子失败，绝不覆盖。
                os.link(temporary, target)
            except FileExistsError:
                serial += 1
                continue
            break
    for old in sorted(_published_backups(backup_dir), key=_order)[:-BACKUP_KEEP]:
        old.unlink()
    return target


def backup_database(db_path: Path, backup_dir: Path, version: int, now: datetime) -> Path:
    from .db import _gate_for_path

    db_path = db_path.resolve()
    gate = _gate_for_path(db_path)
    with gate.lock:
        gate.require_idle()
        if not db_path.is_file() or db_path.stat().st_size == 0:
            raise ValueError("database is missing or empty")
        # CHECKPOINT 失败（例如仍有活动事务）时绝不能复制缺少 WAL 的主文件。
        connection = duckdb.connect(str(db_path))
        try:
            connection.execute("CHECKPOINT")
        finally:
            connection.close()
        return _backup_file(db_path, backup_dir, version, now)
