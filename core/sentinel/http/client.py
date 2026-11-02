"""Synchronous source HTTP facade with isolated attempt state and cancellable waits."""

from __future__ import annotations

import codecs
import hashlib
import json
import logging
import os
import random
import threading
import time
from collections.abc import Callable, Mapping
from concurrent.futures import Future
from dataclasses import dataclass
from email.message import Message
from pathlib import Path
from types import MappingProxyType
from typing import Protocol
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import httpx

from sentinel.errors import CancelledError, SourceError

from .breaker import OPEN_SECONDS, BreakerPermit, CircuitBreaker
from .cache import HttpCache
from .policy import SourcePolicy, get_policy
from .ratelimit import TokenBucket
from .retry import is_retryable, parse_retry_after, retry_delay
from .telemetry import get_logger, log_event


class CancelToken(Protocol):
    def is_cancelled(self) -> bool: ...


@dataclass(frozen=True)
class HttpResponse:
    status: int
    headers: Mapping[str, str]
    content: bytes
    text: str
    from_cache: bool
    attempts: int
    elapsed_ms: int


@dataclass
class _SourceState:
    policy: SourcePolicy
    breaker: CircuitBreaker
    bucket: TokenBucket | None


@dataclass(frozen=True)
class _Received:
    status: int
    headers: Mapping[str, str]
    content: bytes
    truncated: bool


_shared_sources: dict[tuple[tuple[int, int], str], _SourceState] = {}
_sources_lock = threading.Lock()


def _clock_key(function: Callable[..., object]) -> tuple[int, int]:
    return (id(getattr(function, "__self__", None)), id(getattr(function, "__func__", function)))


def _safe_url(url: str) -> str:
    parts = urlsplit(url)
    query = [
        (key, value)
        for key, value in parse_qsl(parts.query, keep_blank_values=True)
        if key.lower() not in {"token", "key", "apikey", "api_key", "access_token"}
    ]
    # Credentials and fragments must not reach logs either.
    netloc = parts.netloc.rsplit("@", 1)[-1]
    return urlunsplit((parts.scheme, netloc, parts.path, urlencode(query), ""))


def _decode(content: bytes, headers: Mapping[str, str], truncated: bool) -> str:
    message = Message()
    message["content-type"] = headers.get("content-type", "")
    charset = message.get_content_charset()
    encodings = (charset,) if charset else ("utf-8", "cp1252")
    for encoding in encodings:
        try:
            decoder = codecs.getincrementaldecoder(encoding)(errors="strict")
            return decoder.decode(content, final=not truncated)
        except (LookupError, UnicodeError):
            pass
    raise SourceError("SOURCE_UNAVAILABLE", reason="DECODE_FAILED")


