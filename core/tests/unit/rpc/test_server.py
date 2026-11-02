from __future__ import annotations

import io
import json
import os
import queue
import subprocess
import sys
import threading
import time
from collections.abc import Buffer, Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import IO

import pytest
from pydantic import BaseModel

from sentinel.errors import UserError
from sentinel.rpc import Dispatcher, RpcServer
from sentinel.rpc.builtins import EmptyParams
from sentinel.rpc.dispatcher import RequestContext
from sentinel.rpc.protocol import MAX_LINE_BYTES, serialize
from sentinel.rpc.writer import Writer, WriterClosed

from .conftest import PipePair


class SlowHandler:
    def __init__(self, count: int = 1) -> None:
        self.started = threading.Event()
        self.release = threading.Event()
        self.finished = threading.Event()
        self.count = count
        self.calls = 0
        self.tokens: list[bool] = []
        self.lock = threading.Lock()

    def __call__(self, params: BaseModel, ctx: RequestContext) -> dict[str, object]:
        with self.lock:
            self.calls += 1
            if self.calls >= self.count:
                self.started.set()
        assert self.release.wait(10.0)
        self.tokens.append(ctx.cancel.cancelled)
        self.finished.set()
        return {"ok": True}


def test_server_ping_does_not_use_worker_pool(dispatcher: Dispatcher) -> None:
    slow = SlowHandler(4)
    dispatcher.register("slow.method", slow, EmptyParams)
    pair = PipePair(dispatcher)
    try:
        for i in range(4):
            pair.request(f"slow-{i}", "slow.method")
        assert slow.started.wait(1.0)
        start = time.monotonic()
        pair.request("ping", "app.ping")
        response = pair.wait_for_line(0.2)
        assert time.monotonic() - start < 0.2
        assert response["id"] == "ping"
        assert response["result"]["ok"] is True  # type: ignore[index]
        assert slow.calls == 4
    finally:
        slow.release.set()
        pair.close()


def test_server_cancel_responds_within_200_ms(dispatcher: Dispatcher) -> None:
    slow = SlowHandler()
    dispatcher.register("slow.method", slow, EmptyParams, cancellable=True)
    pair = PipePair(dispatcher)
    try:
        pair.request("slow", "slow.method")
        assert slow.started.wait(1.0)
        start = time.monotonic()
        pair.cancel("slow")
        response = pair.wait_for_line(0.2)
        assert time.monotonic() - start < 0.2
        assert response["id"] == "slow"
        assert response["error"]["code"] == "CANCELLED"  # type: ignore[index]
        slow.release.set()
        assert slow.finished.wait(1.0)
        pair.cancel("slow")
        pair.cancel("unknown")
        pair.request("ping", "app.ping")
        assert pair.wait_for_line()["id"] == "ping"
        pair.input.close()
        pair.server.stop()
        assert pair.lines.empty()
    finally:
        slow.release.set()
        pair.close()


def test_non_cancellable_method_ignores_cancel(dispatcher: Dispatcher) -> None:
    slow = SlowHandler()
    dispatcher.register("paper.order.place", slow, EmptyParams)
    pair = PipePair(dispatcher)
    try:
        pair.request("mutation", "paper.order.place")
        assert slow.started.wait(1.0)
        pair.cancel("mutation")
        pair.request("barrier", "app.ping")
        assert pair.wait_for_line()["id"] == "barrier"
        slow.release.set()
        assert pair.wait_for_line() == {"jsonrpc": "2.0", "id": "mutation", "result": {"ok": True}}
        assert slow.tokens == [False]
        pair.server.stop()
        assert pair.lines.empty()
    finally:
        slow.release.set()
        pair.close()


def test_duplicate_id_preserves_inflight_token_and_never_reexecutes(dispatcher: Dispatcher) -> None:
    slow = SlowHandler()
    dispatcher.register("slow.method", slow, EmptyParams, cancellable=True)
    pair = PipePair(dispatcher)
    try:
        pair.request("same", "slow.method")
        assert slow.started.wait(1.0)
        pair.request("same", "app.ping")
        pair.request("same", "slow.method")
        pair.cancel("same")
        assert pair.wait_for_line()["error"]["code"] == "CANCELLED"  # type: ignore[index]
        slow.release.set()
        assert slow.finished.wait(1.0)
        pair.request("same", "app.ping")
        pair.request("barrier", "app.ping")
        assert pair.wait_for_line()["id"] == "barrier"
        pair.server.stop()
        assert slow.calls == 1
        assert slow.tokens == [True]
        assert pair.lines.empty()
    finally:
        slow.release.set()
        pair.close()


