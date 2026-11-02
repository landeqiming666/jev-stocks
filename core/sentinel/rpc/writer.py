from __future__ import annotations

import logging
import queue
import threading
import time
from typing import BinaryIO

from sentinel.logging_setup import get_logger, log_event

WRITE_QUEUE_SIZE = 1024


class WriterClosed(RuntimeError):
    pass


class Writer:
    def __init__(self, stdout: BinaryIO, *, queue_size: int = WRITE_QUEUE_SIZE) -> None:
        self._stdout = stdout
        self._queue: queue.Queue[bytes] = queue.Queue(maxsize=queue_size)
        self._closing = threading.Event()
        self._failed = threading.Event()
        self._thread = threading.Thread(target=self._run, name="rpc-writer", daemon=True)

    @property
    def failed(self) -> bool:
        return self._failed.is_set()

    def start(self) -> None:
        self._thread.start()

    def send(
        self,
        payload: bytes,
        *,
        notification: bool = False,
        until: float | None = None,
    ) -> bool:
        deadline = time.monotonic() + 1.0
        while not self._closing.is_set() and not self.failed:
            try:
                self._queue.put(payload, timeout=0.05)
                return True
            except queue.Full:
                if until is not None and time.monotonic() >= until:
                    self._failed.set()
                    log_event(
                        get_logger(__name__), logging.ERROR, event="rpc.writer.response_timeout"
                    )
                    raise WriterClosed("RPC response could not be queued before shutdown") from None
                if time.monotonic() >= deadline:
                    log_event(
                        get_logger(__name__),
                        logging.WARNING,
                        event="rpc.writer.backpressure",
                        notification=notification,
                    )
                    if notification:
                        return False
                    # 响应不能按通知策略丢弃；等待消费者或显式传输失败。
                    deadline = time.monotonic() + 1.0
        raise WriterClosed("RPC output is closed")

    def close(self, timeout: float) -> bool:
        self._closing.set()
        self._thread.join(max(0.0, timeout))
        if self._thread.is_alive():
            self._failed.set()
            log_event(get_logger(__name__), logging.ERROR, event="rpc.writer.flush_timeout")
            return False
        return not self.failed

    def _run(self) -> None:
        try:
            while not self._closing.is_set() or not self._queue.empty():
                try:
                    payload = self._queue.get(timeout=0.02)
                except queue.Empty:
                    continue
                try:
                    # BinaryIO 允许短写，不能假定一次 write 就写完一条响应。
                    offset = 0
                    while offset < len(payload):
                        written = self._stdout.write(payload[offset:])
                        if written is None or written <= 0:
                            raise OSError("RPC output made no progress")
                        offset += written
                    self._stdout.flush()
                finally:
                    self._queue.task_done()
        except Exception as exc:
            self._failed.set()
            log_event(
                get_logger(__name__),
                logging.ERROR,
                event="rpc.writer.failed",
                detail=type(exc).__name__,
            )
