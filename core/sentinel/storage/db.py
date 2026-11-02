"""Serialized access to a DuckDB file through scoped cursors."""

from __future__ import annotations

import re
import threading
from collections.abc import Iterator, Sequence
from contextlib import contextmanager, suppress
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Protocol, cast
from weakref import WeakSet, WeakValueDictionary

import duckdb

from sentinel import clock
from sentinel.errors import InternalError

if TYPE_CHECKING:
    from .migrations import MigrationReport

DB_FILENAME = "sentinel.duckdb"
_LABEL_RE = re.compile(r"[a-z][a-z0-9_.-]{0,31}")


@dataclass
class _Gate:
    lock: threading.RLock = field(default_factory=threading.RLock)
    local: threading.local = field(default_factory=threading.local)
    handles: WeakSet[Database] = field(default_factory=WeakSet)

    def require_idle(self) -> None:
        if getattr(self.local, "reads", 0) or getattr(self.local, "writing", False):
            raise RuntimeError("operation requires no active read or write context")


_GATES: WeakValueDictionary[Path, _Gate] = WeakValueDictionary()
_GATES_LOCK = threading.Lock()


def _gate_for_path(path: Path) -> _Gate:
    with _GATES_LOCK:
        key = path.resolve()
        gate = _GATES.get(key)
        if gate is None:
            gate = _Gate()
            _GATES[key] = gate
        return gate


class SqlExecutor(Protocol):
    def execute(self, sql: str, params: Sequence[object] | None = None) -> object: ...
    def executemany(self, sql: str, rows: Sequence[Sequence[object]]) -> object: ...
    def fetchone(self) -> tuple[object, ...] | None: ...
    def fetchall(self) -> list[tuple[object, ...]]: ...


def _utc_row(row: tuple[object, ...]) -> tuple[object, ...]:
    return tuple(
        value.replace(tzinfo=UTC) if isinstance(value, datetime) and value.tzinfo is None else value
        for value in row
    )


class _Reader:
    def __init__(self, cursor: duckdb.DuckDBPyConnection) -> None:
        self._cursor = cursor
        self._thread = threading.get_ident()
        self._active = True

    def _check_active(self) -> None:
        if not self._active or self._thread != threading.get_ident():
            raise RuntimeError("executor is closed or belongs to another thread")

    def _validate(self, sql: str) -> None:
        self._check_active()
        statements = self._cursor.extract_statements(sql)
        if any(statement.type.name != "SELECT" for statement in statements):
            raise InternalError(detail="read: only SELECT statements are allowed")

    def execute(self, sql: str, params: Sequence[object] | None = None) -> object:
        self._validate(sql)
        self._cursor.execute(sql, params)
        return self

    def executemany(self, sql: str, rows: Sequence[Sequence[object]]) -> None:
        self._validate(sql)
        self._cursor.executemany(sql, rows)

    def fetchone(self) -> tuple[object, ...] | None:
        self._check_active()
        row = cast("tuple[object, ...] | None", self._cursor.fetchone())
        return None if row is None else _utc_row(row)

    def fetchall(self) -> list[tuple[object, ...]]:
        self._check_active()
        return [_utc_row(row) for row in cast("list[tuple[object, ...]]", self._cursor.fetchall())]


class WriteTx(_Reader):
    def __init__(self, cursor: duckdb.DuckDBPyConnection, gate: _Gate) -> None:
        super().__init__(cursor)
        self._failure: duckdb.Error | None = None
        self._gate = gate

    def _validate(self, sql: str) -> None:
        self._check_active()
        statements = self._cursor.extract_statements(sql)
        if any(statement.type.name == "TRANSACTION" for statement in statements):
            raise RuntimeError("transaction boundaries are owned by Database.write()")
        if getattr(self._gate.local, "reads", 0) and any(
            statement.type.name != "SELECT" for statement in statements
        ):
            raise RuntimeError("cannot write inside a read context")

    def execute(self, sql: str, params: Sequence[object] | None = None) -> WriteTx:
        try:
            self._validate(sql)
            self._cursor.execute(sql, params)
            return self
        except duckdb.Error as exc:
            if self._failure is None:
                self._failure = exc
            raise

    def executemany(self, sql: str, rows: Sequence[Sequence[object]]) -> None:
        try:
            super().executemany(sql, rows)
        except duckdb.Error as exc:
            if self._failure is None:
                self._failure = exc
            raise