def test_invalid_json_with_id_returns_error_and_reader_continues(pipe_pair: PipePair) -> None:
    pipe_pair.raw(b'{"id":"bad","jsonrpc":"2.0",invalid}\nnot-json\n[]\n')
    pipe_pair.request("ping", "app.ping")
    assert pipe_pair.wait_for_line()["error"]["code"] == "INVALID_ARGUMENT"  # type: ignore[index]
    assert pipe_pair.wait_for_line()["id"] == "ping"


def test_unserializable_error_data_still_returns_one_internal_response(
    dispatcher: Dispatcher,
) -> None:
    def broken(params: BaseModel, ctx: RequestContext) -> dict[str, object]:
        raise UserError("INVALID_ARGUMENT", params={"invalid": object()})

    dispatcher.register("test.method", broken, EmptyParams)
    pair = PipePair(dispatcher)
    try:
        pair.request("broken", "test.method")
        response = pair.wait_for_line()
        assert response["id"] == "broken"
        assert response["error"]["code"] == "INTERNAL"  # type: ignore[index]
        pair.request("ping", "app.ping")
        assert pair.wait_for_line()["id"] == "ping"
    finally:
        pair.close()


def test_oversized_line_is_discarded_before_reading_next_request(pipe_pair: PipePair) -> None:
    # 尾部故意放完整合法请求，只有下一整行可以执行。
    embedded = serialize({"jsonrpc": "2.0", "id": "embedded", "method": "app.ping", "params": {}})
    pipe_pair.raw(b'{"jsonrpc":"2.0","id":"large","params":"' + b"x" * MAX_LINE_BYTES + embedded)
    response = pipe_pair.wait_for_line()
    assert response["id"] == "large"
    assert response["error"]["code"] == "INVALID_ARGUMENT"  # type: ignore[index]
    pipe_pair.request("next", "app.ping")
    assert pipe_pair.wait_for_line()["id"] == "next"


def test_eof_drains_all_queued_requests_and_stops(dispatcher: Dispatcher) -> None:
    dispatcher.register("test.method", lambda p, c: {"requestId": c.request_id}, EmptyParams)
    pair = PipePair(dispatcher)
    try:
        for i in range(100):
            pair.request(f"r-{i}", "test.method")
        pair.input.close()
        pair.server.serve_forever()
        responses = [pair.wait_for_line() for _ in range(100)]
        assert {r["id"] for r in responses} == {f"r-{i}" for i in range(100)}
        assert all("result" in r for r in responses)
        assert pair.server.stopped
    finally:
        pair.close()


def test_cancel_completion_races_still_produce_exactly_one_response(dispatcher: Dispatcher) -> None:
    dispatcher.register("test.method", lambda p, c: {"ok": True}, EmptyParams, cancellable=True)
    pair = PipePair(dispatcher)
    try:
        for i in range(200):
            pair.request(f"r-{i}", "test.method")
            pair.cancel(f"r-{i}")
        pair.input.close()
        pair.server.serve_forever()
        responses = [pair.wait_for_line() for _ in range(200)]
        assert len({r["id"] for r in responses}) == 200
        assert all(
            "result" in r or r["error"]["code"] == "CANCELLED"  # type: ignore[index]
            for r in responses
        )
        assert pair.lines.empty()
    finally:
        pair.close()


def test_cancel_queued_task_does_not_execute_handler(dispatcher: Dispatcher) -> None:
    slow = SlowHandler(4)
    dispatcher.register("slow.method", slow, EmptyParams)
    called = threading.Event()

    def queued(params: BaseModel, ctx: RequestContext) -> dict[str, object]:
        called.set()
        return {}

    dispatcher.register("queued.method", queued, EmptyParams, cancellable=True)
    pair = PipePair(dispatcher)
    try:
        for i in range(4):
            pair.request(f"slow-{i}", "slow.method")
        assert slow.started.wait(1.0)
        pair.request("queued", "queued.method")
        pair.cancel("queued")
        assert pair.wait_for_line()["error"]["code"] == "CANCELLED"  # type: ignore[index]
        slow.release.set()
        pair.server.stop()
        assert not called.is_set()
    finally:
        slow.release.set()
        pair.close()


def test_start_once_and_stop_idempotent(pipe_pair: PipePair) -> None:
    with pytest.raises(RuntimeError):
        pipe_pair.server.start()
    pipe_pair.server.stop()
    pipe_pair.server.stop()
    assert pipe_pair.server.stopped


