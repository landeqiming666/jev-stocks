from __future__ import annotations

import threading

from sentinel.errors import CancelledError


class CancelToken:
    def __init__(self) -> None:
        self._event = threading.Event()

    def cancel(self) -> None:
        self._event.set()

    @property
    def cancelled(self) -> bool:
        return self._event.is_set()

    def is_cancelled(self) -> bool:
        return self.cancelled

    def raise_if_cancelled(self) -> None:
        if self.cancelled:
            raise CancelledError()


class CancelRegistry:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._entries: dict[str, tuple[CancelToken, bool]] = {}

    def register(self, request_id: str, token: CancelToken, *, cancellable: bool = False) -> None:
        with self._lock:
            if request_id in self._entries:
                raise ValueError("duplicate request id")
            self._entries[request_id] = (token, cancellable)

    def cancel(self, request_id: str) -> bool:
        with self._lock:
            entry = self._entries.get(request_id)
            if entry is None or not entry[1]:
                return False
            entry[0].cancel()
            return True

    def unregister(self, request_id: str) -> None:
        with self._lock:
            self._entries.pop(request_id, None)