class HttpClient:
    def __init__(
        self,
        *,
        cache_dir: Path | None = None,
        transport: httpx.BaseTransport | None = None,
        on_degraded: Callable[[str, float], None] | None = None,
        sleeper: Callable[[float], None] = time.sleep,
        monotonic: Callable[[], float] = time.monotonic,
        uniform: Callable[[float, float], float] = random.uniform,
    ) -> None:
        # Third-party request/trace logs contain raw URLs and headers.
        for name in ("httpx", "httpcore"):
            logging.getLogger(name).setLevel(logging.WARNING)
        self._client = httpx.Client(transport=transport, follow_redirects=False)
        self._cache = HttpCache(cache_dir) if cache_dir is not None else None
        self._on_degraded = on_degraded
        self._sleeper = sleeper
        self._monotonic = monotonic
        self._uniform = uniform
        self._logger = get_logger(__name__)

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> HttpClient:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    def _source(self, source: str) -> _SourceState:
        policy = get_policy(source)
        key = (_clock_key(self._monotonic), source)
        with _sources_lock:
            state = _shared_sources.get(key)
            if state is None or state.policy != policy:
                bucket = state.bucket if state is not None else None
                rate_changed = state is None or (state.policy.rate_per_s, state.policy.burst) != (
                    policy.rate_per_s,
                    policy.burst,
                )
                if rate_changed:
                    bucket = None
                if rate_changed and policy.rate_per_s is not None:
                    bucket = TokenBucket(
                        rate_per_s=policy.rate_per_s,
                        burst=policy.burst,
                        sleeper=self._sleeper,
                        monotonic=self._monotonic,
                    )
                breaker = (
                    state.breaker
                    if state is not None
                    else CircuitBreaker(monotonic=self._monotonic)
                )
                state = _SourceState(policy, breaker, bucket)
                _shared_sources[key] = state
            return state

    @staticmethod
    def _check(cancel: CancelToken | None) -> None:
        if cancel is not None and cancel.is_cancelled():
            raise CancelledError()
        if os.environ.get("SENTINEL_OFFLINE") == "1":
            raise SourceError("SOURCE_UNAVAILABLE", reason="OFFLINE")

    def _wait(self, seconds: float, cancel: CancelToken | None) -> None:
        deadline = self._monotonic() + seconds
        while True:
            self._check(cancel)
            remaining = deadline - self._monotonic()
            if remaining <= 1e-12:
                return
            self._sleeper(min(remaining, 0.05) if cancel is not None else remaining)

    def _failure(
        self, source: str, state: _SourceState, permit: BreakerPermit, *, force: bool = False
    ) -> None:
        if state.breaker.record_failure(force_open=force, permit=permit):
            log_event(
                self._logger,
                logging.WARNING,
                event="source.degraded",
                source=source,
                open_seconds=OPEN_SECONDS,
            )
            if self._on_degraded is not None:
                try:
                    self._on_degraded(source, OPEN_SECONDS)
                except Exception:
                    log_event(
                        self._logger,
                        logging.WARNING,
                        event="http.degraded_callback_failed",
                        source=source,
                    )

    def _receive(
        self,
        url: str,
        headers: Mapping[str, str],
        policy: SourcePolicy,
        cancel: CancelToken | None,
    ) -> _Received:
        deadline = self._monotonic() + policy.total_timeout_s
        stopped = threading.Event()
        done = threading.Event()
        result: Future[_Received] = Future()

        def check_deadline() -> None:
            self._check(cancel)
            if stopped.is_set() or self._monotonic() >= deadline:
                raise httpx.ReadTimeout("attempt deadline exceeded")

        def receive() -> None:
            try:
                check_deadline()
                timeout = httpx.Timeout(
                    policy.total_timeout_s,
                    connect=min(policy.connect_timeout_s, policy.total_timeout_s),
                    read=min(policy.read_timeout_s, policy.total_timeout_s),
                )
                with self._client.stream("GET", url, headers=headers, timeout=timeout) as response:
                    check_deadline()
                    body = bytearray()
                    truncated = False
                    # Error/304 bodies are unnecessary; reading them would delay classification.
                    if 200 <= response.status_code < 300:
                        iterator = response.iter_bytes()
                        while True:
                            check_deadline()
                            try:
                                chunk = next(iterator)
                            except StopIteration:
                                check_deadline()
                                break
                            check_deadline()
                            remaining = policy.max_bytes - len(body)
                            body.extend(chunk[:remaining])
                            if len(chunk) > remaining:
                                truncated = True
                                break
                    received = _Received(
                        response.status_code,
                        MappingProxyType(dict(response.headers)),
                        bytes(body),
                        truncated,
                    )
                check_deadline()
                result.set_result(received)
            except BaseException as exc:
                result.set_exception(exc)
            finally:
                done.set()

        # httpx per-read timeouts alone cannot bound a stream that keeps producing chunks.
        # Only this worker touches the response; expired results never update cache or breaker.
        threading.Thread(target=receive, name="sentinel-http-attempt", daemon=True).start()
        try:
            while not done.is_set():
                check_deadline()
                done.wait(min(0.05, max(0.0, deadline - self._monotonic())))
            check_deadline()
            return result.result()
        finally:
            stopped.set()

    def get(
        self,
        url: str,
        *,
        source: str,
        headers: Mapping[str, str] | None = None,
        cancel: CancelToken | None = None,
        use_cache: bool | None = None,
    ) -> HttpResponse:
        started = self._monotonic()
        attempts = 0
        status: int | None = None
        from_cache = False
        error_code: str | None = None
        permit = None
        state = None
        try:
            self._check(cancel)
            state = self._source(source)
            policy = state.policy
            permit = state.breaker.begin()
            if permit is None:
                raise SourceError("SOURCE_UNAVAILABLE", reason="CIRCUIT_OPEN")
            cache = (
                self._cache if (policy.cache_enabled if use_cache is None else use_cache) else None
            )
            request_headers = {key.lower(): value for key, value in (headers or {}).items()}
            context = hashlib.sha256(
                json.dumps([source, sorted(request_headers.items())]).encode()
            ).hexdigest()
            entry = cache.load(url, context=context, max_bytes=policy.max_bytes) if cache else None
            last_error = SourceError("SOURCE_UNAVAILABLE", reason="HTTP_304")
            for attempt in range(1, policy.max_attempts + 1):
                self._check(cancel)
                if not state.breaker.allows_retry(permit):
                    raise SourceError("SOURCE_UNAVAILABLE", reason="CIRCUIT_OPEN")
                if state.bucket is not None:
                    state.bucket.acquire(
                        policy.rate_wait_max_s,
                        check=lambda: self._check(cancel),
                        waiter=lambda delay: self._wait(delay, cancel),
                    )
                self._check(cancel)
                if not state.breaker.allows_retry(permit):
                    raise SourceError("SOURCE_UNAVAILABLE", reason="CIRCUIT_OPEN")
                outgoing = dict(request_headers)
                if entry is not None:
                    outgoing.pop("if-none-match", None)
                    outgoing.pop("if-modified-since", None)
                    if entry.etag:
                        outgoing["if-none-match"] = entry.etag
                    if entry.last_modified:
                        outgoing["if-modified-since"] = entry.last_modified
                attempts = attempt
                status = None
                retry_after = 0.0
                try:
                    received = self._receive(url, outgoing, policy, cancel)
                except httpx.HTTPError as exc:
                    last_error = SourceError(
                        "TIMEOUT"
                        if isinstance(exc, httpx.TimeoutException)
                        else "SOURCE_UNAVAILABLE"
                    )
                    if not is_retryable(exc):
                        self._failure(source, state, permit)
                        raise last_error from None
                else:
                    status = received.status
                    if status == 304:
                        if entry is None:
                            # Never accept an orphan 304 or retry with caller-supplied validators.
                            request_headers.pop("if-none-match", None)
                            request_headers.pop("if-modified-since", None)
                            continue
                        merged = {**entry.headers, **received.headers}
                        merged["content-length"] = str(len(entry.content))
                        received = _Received(304, MappingProxyType(merged), entry.content, False)
                        from_cache = True
                    if 200 <= status < 300 or from_cache:
                        try:
                            text = _decode(received.content, received.headers, received.truncated)
                        except SourceError:
                            self._failure(source, state, permit)
                            raise
                        self._check(cancel)
                        if received.truncated:
                            log_event(
                                self._logger,
                                logging.WARNING,
                                event="http.body_truncated",
                                source=source,
                                max_bytes=policy.max_bytes,
                            )
                        if cache is not None:
                            try:
                                if received.truncated:
                                    cache.discard(url)
                                elif from_cache and entry is not None:
                                    cache.revalidate(url, entry, received.headers, context=context)
                                else:
                                    cache.store(
                                        url, received.content, received.headers, context=context
                                    )
                            except OSError:
                                log_event(
                                    self._logger,
                                    logging.WARNING,
                                    event="http.cache_write_failed",
                                    source=source,
                                )
                        state.breaker.record_success(permit=permit)
                        return HttpResponse(
                            status,
                            received.headers,
                            received.content,
                            text,
                            from_cache,
                            attempts,
                            int((self._monotonic() - started) * 1000),
                        )
                    if status == 403 and source == "sec":
                        self._failure(source, state, permit, force=True)
                        raise SourceError("SOURCE_UNAVAILABLE", reason="SEC_FORBIDDEN")
                    retry_after = parse_retry_after(received.headers.get("retry-after"))
                    last_error = (
                        SourceError("RATE_LIMITED", params={"retryAfterSec": retry_after})
                        if status == 429
                        else SourceError("SOURCE_UNAVAILABLE", reason=f"HTTP_{status}")
                    )
                    if not is_retryable(status):
                        if permit.probe:
                            self._failure(source, state, permit)
                        raise last_error
                if attempt < policy.max_attempts:
                    self._wait(
                        retry_delay(
                            attempt,
                            backoff_s=policy.backoff_s,
                            jitter=policy.jitter,
                            retry_after=retry_after,
                            uniform=self._uniform,
                        ),
                        cancel,
                    )
            self._failure(source, state, permit)
            raise last_error
        except (SourceError, CancelledError) as exc:
            error_code = exc.code.value
            raise
        finally:
            if state is not None and permit is not None:
                state.breaker.release(permit)
            log_event(
                self._logger,
                logging.INFO,
                event="http.get",
                method="GET",
                source=source,
                url=_safe_url(url),
                status=status,
                attempts=attempts,
                from_cache=from_cache,
                duration_ms=int((self._monotonic() - started) * 1000),
                error_code=error_code,
            )

    def get_text(
        self,
        url: str,
        *,
        source: str,
        headers: Mapping[str, str] | None = None,
        cancel: CancelToken | None = None,
        use_cache: bool | None = None,
    ) -> str:
        return self.get(
            url, source=source, headers=headers, cancel=cancel, use_cache=use_cache
        ).text

    def get_json(
        self,
        url: str,
        *,
        source: str,
        headers: Mapping[str, str] | None = None,
        cancel: CancelToken | None = None,
        use_cache: bool | None = None,
    ) -> object:
        text = self.get_text(
            url, source=source, headers=headers, cancel=cancel, use_cache=use_cache
        )
        try:
            return json.loads(text)
        except ValueError:
            raise SourceError("SOURCE_UNAVAILABLE", reason="INVALID_JSON") from None