class Database:
    def __init__(self, path: Path, *, read_only: bool = False) -> None:
        self._path = path.resolve()
        self._read_only = read_only
        self._gate = _gate_for_path(self._path)
        self._connection: duckdb.DuckDBPyConnection | None = None
        self._new_file = False
        self._created_files: set[Path] = set()

    @property
    def path(self) -> Path:
        return self._path

    def _connect(self) -> duckdb.DuckDBPyConnection:
        connection = duckdb.connect(str(self.path), read_only=self._read_only)
        try:
            self._configure(connection)
        except BaseException:
            connection.close()
            raise
        return connection

    @staticmethod
    def _configure(cursor: duckdb.DuckDBPyConnection) -> None:
        cursor.execute("PRAGMA enable_progress_bar=false")
        cursor.execute("SET TimeZone='UTC'")

    def open(self) -> None:
        from .migrations import SCHEMA_TABLE_SQL

        with self._gate.lock:
            self._gate.require_idle()
            if self._connection is not None:
                return
            candidates = {self.path, Path(str(self.path) + ".wal")}
            absent = {path for path in candidates if not path.exists()}
            self._new_file = self.path in absent
            try:
                if not self._read_only:
                    self.path.parent.mkdir(parents=True, exist_ok=True)
                self._connection = self._connect()
                if not self._read_only:
                    self._connection.execute(SCHEMA_TABLE_SQL)
                else:
                    self._connection.execute("SELECT version FROM schema_version LIMIT 0")
            except Exception as exc:
                self.close()
                for path in absent:
                    path.unlink(missing_ok=True)
                raise InternalError(detail="open") from exc
            self._created_files = absent
            self._gate.handles.add(self)

    def close(self) -> None:
        with self._gate.lock:
            self._gate.require_idle()
            if self._connection is not None:
                self._connection.close()
                self._connection = None
            self._gate.handles.discard(self)

    def _close_handles(self) -> tuple[Database, ...]:
        handles = tuple(self._gate.handles)
        for handle in handles:
            handle.close()
        return handles

    def _require_open(self) -> duckdb.DuckDBPyConnection:
        if self._connection is None:
            raise RuntimeError("database is not open")
        return self._connection

    @contextmanager
    def read(self) -> Iterator[SqlExecutor]:
        with self._gate.lock:
            cursor = self._require_open().cursor()
            reader = _Reader(cursor)
            local = self._gate.local
            local.reads = getattr(local, "reads", 0) + 1
            try:
                self._configure(cursor)
                # 独立 cursor 的只读事务还会拦截 SELECT nextval 等隐藏写入。
                cursor.execute("BEGIN TRANSACTION READ ONLY")
                yield reader
            finally:
                reader._active = False
                with suppress(duckdb.Error):
                    cursor.execute("ROLLBACK")
                cursor.close()
                local.reads -= 1

    @contextmanager
    def write(self) -> Iterator[WriteTx]:
        with self._gate.lock:
            self._gate.require_idle()
            connection = self._require_open()
            if self._read_only:
                raise RuntimeError("database is read-only")
            cursor = connection.cursor()
            tx = WriteTx(cursor, self._gate)
            self._gate.local.writing = True
            try:
                self._configure(cursor)
                cursor.execute("BEGIN TRANSACTION")
                yield tx
                if tx._failure is not None:
                    raise tx._failure
                cursor.execute("COMMIT")
                for handle in self._gate.handles:
                    handle._new_file = False
            except BaseException:
                with suppress(duckdb.Error):
                    cursor.execute("ROLLBACK")
                raise
            finally:
                tx._active = False
                cursor.close()
                self._gate.local.writing = False

    @property
    def schema_version(self) -> int:
        with self.read() as reader:
            reader.execute("SELECT COALESCE(MAX(version), 0) FROM schema_version")
            row = reader.fetchone()
            assert row is not None
            return cast(int, row[0])

    def _backup(self, label: str | None) -> Path:
        from .backup import _backup_file

        with self._gate.lock:
            self._gate.require_idle()
            connection = self._require_open()
            version = self.schema_version
            if self._read_only:
                raise RuntimeError("checkpoint backup requires a writable database")
            connection.execute("CHECKPOINT")
            handles = self._close_handles()
            try:
                return _backup_file(
                    self.path, self.path.parent / "backups", version, clock.now(), label
                )
            finally:
                for handle in handles:
                    handle._connection = handle._connect()
                    self._gate.handles.add(handle)

    def backup(self, label: str) -> Path:
        if _LABEL_RE.fullmatch(label) is None:
            raise ValueError("invalid backup label")
        return self._backup(label)

    def migrate(self, migrations_dir: Path | None = None) -> MigrationReport:
        from .migrations import migrate

        with self._gate.lock:
            self._gate.require_idle()
            self._require_open()
            if self._read_only:
                raise RuntimeError("database is read-only")
            return migrate(self, migrations_dir)