def test_notify_writes_notification_without_response(pipe_pair: PipePair) -> None:
    pipe_pair.server.notify("scan.progress", {"done": 1})
    assert pipe_pair.wait_for_line() == {
        "jsonrpc": "2.0",
        "method": "scan.progress",
        "params": {"done": 1},
    }


def test_watchdog_is_injectable_and_uses_two_second_interval() -> None:
    calls: list[tuple[int, float]] = []
    source = io.BytesIO()
    output = io.BytesIO()

    # 输入保持阻塞，退出由 watchdog 触发。
    class BlockingInput(io.BytesIO):
        def __init__(self) -> None:
            super().__init__()
            self.closed_event = threading.Event()

        def readline(self, size: int | None = -1) -> bytes:
            self.closed_event.wait()
            return b""

        def close(self) -> None:
            self.closed_event.set()
            super().close()

    source = BlockingInput()

    def alive(pid: int) -> bool:
        calls.append((pid, time.monotonic()))
        return False

    server = RpcServer(source, output, Dispatcher(), parent_pid=123, process_alive=alive)
    start = time.monotonic()
    server.serve_forever()
    assert server.stopped and source.closed
    assert len(calls) == 1 and calls[0][0] == 123
    assert 1.9 <= calls[0][1] - start < 2.5


class GatedOutput(io.BytesIO):
    def __init__(self) -> None:
        super().__init__()
        self.entered = threading.Event()
        self.release = threading.Event()

    def write(self, data: Buffer, /) -> int:
        self.entered.set()
        assert self.release.wait(10.0)
        return super().write(data)


def test_writer_backpressure_does_not_drop_responses() -> None:
    output = GatedOutput()
    writer = Writer(output, queue_size=1)
    writer.start()
    writer.send(b"one\n")
    assert output.entered.wait(1.0)
    writer.send(b"two\n")
    sent = threading.Event()

    def send() -> None:
        writer.send(b"three\n")
        sent.set()

    producer = threading.Thread(target=send)
    producer.start()
    try:
        assert not sent.wait(1.05)
        output.release.set()
        assert sent.wait(1.0)
        assert writer.close(1.0)
        assert output.getvalue() == b"one\ntwo\nthree\n"
    finally:
        output.release.set()
        producer.join(1.0)


def test_writer_drops_only_notification_after_one_second() -> None:
    output = GatedOutput()
    writer = Writer(output, queue_size=1)
    writer.start()
    writer.send(b"response\n")
    assert output.entered.wait(1.0)
    writer.send(b"second\n")
    try:
        start = time.monotonic()
        assert not writer.send(b"notification\n", notification=True)
        assert 1.0 <= time.monotonic() - start < 1.3
    finally:
        output.release.set()
        assert writer.close(1.0)
    assert output.getvalue() == b"response\nsecond\n"


def test_writer_handles_short_writes() -> None:
    class ShortOutput(io.BytesIO):
        def write(self, data: Buffer, /) -> int:
            return super().write(bytes(memoryview(data))[:3])

    output = ShortOutput()
    writer = Writer(output)
    writer.start()
    writer.send(b'{"ok":true}\n')
    assert writer.close(1.0)
    assert output.getvalue() == b'{"ok":true}\n'


def test_broken_output_stops_server_without_hanging() -> None:
    class BrokenOutput(io.BytesIO):
        def write(self, data: Buffer, /) -> int:
            raise BrokenPipeError()

    server = RpcServer(
        io.BytesIO(serialize({"jsonrpc": "2.0", "id": "r-1", "method": "app.ping", "params": {}})),
        BrokenOutput(),
        Dispatcher(),
    )
    server.serve_forever()
    assert server.stopped


def test_response_enqueue_deadline_reports_transport_failure() -> None:
    output = GatedOutput()
    writer = Writer(output, queue_size=1)
    writer.start()
    writer.send(b"one\n")
    assert output.entered.wait(1.0)
    writer.send(b"two\n")
    try:
        with pytest.raises(WriterClosed):
            writer.send(b"three\n", until=time.monotonic() + 0.05)
        assert writer.failed
    finally:
        output.release.set()
        assert not writer.close(1.0)


