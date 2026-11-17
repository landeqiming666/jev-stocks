from __future__ import annotations

from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import Any

import pytest

from sentinel.app.engines import ENV_JEVDB_PATH, EngineRuntime
from sentinel.errors import EngineError, ErrorCode
from sentinel.semantic.engines.jevdb import JevdbEngine

KEY = "test-key-do-not-use"


class RecordingConnection:
    description: Any = None

    def __init__(self, path: Path) -> None:
        self.path = path
        self.statements: list[str] = []
        self.closed = False

    def execute(self, query: str, parameters: Any = None) -> RecordingConnection:
        self.statements.append(query)
        if query.startswith("LOAD") and self.path.read_bytes() != b"loadable fixture":
            raise RuntimeError("controlled extension load failure")
        assert query.startswith(("LOAD", "SET", "DROP SECRET"))
        return self

    def executemany(self, query: str, parameters: Iterable[Sequence[Any]]) -> RecordingConnection:
        raise AssertionError("load verification must not submit model data")

    def fetchall(self) -> list[tuple[Any, ...]]:
        raise AssertionError("load verification must not submit model data")

    def fetchone(self) -> tuple[Any, ...] | None:
        raise AssertionError("load verification must not submit model data")

    def interrupt(self) -> None:
        pass

    def close(self) -> None:
        self.closed = True


def test_auto_load_failure_falls_back_and_closes_candidate(tmp_path: Path) -> None:
    path = tmp_path / "jevdb.duckdb_extension"
    path.write_bytes(b"invalid fixture")
    connections: list[RecordingConnection] = []

    def connect(*args: Any, **kwargs: Any) -> RecordingConnection:
        connection = RecordingConnection(path)
        connections.append(connection)
        return connection

    runtime = EngineRuntime(
        choice=lambda: "auto",
        secret=lambda: KEY,
        env={ENV_JEVDB_PATH: str(path)},
        jevdb_connection_factory=connect,
    )
    try:
        snapshot = runtime.snapshot()
        assert snapshot.active == "jev_direct" and not snapshot.jevdb_available
        assert runtime.health() == ("jev_direct", "ok")
        assert len(connections) == 1 and connections[0].closed
        assert connections[0].statements[0].startswith("LOAD")
        assert runtime.take_change() is not None
        assert runtime.take_change() is None
    finally:
        runtime.close()


def test_explicit_jevdb_propagates_native_load_failure(tmp_path: Path) -> None:
    path = tmp_path / "jevdb.duckdb_extension"
    path.write_bytes(b"invalid fixture")
    connection = RecordingConnection(path)
    runtime = EngineRuntime(
        choice=lambda: "jevdb",
        secret=lambda: KEY,
        env={ENV_JEVDB_PATH: str(path)},
        jevdb_connection_factory=lambda *args, **kwargs: connection,
    )
    try:
        with pytest.raises(EngineError) as caught:
            runtime.engine_for("jevdb")
        assert caught.value.code == ErrorCode.ENGINE_UNAVAILABLE
        assert caught.value.reason == "EXTENSION_LOAD"
        assert connection.closed
        assert runtime.current() is None and runtime.take_change() is None
    finally:
        runtime.close()


def test_auto_rechecks_replaced_and_restored_extension(tmp_path: Path) -> None:
    path = tmp_path / "jevdb.duckdb_extension"
    path.write_bytes(b"loadable fixture")
    connections: list[RecordingConnection] = []

    def connect(*args: Any, **kwargs: Any) -> RecordingConnection:
        connection = RecordingConnection(path)
        connections.append(connection)
        return connection

    runtime = EngineRuntime(
        choice=lambda: "auto",
        secret=lambda: KEY,
        env={ENV_JEVDB_PATH: str(path)},
        jevdb_connection_factory=connect,
    )
    try:
        assert runtime.snapshot().active == "jevdb"
        assert runtime.snapshot().jevdb_available
        assert len(connections) == 1 and not connections[0].closed
        path.write_bytes(b"broken replacement")
        assert runtime.snapshot().active == "jev_direct"
        assert len(connections) == 2 and all(connection.closed for connection in connections)
        assert runtime.take_change() is not None
        path.write_bytes(b"loadable fixture")
        assert runtime.snapshot().active == "jevdb"
        assert len(connections) == 3 and not connections[2].closed
        assert runtime.take_change() is None
        # The independent connection probe uses the same injected native factory.
        active = runtime.current()
        assert runtime.load_jevdb()
        assert runtime.current() is active
        assert len(connections) == 4 and connections[3].closed
    finally:
        runtime.close()
    assert all(connection.closed for connection in connections)


def test_auto_does_not_mask_non_availability_load_errors(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "jevdb.duckdb_extension"
    path.touch()
    closed: list[JevdbEngine] = []

    def timeout(engine: JevdbEngine) -> None:
        raise EngineError(ErrorCode.TIMEOUT)

    def close(engine: JevdbEngine) -> None:
        closed.append(engine)

    monkeypatch.setattr(JevdbEngine, "load", timeout)
    monkeypatch.setattr(JevdbEngine, "close", close)
    runtime = EngineRuntime(
        choice=lambda: "auto", secret=lambda: KEY, env={ENV_JEVDB_PATH: str(path)}
    )
    with pytest.raises(EngineError) as caught:
        runtime.engine_for("auto")
    assert caught.value.code == ErrorCode.TIMEOUT
    assert len(closed) == 1 and runtime.current() is None
    assert runtime.take_change() is None


def test_real_invalid_extension_is_not_reported_as_available(tmp_path: Path) -> None:
    path = tmp_path / "jevdb.duckdb_extension"
    path.write_bytes(b"invalid native extension")
    runtime = EngineRuntime(
        choice=lambda: "auto", secret=lambda: KEY, env={ENV_JEVDB_PATH: str(path)}
    )
    try:
        snapshot = runtime.snapshot()
        assert snapshot.active == "jev_direct" and not snapshot.jevdb_available
        assert runtime.health() == ("jev_direct", "ok")
        assert runtime.take_change() is not None
    finally:
        runtime.close()
