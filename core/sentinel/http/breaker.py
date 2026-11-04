"""Circuit breaker permits isolate concurrent and stale completions."""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal

FAILURE_THRESHOLD = 5
OPEN_SECONDS = 600.0


@dataclass(frozen=True)
class BreakerPermit:
    generation: int
    probe: bool


class CircuitBreaker:
    def __init__(
        self,
        *,
        failure_threshold: int = FAILURE_THRESHOLD,
        open_seconds: float = OPEN_SECONDS,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        if failure_threshold < 1 or open_seconds <= 0:
            raise ValueError("invalid circuit breaker configuration")
        self._threshold = failure_threshold
        self._open_seconds = open_seconds
        self._monotonic = monotonic
        self._lock = threading.Lock()
        self._local = threading.local()
        self._state: Literal["closed", "open", "half_open"] = "closed"
        self._failures = 0
        self._until = 0.0
        self._generation = 0
        self._probe = False

    @property
    def state(self) -> Literal["closed", "open", "half_open"]:
        with self._lock:
            return self._state

    def begin(self) -> BreakerPermit | None:
        with self._lock:
            if self._state == "open":
                if self._monotonic() < self._until:
                    return None
                self._state = "half_open"
            if self._state == "half_open":
                if self._probe:
                    return None
                self._probe = True
            permit = BreakerPermit(self._generation, self._state == "half_open")
            self._local.permit = permit
            return permit

    def allow(self) -> bool:
        return self.begin() is not None

    def allows_retry(self, permit: BreakerPermit) -> bool:
        with self._lock:
            return permit.generation == self._generation and self._state != "open"

    def release(self, permit: BreakerPermit) -> None:
        with self._lock:
            if permit.generation == self._generation and permit.probe:
                self._probe = False

    def record_success(self, *, permit: BreakerPermit | None = None) -> None:
        permit = permit or getattr(self._local, "permit", None)
        with self._lock:
            if permit is not None and permit.generation != self._generation:
                return
            # An unassociated late success must never close an open circuit.
            if self._state == "open":
                return
            self._state = "closed"
            self._failures = 0
            self._probe = False

    def record_failure(
        self,
        *,
        force_open: bool = False,
        permit: BreakerPermit | None = None,
    ) -> bool:
        permit = permit or getattr(self._local, "permit", None)
        with self._lock:
            if not force_open and permit is not None and permit.generation != self._generation:
                return False
            self._failures += 1
            if force_open or self._state == "half_open" or self._failures >= self._threshold:
                self._state = "open"
                self._until = self._monotonic() + self._open_seconds
                self._generation += 1
                self._probe = False
                return True
            return False
