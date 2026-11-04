from __future__ import annotations

import io
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

import pytest

from sentinel.app.args import AppArgs
from sentinel.app.container import AppContainer
from sentinel.app.errors import StartupError
from sentinel.app.lifecycle import shutdown, startup
from sentinel.app.main import run, serve
from sentinel.rpc import RpcServer

NOW = datetime(2026, 11, 2, 8, 0, tzinfo=UTC)


def _insert_run(container: AppContainer, run_id: str, status: str) -> None:
    with container.db.write() as tx:
        tx.execute(
            "INSERT INTO scan_run (run_id, trigger, market, status, window_start, window_end,"
            " engine, model_id, question_set_version, created_at)"
            " VALUES (?, 'manual', 'us', ?, ?, ?, 'jev_direct', 'jev-1.14.0', 'q1', ?)",
            [run_id, status, NOW, NOW, NOW],
        )


def _statuses(container: AppContainer) -> list[str]:
    with container.db.read() as reader:
        reader.execute("SELECT status FROM scan_run ORDER BY run_id")
        return [str(row[0]) for row in reader.fetchall()]


def test_recover_marks_queued_and_running_once(container: AppContainer) -> None:
    _insert_run(container, "run-a", "queued")
    _insert_run(container, "run-b", "running")
    assert startup(container) == 2
    assert _statuses(container) == ["interrupted", "interrupted"]


def test_serve_sends_ready_first_and_recovers_before_requests(
    container: AppContainer, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[str] = []
    original = container.scan.recover_on_startup

    def recover() -> int:
        calls.append("recover")
        return original()

    monkeypatch.setattr(container.scan, "recover_on_startup", recover)
    request = json.dumps(
        {"jsonrpc": "2.0", "id": "r-01", "method": "app.shutdown", "params": {}}
    ).encode()
    stdout = io.BytesIO()
    code = serve(container, parent_pid=None, stdin=io.BytesIO(request + b"\n"), stdout=stdout)
    assert code == 0
    assert calls == ["recover"]
    first = json.loads(stdout.getvalue().splitlines()[0])
    assert first["method"] == "app.ready"
    assert first["params"]["migrationsApplied"] == 12


def test_migration_failure_exits_three(tmp_path: Path) -> None:
    def failing(args: AppArgs) -> AppContainer:
        raise StartupError(StartupError.MIGRATION_FAILED)

    code = run(
        ["--data-dir", str(tmp_path / "data"), "--resource-dir", str(_resources())],
        container_factory=failing,
    )
    assert code == 3


def test_bad_arguments_exit_two(tmp_path: Path) -> None:
    code = run(["--data-dir", str(tmp_path / "data")])
    assert code == 2


def test_shutdown_closes_db_even_if_server_stop_fails(container: AppContainer) -> None:
    class _Broken:
        def stop(self) -> None:
            raise RuntimeError("boom")

    shutdown(container, cast(RpcServer, _Broken()))
    with pytest.raises(RuntimeError), container.db.read():
        pass


def _resources() -> Path:
    return Path(__file__).resolve().parents[4] / "resources"
