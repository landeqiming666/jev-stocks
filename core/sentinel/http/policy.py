"""Validated policies and a thread-safe source registry."""

from __future__ import annotations

import logging
import math
import threading
from dataclasses import dataclass

from .telemetry import get_logger, log_event

DEFAULT_MAX_ATTEMPTS = 3
SEC_RATE_PER_S = 5.0
SEC_BURST = 5
MAX_BYTES = 5_242_880


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
        positive = (
            self.connect_timeout_s,
            self.read_timeout_s,
            self.total_timeout_s,
            *self.backoff_s,
        )
        if not self.name or any(not math.isfinite(n) or n <= 0 for n in positive):
            raise ValueError("name and timeouts/backoff must be positive")
        if (
            type(self.max_attempts) is not int
            or not 1 <= self.max_attempts <= 4
            or len(self.backoff_s) < self.max_attempts - 1
        ):
            raise ValueError("max_attempts must be 1..4 with sufficient backoff values")
        if len(self.jitter) != 2 or not 0 < self.jitter[0] <= self.jitter[1] <= 1:
            raise ValueError("jitter must be ordered within (0, 1]")
        if not math.isfinite(self.rate_wait_max_s) or self.rate_wait_max_s < 0:
            raise ValueError("invalid rate wait budget")
        if not isinstance(self.max_bytes, int) or not 0 < self.max_bytes <= MAX_BYTES:
            raise ValueError("max_bytes must be within the 5 MiB cap")
        if self.rate_per_s is not None and (
            not math.isfinite(self.rate_per_s)
            or self.rate_per_s <= 0
            or not isinstance(self.burst, int)
            or self.burst < 1
        ):
            raise ValueError("rate and burst must be positive")


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
