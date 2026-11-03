import queue
import threading
import time
from collections.abc import Callable
from typing import TypeVar, cast

from sentinel.errors import CancelledError, EngineError, ErrorCode
from sentinel.semantic.base import CancelToken

T = TypeVar("T")


class Cancellation:
    def __init__(self) -> None:
        self._event = threading.Event()

    def cancel(self) -> None:
        self._event.set()

    def is_cancelled(self) -> bool:
        return self._event.is_set()

    def raise_if_cancelled(self) -> None:
        if self.is_cancelled():
            raise CancelledError()


class CallToken(Cancellation):
    def __init__(self, parent: CancelToken, timeout: float) -> None:
        super().__init__()
        self.parent, self.deadline = parent, time.monotonic() + timeout

    def is_cancelled(self) -> bool:
        return super().is_cancelled() or self.parent.is_cancelled()

    def raise_if_cancelled(self) -> None:
        super().raise_if_cancelled()
        if time.monotonic() >= self.deadline:
            raise EngineError(ErrorCode.TIMEOUT)


class BoundedCall:
    def __init__(self) -> None:
        self._thread: threading.Thread | None = None
        self._idle = threading.Event()
        self._idle.set()

    @property
    def busy(self) -> bool:
        return not self._idle.is_set()

    def call(self, fn: Callable[[CallToken], T], parent: CancelToken, timeout: float) -> T:
        parent.raise_if_cancelled()
        if self.busy:
            raise EngineError(ErrorCode.TIMEOUT)
        token = CallToken(parent, timeout)
        results: queue.Queue[tuple[T | None, Exception | None]] = queue.Queue(maxsize=1)

        def invoke() -> None:
            try:
                item: tuple[T | None, Exception | None] = (fn(token), None)
            except Exception as exc:
                item = (None, exc)
            finally:
                self._idle.set()
            results.put(item)

        # 卡死调用只占本实例一个槽位；取消/超时不等待 daemon，也不另开线程绕过上限。
        self._thread = threading.Thread(target=invoke, daemon=True)
        self._idle.clear()
        self._thread.start()
        try:
            while True:
                token.raise_if_cancelled()
                try:
                    result, error = results.get(timeout=0.01)
                except queue.Empty:
                    continue
                if error is not None:
                    raise error
                return cast(T, result)
        finally:
            token.cancel()