CHILD_SETUP = """
import os
import threading
from pydantic import BaseModel
from sentinel.rpc import Dispatcher
from sentinel.rpc.builtins import EmptyParams
from sentinel.rpc.dispatcher import RequestContext
import sentinel.rpc.__main__ as entry
dispatcher = Dispatcher()
def blocked(params: BaseModel, ctx: RequestContext) -> dict[str, object]:
    print("worker-started", flush=True)
    threading.Event().wait()
    return {}
def noisy(params: BaseModel, ctx: RequestContext) -> dict[str, object]:
    print("noise", flush=True)
    os.write(1, b"native-noise\\n")
    return {"ok": True}
dispatcher.register("slow.method", blocked, EmptyParams)
dispatcher.register("noisy.method", noisy, EmptyParams)
entry.Dispatcher = lambda: dispatcher
raise SystemExit(entry.main())
"""


@contextmanager
def child(script: str | None = None, *args: str) -> Iterator[subprocess.Popen[bytes]]:
    command = [sys.executable, "-c", script] if script else [sys.executable, "-m", "sentinel.rpc"]
    proc = subprocess.Popen(
        command + list(args),
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        cwd=Path(__file__).resolve().parents[3],
        env=os.environ | {"PYTHONUTF8": "1", "SENTINEL_OFFLINE": "1"},
    )
    try:
        yield proc
    finally:
        if proc.poll() is None:
            proc.kill()
        proc.wait(timeout=2.0)
        for stream in (proc.stdin, proc.stdout, proc.stderr):
            assert stream is not None
            stream.close()


def subprocess_line(stream: IO[bytes], timeout: float = 1.0) -> bytes:
    lines: queue.Queue[bytes] = queue.Queue()
    threading.Thread(target=lambda: lines.put(stream.readline()), daemon=True).start()
    return lines.get(timeout=timeout)


def send_child(
    proc: subprocess.Popen[bytes],
    request_id: str,
    method: str,
    params: dict[str, object] | None = None,
) -> None:
    assert proc.stdin is not None
    proc.stdin.write(
        serialize({"jsonrpc": "2.0", "id": request_id, "method": method, "params": params or {}})
    )
    proc.stdin.flush()


def test_server_writes_only_ndjson() -> None:
    with child(CHILD_SETUP) as proc:
        assert proc.stdout is not None and proc.stderr is not None
        send_child(proc, "noise", "noisy.method")
        response = json.loads(subprocess_line(proc.stdout))
        assert response["result"] == {"ok": True}
        send_child(proc, "shutdown", "app.shutdown")
        assert json.loads(subprocess_line(proc.stdout))["result"] == {"ok": True}
        assert proc.wait(timeout=1.0) == 0
        assert proc.stdout.read() == b""
        assert b"noise\nnative-noise\n" in proc.stderr.read()


@pytest.mark.parametrize("force", [False, True])
def test_real_subprocess_shutdown_exits_with_four_permanently_blocked_workers(force: bool) -> None:
    with child(CHILD_SETUP) as proc:
        assert proc.stdout is not None and proc.stderr is not None
        for i in range(4):
            send_child(proc, f"slow-{i}", "slow.method")
        for _ in range(4):
            assert subprocess_line(proc.stderr) == b"worker-started\n"
        send_child(proc, "ping", "app.ping")
        assert json.loads(subprocess_line(proc.stdout, 0.2))["id"] == "ping"
        start = time.monotonic()
        send_child(proc, "shutdown", "app.shutdown", {"force": force})
        assert json.loads(subprocess_line(proc.stdout, 0.2)) == {
            "jsonrpc": "2.0",
            "id": "shutdown",
            "result": {"ok": True},
        }
        assert proc.wait(timeout=4.0) == 0
        elapsed = time.monotonic() - start
        assert elapsed < (0.5 if force else 3.6)
        if not force:
            assert elapsed >= 2.9
        responses = [json.loads(line) for line in proc.stdout.readlines()]
        assert len(responses) == 4
        assert {r["id"] for r in responses} == {f"slow-{i}" for i in range(4)}
        assert all(r["error"]["code"] == "INTERNAL" for r in responses)


def test_cli_eof_flushes_output_and_exits_zero() -> None:
    with child() as proc:
        send_child(proc, "ping", "app.ping")
        assert proc.stdin is not None and proc.stdout is not None
        proc.stdin.close()
        assert proc.wait(timeout=1.0) == 0
        assert json.loads(proc.stdout.readline())["id"] == "ping"
        assert proc.stdout.read() == b""


def test_real_parent_watchdog_exits_with_stdin_still_open() -> None:
    with child(None, "--parent-pid", "2147483647") as proc:
        start = time.monotonic()
        assert proc.wait(timeout=3.0) == 0
        assert time.monotonic() - start >= 1.9
