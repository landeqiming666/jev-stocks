from __future__ import annotations

import io
import sys
import time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from tests.integration import harness as module
from tests.integration.harness import CoreConfig, CoreFailure, CoreHarness


def _process(output: bytes) -> SimpleNamespace:
    return SimpleNamespace(
        pid=4321,
        stdin=io.BytesIO(),
        stdout=io.BytesIO(output),
        stderr=io.BytesIO(),
        poll=lambda: 0,
        wait=lambda **kwargs: 0,
        kill=Mock(),
    )


def test_automated_core_uses_memory_secrets_and_keeps_windows_runtime_env(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    child = _process(b'{"jsonrpc":"2.0","method":"app.ready","params":{}}\n')
    launch = Mock(return_value=child)
    monkeypatch.setattr(module.shutil, "which", lambda name: "uv")
    monkeypatch.setattr(module.subprocess, "Popen", launch)
    monkeypatch.setenv("SYSTEMROOT", "isolated-system")
    monkeypatch.setenv("TEMP", str(tmp_path))
    for name in ("JEV_API_KEY", "TYPESAFE_API_KEY", "JEV_ENDPOINT", "SENTINEL_JEVDB_PATH"):
        monkeypatch.setenv(name, "must-not-reach-the-child")
    core = CoreHarness(CoreConfig(tmp_path / "data", tmp_path / "resources"))
    core.start()
    core.stop()
    arguments, options = launch.call_args
    assert str(module.ROOT / "apps/desktop/e2e/acceptance/memory_core.py") in arguments[0]
    assert "--offline" in arguments[0]
    env = options["env"]
    assert env["SYSTEMROOT"] == "isolated-system" and env["TEMP"] == str(tmp_path)
    assert env["SENTINEL_OFFLINE"] == "1" and env["PYTHONUTF8"] == "1"
    assert not any(value == "must-not-reach-the-child" for value in env.values())


def test_failed_start_reaps_the_child_and_closes_pipes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    child = _process(b"not ndjson\n")
    monkeypatch.setattr(module.shutil, "which", lambda name: "uv")
    monkeypatch.setattr(module.subprocess, "Popen", lambda *args, **kwargs: child)
    core = CoreHarness(CoreConfig(tmp_path / "data", tmp_path / "resources"))
    kill = Mock()
    monkeypatch.setattr(core, "_kill", kill)
    with pytest.raises(CoreFailure, match="non-JSON stdout"):
        core.start()
    kill.assert_called_once()
    assert child.stdin.closed and child.stdout.closed and child.stderr.closed
    assert core._process is None


def test_windows_kill_uses_the_owned_root_process_tree(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delattr(module.os, "killpg", raising=False)
    monkeypatch.setenv("SYSTEMROOT", str(tmp_path / "Windows"))
    run = Mock()
    monkeypatch.setattr(module.subprocess, "run", run)
    child = _process(b"")
    child.poll = Mock(side_effect=[None, 0])
    core = CoreHarness(CoreConfig(tmp_path / "data", tmp_path / "resources"))
    core._process = child
    core._kill()
    assert run.call_args.args[0] == [
        str(tmp_path / "Windows" / "System32/taskkill.exe"),
        "/PID",
        "4321",
        "/T",
        "/F",
    ]
    assert run.call_args.kwargs["timeout"] == 5
    child.kill.assert_not_called()


@pytest.mark.parametrize(
    "failure", [OSError("unavailable"), module.subprocess.TimeoutExpired("taskkill", 5)]
)
def test_windows_kill_failure_still_terminates_the_live_child(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, failure: Exception
) -> None:
    monkeypatch.delattr(module.os, "killpg", raising=False)
    monkeypatch.setattr(module.subprocess, "run", Mock(side_effect=failure))
    child = _process(b"")
    child.poll = lambda: None
    core = CoreHarness(CoreConfig(tmp_path / "data", tmp_path / "resources"))
    core._process = child
    core._kill()
    child.kill.assert_called_once()


@pytest.mark.windows
def test_failed_start_terminates_real_descendant(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from ctypes import wintypes

    from sentinel.platform.windows import _kernel32

    _kernel32.TerminateProcess.argtypes = (wintypes.HANDLE, wintypes.UINT)
    _kernel32.TerminateProcess.restype = wintypes.BOOL
    script = tmp_path / "no ready.py"
    leaf_file = tmp_path / "leaf.pid"
    script.write_text(
        "import subprocess, sys, time\n"
        "from pathlib import Path\n"
        "leaf = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'])\n"
        f"Path({str(leaf_file)!r}).write_text(str(leaf.pid))\n"
        "time.sleep(60)\n",
        encoding="utf-8",
    )
    real_popen = module.subprocess.Popen
    children = []
    leaf_handles = []

    def launch(command, **options):
        if command[0] != sys.executable or "run" not in command:
            return real_popen(command, **options)
        child = real_popen([sys.executable, str(script)], **options)
        children.append(child)
        deadline = time.monotonic() + 1
        while not leaf_file.exists() and child.poll() is None and time.monotonic() < deadline:
            time.sleep(0.01)
        if leaf_file.exists():
            leaf_pid = int(leaf_file.read_text())
            handle = _kernel32.OpenProcess(0x00100001, False, leaf_pid)
            if handle:
                leaf_handles.append(handle)
        return child

    monkeypatch.setattr(module.shutil, "which", lambda name: sys.executable)
    monkeypatch.setattr(module.subprocess, "Popen", launch)
    core = CoreHarness(CoreConfig(tmp_path / "data", tmp_path / "resources", startup_timeout_s=2))
    try:
        with pytest.raises(CoreFailure, match="timeout waiting"):
            core.start()
        assert len(leaf_handles) == 1
        assert _kernel32.WaitForSingleObject(leaf_handles[0], 3000) == 0
        assert children[0].poll() is not None
    finally:
        if children and children[0].poll() is None:
            children[0].kill()
            children[0].wait(timeout=5)
        for handle in leaf_handles:
            try:
                if _kernel32.WaitForSingleObject(handle, 0) == 258:
                    _kernel32.TerminateProcess(handle, 1)
                    _kernel32.WaitForSingleObject(handle, 5000)
            finally:
                _kernel32.CloseHandle(handle)
