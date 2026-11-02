"""Validated policies and a thread-safe source registry."""

from __future__ import annotations

import logging
import math
import threading
from collections.abc import Sequence
from dataclasses import dataclass
from numbers import Real

from .telemetry import get_logger, log_event

DEFAULT_MAX_ATTEMPTS = 3
SEC_RATE_PER_S = 5.0
SEC_BURST = 5
MAX_BYTES = 5_242_880


def _finite_number(value: object) -> bool:
    if isinstance(value, bool) or not isinstance(value, Real):
        return False
    try:
        return math.isfinite(float(value))
    except (OverflowError, TypeError, ValueError):
        return False


@dataclass(frozen=True)
class SourcePolicy:
    name: str
    connect_timeout_s: float = 5.0
    read_timeout_s: float = 20.0
    total_timeout_s: float = 30.0
    max_attempts: int = DEFAULT_MAX_ATTEMPTS
    backoff_s: tuple[float, ...] = (1.0, 2.0, 4.0)
    jitter: tuple[float, float] = (0.5, 1.0)
    rate_per_s: float | None = None
    burst: int = 0
    rate_wait_max_s: float = 30.0
    cache_enabled: bool = False
    max_bytes: int = MAX_BYTES

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not self.name:
            raise ValueError("name must be a nonempty string")
        if not isinstance(self.cache_enabled, bool):
            raise ValueError("cache_enabled must be bool")
        if not isinstance(self.backoff_s, Sequence):
            raise ValueError("backoff must be a sequence of positive numbers")
        positive = (
            self.connect_timeout_s,
            self.read_timeout_s,
            self.total_timeout_s,
            *self.backoff_s,
        )
        if any(not _finite_number(n) or n <= 0 for n in positive):
            raise ValueError("timeouts/backoff must be finite positive numbers")
        if (
            type(self.max_attempts) is not int
            or not 1 <= self.max_attempts <= 4
            or len(self.backoff_s) < self.max_attempts - 1
        ):
            raise ValueError("max_attempts must be 1..4 with sufficient backoff values")
        if (
            not isinstance(self.jitter, Sequence)
            or len(self.jitter) != 2
            or any(not _finite_number(n) for n in self.jitter)
            or not 0 < self.jitter[0] <= self.jitter[1] <= 1
        ):
            raise ValueError("jitter must be ordered within (0, 1]")
        if not _finite_number(self.rate_wait_max_s) or self.rate_wait_max_s < 0:
            raise ValueError("invalid rate wait budget")
        if type(self.max_bytes) is not int or not 0 < self.max_bytes <= MAX_BYTES:
            raise ValueError("max_bytes must be within the 5 MiB cap")
        if type(self.burst) is not int or not _finite_number(self.burst) or self.burst < 0:
            raise ValueError("burst must be a nonnegative int")
        if self.rate_per_s is not None and (
            not _finite_number(self.rate_per_s) or self.rate_per_s <= 0 or self.burst < 1
        ):
            raise ValueError("rate and burst must be positive")
        object.__setattr__(self, "backoff_s", tuple(self.backoff_s))
        object.__setattr__(self, "jitter", tuple(self.jitter))


POLICIES: dict[str, SourcePolicy] = {
    "sec": SourcePolicy("sec", rate_per_s=SEC_RATE_PER_S, burst=SEC_BURST, cache_enabled=True),
    "tencent": SourcePolicy("tencent"),
    "nasdaq": SourcePolicy("nasdaq"),
}
_registry_lock = threading.Lock()
_warned: set[str] = set()


def register_policy(policy: SourcePolicy) -> None:
    with _registry_lock:
        POLICIES[policy.name] = policy


def get_policy(name: str) -> SourcePolicy:
    with _registry_lock:
        policy = POLICIES.get(name)
        warn = policy is None and name not in _warned
        if warn:
            _warned.add(name)
    if warn:
        log_event(get_logger(__name__), logging.WARNING, event="http.unknown_source", source=name)
    return policy if policy is not None else SourcePolicy(name)
