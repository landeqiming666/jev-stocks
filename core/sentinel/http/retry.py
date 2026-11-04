"""Retry classification and bounded numeric Retry-After parsing."""

from __future__ import annotations

import logging
import math
import random
from collections.abc import Callable

import httpx

from .telemetry import get_logger, log_event

BACKOFF_SECONDS = (1.0, 2.0, 4.0)
MAX_RETRY_AFTER_S = 60.0


def is_retryable(value: int | BaseException) -> bool:
    if isinstance(value, int):
        return value == 429 or 500 <= value <= 599
    return isinstance(value, (httpx.ConnectError, httpx.ConnectTimeout, httpx.ReadTimeout))


def parse_retry_after(value: str | None) -> float:
    if value is None:
        return 0.0
    try:
        seconds = float(value)
        if math.isfinite(seconds) and seconds >= 0:
            return min(seconds, MAX_RETRY_AFTER_S)
    except ValueError:
        pass
    log_event(get_logger(__name__), logging.WARNING, event="http.invalid_retry_after")
    return 0.0


def retry_delay(
    retry_number: int,
    *,
    backoff_s: tuple[float, ...] = BACKOFF_SECONDS,
    jitter: tuple[float, float] = (0.5, 1.0),
    retry_after: float = 0.0,
    uniform: Callable[[float, float], float] = random.uniform,
) -> float:
    backoff = backoff_s[retry_number - 1] * uniform(*jitter)
    return min(MAX_RETRY_AFTER_S, max(backoff, retry_after))
