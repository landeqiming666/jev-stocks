from __future__ import annotations

import logging
import queue
import threading
import time
from collections.abc import Callable, Mapping
from contextlib import suppress
from dataclasses import dataclass
from typing import BinaryIO

from sentinel import clock
from sentinel.errors import CancelledError, InternalError
from sentinel.logging_setup import get_logger, log_event
from sentinel.platform import is_process_alive

from .builtins import PING_METHOD, SHUTDOWN_METHOD, register_builtins
from .cancel import CancelRegistry, CancelToken
from .dispatcher import Dispatcher, RequestContext
from .protocol import (
    MAX_LINE_BYTES,
    CancelNotification,
    ProtocolError,
    Request,
    failure,
    invalid,
    parse_request,
    serialize,
)
from .writer import Writer, WriterClosed

CANCEL_DEADLINE_MS = 200
WORKER_COUNT = 4


@dataclass(frozen=True)
class ServerConfig:
    max_line_bytes: int = MAX_LINE_BYTES
    workers: int = WORKER_COUNT
    cancel_deadline_ms: int = CANCEL_DEADLINE_MS
    shutdown_timeout_s: float = 3.0
    ping_timeout_s: float = 2.0

    def __post_init__(self) -> None:
        if min(self.max_line_bytes, self.workers, self.cancel_deadline_ms) <= 0:
            raise ValueError("server limits must be positive")
        if self.shutdown_timeout_s <= 0 or self.ping_timeout_s <= 0:
            raise ValueError("server timeouts must be positive")


@dataclass
class _State:
    token: CancelToken
    responded: bool = False


DEFAULT_CONFIG = ServerConfig()


