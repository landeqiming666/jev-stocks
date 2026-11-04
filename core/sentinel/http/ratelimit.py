"""Floating-point monotonic token bucket; never sleeps while holding its lock."""

from __future__ import annotations

import math
import threading
import time
from collections.abc import Callable

from sentinel.errors import SourceError


class TokenBucket:
    def __init__(
        self,
        *,
        rate_per_s: float,
        burst: int,
        sleeper: Callable[[float], None] = time.sleep,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        if not math.isfinite(rate_per_s) or rate_per_s <= 0 or burst < 1:
            raise ValueError("rate and burst must be positive")
        self._rate = rate_per_s
        self._burst = burst
        self._tokens = float(burst)
        self._sleeper = sleeper
        self._monotonic = monotonic
        self._updated = monotonic()
        self._lock = threading.Lock()

    def acquire(
        self,
        timeout_s: float,
        *,
        check: Callable[[], None] | None = None,
        waiter: Callable[[float], None] | None = None,
    ) -> None:
        if not math.isfinite(timeout_s) or timeout_s < 0:
            raise ValueError("invalid rate wait budget")
        deadline = self._monotonic() + timeout_s
        while True:
            if check is not None:
                check()
            with self._lock:
                now = self._monotonic()
                self._tokens = min(
                    self._burst, self._tokens + max(0.0, now - self._updated) * self._rate
                )
                self._updated = now
                if now <= deadline and self._tokens >= 1.0 - 1e-12:
                    self._tokens = max(0.0, self._tokens - 1.0)
                    return
                remaining = deadline - now
                if remaining <= 1e-12:
                    raise SourceError("TIMEOUT", reason="RATE_WAIT_TIMEOUT")
                delay = min((1.0 - self._tokens) / self._rate, remaining)
            # The client supplies a cancellable sleeper; standalone use preserves one wait.
            (waiter or self._sleeper)(delay)
