"""真实核心进程测试装置：stdin/stdout NDJSON、超时、清理与 stderr 收集。"""

from __future__ import annotations

import contextlib
import json
import os
import shutil
import signal
import subprocess
import threading
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import IO, Any

STARTUP_TIMEOUT_S = 30.0
REQUEST_TIMEOUT_S = 30.0
SHUTDOWN_TIMEOUT_S = 3.0
ROOT = Path(__file__).resolve().parents[3]


class CoreFailure(RuntimeError):
    """核心进程未按契约响应。"""


@dataclass(frozen=True)
class CoreConfig:
    data_dir: Path
    resource_dir: Path
    env: Mapping[str, str] = field(default_factory=dict)
    startup_timeout_s: float = STARTUP_TIMEOUT_S


class CoreHarness:
    def __init__(self, config: CoreConfig) -> None:
        self.config = config
        self._process: subprocess.Popen[bytes] | None = None
        self._stdout: IO[bytes] | None = None
        self._stderr: IO[bytes] | None = None
        self._stderr_lines: list[str] = []
        self._notifications: list[dict[str, Any]] = []
        self._consumed = 0
        self._responses: dict[str, dict[str, Any]] = {}
        self._condition = threading.Condition()
        self._sequence = 0
        self._reader: threading.Thread | None = None
        self._stderr_reader: threading.Thread | None = None
        self._raw: list[str] = []

    # -- 生命周期 ---------------------------------------------------------
    def start(self) -> None:
        uv = shutil.which("uv")
        if uv is None:
            raise CoreFailure("uv is required to start the real core")
        command = [
            uv,
            "run",
            "--project",
            str(ROOT / "core"),
            "python",
            "-m",
            "sentinel",
            "--data-dir",
            str(self.config.data_dir),
            "--resource-dir",
            str(self.config.resource_dir),
            "--log-level",
            "WARN",
        ]
        env = {
            "PATH": os.environ.get("PATH", ""),
            "HOME": os.environ.get("HOME", ""),
            "SENTINEL_OFFLINE": "1",
            "SENTINEL_CLOCK": "2026-11-02T08:35:00Z",
            "PYTHONUNBUFFERED": "1",
            **self.config.env,
        }
        self._process = subprocess.Popen(
            command,
            cwd=str(ROOT),
            env=env,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            start_new_session=True,
        )
        assert self._process.stdout is not None and self._process.stderr is not None
        self._stdout, self._stderr = self._process.stdout, self._process.stderr
        self._reader = threading.Thread(target=self._read_stdout, name="core-stdout", daemon=True)
        self._stderr_reader = threading.Thread(
            target=self._read_stderr, name="core-stderr", daemon=True
        )
        self._reader.start()
        self._stderr_reader.start()
        self.recv_until(
            lambda message: message.get("method") == "app.ready",
            self.config.startup_timeout_s,
        )

    def _read_stdout(self) -> None:
        assert self._stdout is not None
        for raw in self._stdout:
            line = raw.decode("utf-8", "replace").strip()
            if not line:
                continue
            self._raw.append(line)
            try:
                message = json.loads(line)
            except json.JSONDecodeError as exc:
                with self._condition:
                    self._condition.notify_all()
                raise CoreFailure(f"non-JSON stdout line: {line!r}") from exc
            with self._condition:
                if "id" in message:
                    self._responses[str(message["id"])] = message
                else:
                    self._notifications.append(message)
                self._condition.notify_all()

    def _read_stderr(self) -> None:
        assert self._stderr is not None
        for raw in self._stderr:
            self._stderr_lines.append(raw.decode("utf-8", "replace").rstrip())

    # -- 发送与接收 -------------------------------------------------------
    def send(self, payload: dict[str, Any]) -> str:
        if self._process is None or self._process.stdin is None:
            raise CoreFailure("core is not running")
        request_id = str(payload.get("id", ""))
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8") + b"\n"
        self._process.stdin.write(data)
        self._process.stdin.flush()
        return request_id

    def notify(self, method: str, params: dict[str, Any]) -> None:
        self.send({"jsonrpc": "2.0", "method": method, "params": params})

    def recv_until(
        self, predicate: Callable[[dict[str, Any]], bool], timeout_s: float
    ) -> dict[str, Any]:
        deadline = time.monotonic() + timeout_s
        with self._condition:
            while True:
                for index in range(self._consumed, len(self._notifications)):
                    if predicate(self._notifications[index]):
                        self._consumed = index + 1
                        return self._notifications[index]
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise CoreFailure(f"timeout waiting for message\n{self.stderr_tail()}")
                self._condition.wait(min(remaining, 0.05))

    def request(
        self,
        method: str,
        params: dict[str, Any] | None = None,
        timeout_s: float = REQUEST_TIMEOUT_S,
    ) -> dict[str, Any]:
        self._sequence += 1
        request_id = f"r-{self._sequence:02d}"
        self.send({"jsonrpc": "2.0", "id": request_id, "method": method, "params": params or {}})
        return self.wait_response(request_id, timeout_s)

    def wait_response(self, request_id: str, timeout_s: float) -> dict[str, Any]:
        deadline = time.monotonic() + timeout_s
        with self._condition:
            while request_id not in self._responses:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise CoreFailure(f"timeout waiting for {request_id}\n{self.stderr_tail()}")
                self._condition.wait(min(remaining, 0.05))
            return self._responses.pop(request_id)

    def cancel(self, request_id: str) -> None:
        self.send({"jsonrpc": "2.0", "method": "$/cancel", "params": {"id": request_id}})

    def result(self, method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        response = self.request(method, params)
        if "error" in response:
            raise CoreFailure(f"{method} failed: {response['error']}")
        result = response.get("result")
        if not isinstance(result, dict):
            raise CoreFailure(f"{method} returned non-object result")
        return result

    # -- 诊断与清理 -------------------------------------------------------
    def poll(self) -> int | None:
        return None if self._process is None else self._process.poll()

    def stderr(self) -> str:
        return "\n".join(self._stderr_lines)

    def stderr_tail(self, lines: int = 50) -> str:
        return "\n".join(self._stderr_lines[-lines:])

    def raw_lines(self) -> list[str]:
        return list(self._raw)

    def stop(self, force: bool = False) -> int:
        process = self._process
        if process is None:
            return 0
        if process.poll() is None:
            with contextlib.suppress(CoreFailure):
                self.request("app.shutdown", {"force": force}, timeout_s=SHUTDOWN_TIMEOUT_S)
            try:
                process.wait(timeout=SHUTDOWN_TIMEOUT_S)
            except subprocess.TimeoutExpired:
                self._kill()
        code = process.wait(timeout=5)
        for stream in (self._stdout, self._stderr):
            if stream is not None:
                stream.close()
        if process.stdin is not None:
            process.stdin.close()
        self._process = None
        return code

    def _kill(self) -> None:
        process = self._process
        if process is None:
            return
        try:
            os.killpg(os.getpgid(process.pid), signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            process.kill()

    def __enter__(self) -> CoreHarness:
        self.start()
        return self

    def __exit__(self, *exc: object) -> None:
        self.stop()


__all__ = [
    "CoreConfig",
    "CoreFailure",
    "CoreHarness",
    "REQUEST_TIMEOUT_S",
    "SHUTDOWN_TIMEOUT_S",
    "STARTUP_TIMEOUT_S",
]