class RpcServer:
    def __init__(
        self,
        stdin: BinaryIO,
        stdout: BinaryIO,
        dispatcher: Dispatcher,
        config: ServerConfig = DEFAULT_CONFIG,
        *,
        parent_pid: int | None = None,
        process_alive: Callable[[int], bool] = is_process_alive,
        on_start: Callable[[], None] | None = None,
    ) -> None:
        self._stdin = stdin
        self._dispatcher = dispatcher
        self._config = config
        self._parent_pid = parent_pid
        self._process_alive = process_alive
        self._on_start = on_start
        self._writer = Writer(stdout)
        self._registry = CancelRegistry()
        self._states: dict[str, _State] = {}
        self._seen: set[str] = set()
        self._condition = threading.Condition()
        self._jobs: queue.Queue[tuple[Request, _State]] = queue.Queue()
        self._pending = 0
        self._sending = 0
        self._started = False
        self._accept_responses = True
        self._force = False
        self._stop_event = threading.Event()
        self._stopped = threading.Event()
        self._reader = threading.Thread(target=self._read, name="rpc-reader", daemon=True)
        self._workers = [
            threading.Thread(target=self._work, name=f"rpc-worker-{i}", daemon=True)
            for i in range(config.workers)
        ]
        register_builtins(dispatcher, clock.now())

    @property
    def stopped(self) -> bool:
        return self._stopped.is_set()

    def set_start_hook(self, callback: Callable[[], None] | None) -> None:
        """在读取 stdin 之前执行一次；用于发送 app.ready。"""
        self._on_start = callback

    def start(self) -> None:
        with self._condition:
            if self._started or self._stop_event.is_set():
                raise RuntimeError("RPC server can only start once")
            self._started = True
        self._writer.start()
        for thread in self._workers:
            thread.start()
        threading.Thread(target=self._finish, name="rpc-lifecycle", daemon=True).start()
        if self._parent_pid is not None:
            threading.Thread(target=self._watch, name="rpc-watchdog", daemon=True).start()
        # 在读取 stdin 之前发送 app.ready，保证它是核心输出的第一条消息。
        if self._on_start is not None:
            self._on_start()
        self._reader.start()

    def serve_forever(self) -> None:
        if not self._started:
            self.start()
        self._stopped.wait()

    def _request_stop(self, *, force: bool = False) -> None:
        with self._condition:
            self._force |= force
            self._stop_event.set()
            self._condition.notify_all()

    def stop(self) -> None:
        if self.stopped:
            return
        self._request_stop()
        if not self._started:
            self._stopped.set()
            return
        self._stopped.wait()

    def notify(self, method: str, params: Mapping[str, object]) -> None:
        with self._condition:
            if not self._started or self._stop_event.is_set():
                raise RuntimeError("RPC server is not accepting messages")
            self._sending += 1
        try:
            self._writer.send(
                serialize({"jsonrpc": "2.0", "method": method, "params": dict(params)}),
                notification=True,
            )
        except WriterClosed:
            self._request_stop(force=True)
        finally:
            with self._condition:
                self._sending -= 1
                self._condition.notify_all()

    def _respond(
        self,
        request_id: str,
        response: dict[str, object],
        *,
        until: float | None = None,
    ) -> None:
        payload = serialize(response)
        with self._condition:
            state = self._states.get(request_id)
            if state is None or state.responded or not self._accept_responses:
                return
            state.responded = True
            del self._states[request_id]
            self._registry.unregister(request_id)
            self._sending += 1
        try:
            self._writer.send(payload, until=until)
        except WriterClosed:
            self._request_stop(force=True)
        finally:
            with self._condition:
                self._sending -= 1
                self._condition.notify_all()

    def _accept(self, request_id: str) -> _State | None:
        with self._condition:
            if self._stop_event.is_set() or request_id in self._seen:
                return None
            state = _State(CancelToken())
            self._seen.add(request_id)
            self._states[request_id] = state
            return state

    def _cancel(self, request_id: str) -> None:
        with self._condition:
            state = self._states.get(request_id)
            if (
                state is None
                or state.responded
                or not self._accept_responses
                or not self._registry.cancel(request_id)
            ):
                return
            # 持锁提交取消响应，完成和取消只有一个能取得响应权。
            state.responded = True
            del self._states[request_id]
            self._registry.unregister(request_id)
            self._sending += 1
        try:
            self._writer.send(serialize(failure(request_id, CancelledError())))
        except WriterClosed:
            self._request_stop(force=True)
        finally:
            with self._condition:
                self._sending -= 1
                self._condition.notify_all()

    def _read(self) -> None:
        try:
            while not self._stop_event.is_set():
                line = self._stdin.readline(self._config.max_line_bytes + 1)
                if not line:
                    break
                oversized = len(line) > self._config.max_line_bytes
                if oversized and not line.endswith(b"\n"):
                    # 丢弃整行，不把剩余字节误解释成下一条请求。
                    while not self._stop_event.is_set():
                        tail = self._stdin.readline(self._config.max_line_bytes + 1)
                        if not tail or tail.endswith(b"\n"):
                            break
                if not line.strip():
                    continue
                try:
                    request = parse_request(line, self._config.max_line_bytes)
                except ProtocolError as exc:
                    if exc.request_id is not None and self._accept(exc.request_id) is not None:
                        self._respond(exc.request_id, invalid(exc))
                    else:
                        log_event(
                            get_logger(__name__),
                            logging.WARNING,
                            event="rpc.reader.invalid",
                            reason=exc.reason,
                        )
                    continue
                if isinstance(request, CancelNotification):
                    self._cancel(request.params.id)
                    continue
                state = self._accept(request.id)
                if state is None:
                    continue
                spec = self._dispatcher.lookup(request.method)
                if request.method in (PING_METHOD, SHUTDOWN_METHOD):
                    # 关闭也必须能越过卡死的 worker，否则 force 参数无法生效。
                    response = self._dispatcher.dispatch(
                        spec, request.params, self._context(request, state)
                    )
                    self._respond(request.id, response)
                    if request.method == SHUTDOWN_METHOD and "result" in response:
                        self._request_stop(force=request.params.get("force") is True)
                else:
                    with self._condition:
                        if self._stop_event.is_set() or state.responded:
                            continue
                        self._registry.register(
                            request.id,
                            state.token,
                            cancellable=spec is not None and spec.cancellable,
                        )
                        self._pending += 1
                        self._jobs.put((request, state))
        except (OSError, ValueError) as exc:
            log_event(
                get_logger(__name__),
                logging.WARNING,
                event="rpc.reader.closed",
                detail=type(exc).__name__,
            )
        finally:
            self._request_stop()

    def _context(self, request: Request, state: _State) -> RequestContext:
        return RequestContext(request.id, request.method, state.token, clock.now())

    def _work(self) -> None:
        while True:
            try:
                request, state = self._jobs.get(timeout=0.02)
            except queue.Empty:
                if self._stop_event.is_set():
                    return
                continue
            try:
                with self._condition:
                    execute = (
                        not state.responded
                        and self._accept_responses
                        and not (self._stop_event.is_set() and self._force)
                    )
                if execute:
                    response = self._dispatcher.dispatch(
                        self._dispatcher.lookup(request.method),
                        request.params,
                        self._context(request, state),
                    )
                    self._respond(request.id, response)
                    if request.method == SHUTDOWN_METHOD and "result" in response:
                        self._request_stop(force=request.params.get("force") is True)
            finally:
                self._jobs.task_done()
                with self._condition:
                    self._pending -= 1
                    self._condition.notify_all()

    def _watch(self) -> None:
        while not self._stop_event.wait(2.0):
            assert self._parent_pid is not None
            try:
                alive = self._process_alive(self._parent_pid)
            except Exception as exc:
                log_event(
                    get_logger(__name__),
                    logging.ERROR,
                    event="rpc.watchdog.failed",
                    detail=type(exc).__name__,
                )
                alive = False
            if not alive:
                self._request_stop()

    def _close_input(self) -> None:
        with suppress(OSError, ValueError):
            self._stdin.close()

    def _finish(self) -> None:
        while not self._stop_event.wait(0.02):
            if self._writer.failed:
                self._request_stop(force=True)
        deadline = time.monotonic() + self._config.shutdown_timeout_s
        # BufferedReader.close 可能等待读锁；关闭动作也不能拖住进程退出。
        threading.Thread(target=self._close_input, name="rpc-input-close", daemon=True).start()
        with self._condition:
            while self._pending and not self._force and not self._writer.failed:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    break
                self._condition.wait(min(remaining, 0.02))
            outstanding = [rid for rid, state in self._states.items() if not state.responded]
        for request_id in outstanding:
            error: CancelledError | InternalError
            if self._registry.cancel(request_id):
                error = CancelledError()
            else:
                error = InternalError(reason="SHUTDOWN_TIMEOUT")
            self._respond(request_id, failure(request_id, error), until=deadline)
        with self._condition:
            self._accept_responses = False
            while self._sending and time.monotonic() < deadline:
                self._condition.wait(0.02)
        self._writer.close(max(0.1, deadline - time.monotonic()))
        self._stopped.set()
