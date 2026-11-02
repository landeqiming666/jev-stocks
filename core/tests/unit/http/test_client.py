from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import httpx
import pytest
from conftest import FakeClock

from sentinel.errors import CancelledError, SourceError
from sentinel.http import HttpClient


@dataclass
class Token:
    cancelled: bool = True

    def is_cancelled(self) -> bool:
        return self.cancelled


def test_client_maps_403_to_sec_forbidden_and_opens_breaker() -> None:
    calls = []
    client = HttpClient(
        transport=httpx.MockTransport(lambda request: calls.append(request) or httpx.Response(403))
    )
    with pytest.raises(SourceError) as exc:
        client.get("https://example.test/a", source="sec")
    assert exc.value.reason == "SEC_FORBIDDEN"
    with pytest.raises(SourceError) as exc:
        client.get("https://example.test/a", source="sec")
    assert exc.value.reason == "CIRCUIT_OPEN"
    assert len(calls) == 1


def test_client_truncates_five_mb_body() -> None:
    client = HttpClient(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(200, content=b"a" * (6 * 1024 * 1024))
        )
    )
    assert len(client.get("https://example.test/a", source="nasdaq").content) == 5_242_880


def test_client_decodes_cp1252_when_header_missing() -> None:
    client = HttpClient(
        transport=httpx.MockTransport(lambda request: httpx.Response(200, content=b"\x93hi\x94"))
    )
    assert client.get_text("https://example.test/a", source="tencent") == "\u201chi\u201d"


def test_client_cancel_and_offline_skip_transport(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = []
    client = HttpClient(
        transport=httpx.MockTransport(lambda request: calls.append(request) or httpx.Response(200))
    )
    with pytest.raises(CancelledError):
        client.get("https://example.test/a", source="sec", cancel=Token())
    monkeypatch.setenv("SENTINEL_OFFLINE", "1")
    with pytest.raises(SourceError) as exc:
        client.get("https://example.test/a", source="sec")
    assert exc.value.reason == "OFFLINE"
    assert calls == []


def test_shared_sources_independent_breakers_and_retry_counts(clock: FakeClock) -> None:
    calls: list[str] = []
    degraded: list[tuple[str, float]] = []

    def respond(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        return httpx.Response(503 if request.url.path == "/bad" else 200, content=b"ok")

    clients = [
        HttpClient(
            transport=httpx.MockTransport(respond),
            sleeper=clock.sleep,
            monotonic=clock.monotonic,
            uniform=lambda a, b: a,
            on_degraded=lambda source, seconds: degraded.append((source, seconds)),
        )
        for _ in range(2)
    ]
    for i in range(5):
        with pytest.raises(SourceError):
            clients[i % 2].get("https://example.test/bad", source="sec")
    assert calls == ["/bad"] * 15
    assert degraded == [("sec", 600.0)]
    with pytest.raises(SourceError) as exc:
        clients[1].get("https://example.test/good", source="sec")
    assert exc.value.reason == "CIRCUIT_OPEN"
    assert clients[0].get_text("https://example.test/good", source="nasdaq") == "ok"
    for client in clients:
        client.close()


def test_shared_sec_bucket_does_not_throttle_other_source(clock: FakeClock) -> None:
    times: list[float] = []
    clients = [
        HttpClient(
            transport=httpx.MockTransport(
                lambda request: times.append(clock.value) or httpx.Response(200, content=b"ok")
            ),
            sleeper=clock.sleep,
            monotonic=clock.monotonic,
        )
        for _ in range(2)
    ]
    for i in range(5):
        clients[i % 2].get("https://example.test/a", source="sec")
    clients[0].get("https://example.test/a", source="nasdaq")
    assert clock.value == 0.0
    clients[1].get("https://example.test/a", source="sec")
    assert times == [0.0] * 6 + [pytest.approx(0.2)]
    for client in clients:
        client.close()


def test_each_retry_acquires_token(clock: FakeClock) -> None:
    from sentinel.http import SourcePolicy, register_policy

    register_policy(SourcePolicy("slow", rate_per_s=1.0, burst=1))
    times: list[float] = []

    def respond(request: httpx.Request) -> httpx.Response:
        times.append(clock.value)
        return httpx.Response(503 if len(times) < 3 else 200)

    with HttpClient(
        transport=httpx.MockTransport(respond),
        monotonic=clock.monotonic,
        sleeper=clock.sleep,
        uniform=lambda a, b: a,
    ) as client:
        result = client.get("https://example.test/a", source="slow")
    assert result.attempts == 3
    assert times == [0.0, 1.0, 2.0]


def test_cancel_during_retry_wait_skips_next_transport(clock: FakeClock) -> None:
    token = Token(False)
    calls: list[httpx.Request] = []

    def sleep(seconds: float) -> None:
        clock.sleep(seconds)
        token.cancelled = True

    with HttpClient(
        transport=httpx.MockTransport(
            lambda request: (
                calls.append(request) or httpx.Response(429, headers={"Retry-After": "60"})
            )
        ),
        monotonic=clock.monotonic,
        sleeper=sleep,
    ) as client:
        with pytest.raises(CancelledError):
            client.get("https://example.test/a", source="sec", cancel=token)
        assert client._source("sec").breaker.state == "closed"
    assert len(calls) == 1
    assert clock.value == 0.05


def test_cancel_during_rate_wait_skips_transport(clock: FakeClock) -> None:
    from sentinel.http import SourcePolicy, register_policy

    register_policy(SourcePolicy("slow", rate_per_s=1.0, burst=1))
    token = Token(False)
    calls: list[httpx.Request] = []

    def sleep(seconds: float) -> None:
        clock.sleep(seconds)
        token.cancelled = True

    with HttpClient(
        transport=httpx.MockTransport(lambda request: calls.append(request) or httpx.Response(200)),
        sleeper=sleep,
        monotonic=clock.monotonic,
    ) as client:
        client.get("https://example.test/a", source="slow")
        with pytest.raises(CancelledError):
            client.get("https://example.test/a", source="slow", cancel=token)
    assert len(calls) == 1


def test_non_sec_403_and_other_4xx_do_not_count_failure(clock: FakeClock) -> None:
    with HttpClient(
        transport=httpx.MockTransport(lambda request: httpx.Response(403)),
        monotonic=clock.monotonic,
        sleeper=clock.sleep,
    ) as client:
        for _ in range(8):
            with pytest.raises(SourceError) as exc:
                client.get("https://example.test/a", source="nasdaq")
            assert exc.value.reason == "HTTP_403"
        assert client._source("nasdaq").breaker.state == "closed"


def test_sec_403_callback_failure_does_not_hide_error() -> None:
    def callback(source: str, seconds: float) -> None:
        raise RuntimeError("private callback body")

    with (
        HttpClient(
            transport=httpx.MockTransport(lambda request: httpx.Response(403)), on_degraded=callback
        ) as client,
        pytest.raises(SourceError) as exc,
    ):
        client.get("https://example.test/a", source="sec")
    assert exc.value.reason == "SEC_FORBIDDEN"


class ChunkStream(httpx.SyncByteStream):
    def __init__(
        self, chunks: list[bytes], *, clock: FakeClock | None = None, advance: float = 0.0
    ) -> None:
        self.chunks = chunks
        self.clock = clock
        self.advance = advance
        self.reads = 0
        self.closed = False

    def __iter__(self) -> Iterator[bytes]:
        for chunk in self.chunks:
            self.reads += 1
            if self.clock is not None:
                self.clock.value += self.advance
            yield chunk

    def close(self) -> None:
        self.closed = True


def test_stream_stops_after_limit_and_does_not_cache_truncated(tmp_path: Path) -> None:
    stream = ChunkStream([b"x" * 1_048_576] * 6 + [b"must not be read"])
    with HttpClient(
        cache_dir=tmp_path,
        transport=httpx.MockTransport(
            lambda request: httpx.Response(200, headers={"ETag": "large"}, stream=stream)
        ),
    ) as client:
        result = client.get("https://example.test/a", source="sec")
    assert len(result.content) == 5_242_880
    assert stream.reads == 6 and stream.closed
    assert not list(tmp_path.rglob("*.meta.json"))


@pytest.mark.parametrize("advance, succeeds", [(29.999, True), (30.0, False), (30.001, False)])
def test_attempt_deadline_includes_chunk_reading(
    advance: float, succeeds: bool, clock: FakeClock
) -> None:
    from sentinel.http import SourcePolicy, register_policy

    register_policy(SourcePolicy("deadline", max_attempts=1))
    stream = ChunkStream([b"ok"], clock=clock, advance=advance)
    with HttpClient(
        transport=httpx.MockTransport(lambda request: httpx.Response(200, stream=stream)),
        monotonic=clock.monotonic,
        sleeper=clock.sleep,
    ) as client:
        if succeeds:
            assert client.get_text("https://example.test/a", source="deadline") == "ok"
        else:
            with pytest.raises(SourceError) as exc:
                client.get("https://example.test/a", source="deadline")
            assert exc.value.code == "TIMEOUT"
    assert stream.closed


def test_attempt_deadline_restarts_after_independent_backoff(clock: FakeClock) -> None:
    calls: list[httpx.Request] = []

    def respond(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200, stream=ChunkStream([b"slow"], clock=clock, advance=30.0))

    with (
        HttpClient(
            transport=httpx.MockTransport(respond),
            monotonic=clock.monotonic,
            sleeper=clock.sleep,
            uniform=lambda a, b: a,
        ) as client,
        pytest.raises(SourceError) as exc,
    ):
        client.get("https://example.test/a", source="nasdaq")
    assert exc.value.code == "TIMEOUT"
    assert len(calls) == 3
    assert clock.value == 91.5


def test_blocked_read_is_bounded_and_late_result_is_discarded(tmp_path: Path) -> None:
    import threading
    import time

    from sentinel.http import SourcePolicy, register_policy

    register_policy(
        SourcePolicy("blocked", max_attempts=1, total_timeout_s=0.04, cache_enabled=True)
    )
    release = threading.Event()
    entered = threading.Event()
    exited = threading.Event()

    class BlockedStream(httpx.SyncByteStream):
        def __iter__(self) -> Iterator[bytes]:
            entered.set()
            assert release.wait(2.0)
            yield b"late response"

        def close(self) -> None:
            exited.set()

    client = HttpClient(
        cache_dir=tmp_path,
        transport=httpx.MockTransport(
            lambda request: httpx.Response(200, stream=BlockedStream(), headers={"ETag": "late"})
        ),
    )
    started = time.monotonic()
    try:
        with pytest.raises(SourceError) as exc:
            client.get("https://example.test/a", source="blocked")
        assert entered.is_set()
        assert exc.value.code == "TIMEOUT"
        assert time.monotonic() - started < 0.5
    finally:
        release.set()
        assert exited.wait(2.0)
        client.close()
    assert not list(tmp_path.rglob("*.meta.json"))


def test_inflight_cancel_returns_before_blocked_transport_finishes() -> None:
    import threading
    from concurrent.futures import ThreadPoolExecutor

    token = Token(False)
    release = threading.Event()
    entered = threading.Event()
    exited = threading.Event()

    def respond(request: httpx.Request) -> httpx.Response:
        entered.set()
        assert release.wait(2.0)
        exited.set()
        return httpx.Response(200, content=b"late")

    client = HttpClient(transport=httpx.MockTransport(respond))
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(client.get, "https://example.test/a", source="nasdaq", cancel=token)
        try:
            assert entered.wait(2.0)
            token.cancelled = True
            with pytest.raises(CancelledError):
                future.result(timeout=0.5)
        finally:
            release.set()
            assert exited.wait(2.0)
    client.close()


def test_json_headers_charset_and_invalid_payloads() -> None:
    from sentinel.http import CancelToken

    token: CancelToken = Token(False)

    def respond(request: httpx.Request) -> httpx.Response:
        assert request.headers["x-test"] == "one"
        if request.url.path == "/json":
            return httpx.Response(200, content=b'{"value": 2}')
        if request.url.path == "/bad-charset":
            return httpx.Response(
                200, headers={"Content-Type": "text/plain; charset=no-such-codec"}, content=b"text"
            )
        return httpx.Response(200, content=b"not-json")

    with HttpClient(transport=httpx.MockTransport(respond)) as client:
        assert client.get_json(
            "https://example.test/json",
            source="nasdaq",
            headers={"X-Test": "one"},
            cancel=token,
            use_cache=False,
        ) == {"value": 2}
        with pytest.raises(SourceError) as exc:
            client.get_json(
                "https://example.test/invalid", source="nasdaq", headers={"X-Test": "one"}
            )
        assert exc.value.reason == "INVALID_JSON"
        with pytest.raises(SourceError) as exc:
            client.get(
                "https://example.test/bad-charset", source="nasdaq", headers={"X-Test": "one"}
            )
        assert exc.value.reason == "DECODE_FAILED"


def test_registered_override_and_unknown_source_warn_once(
    clock: FakeClock, caplog: pytest.LogCaptureFixture
) -> None:
    from sentinel.http import SourcePolicy, register_policy

    timeouts: list[object] = []
    with HttpClient(
        transport=httpx.MockTransport(
            lambda request: timeouts.append(request.extensions["timeout"]) or httpx.Response(200)
        ),
        monotonic=clock.monotonic,
        sleeper=clock.sleep,
    ) as client:
        client.get("https://example.test/a", source="tencent")
        register_policy(SourcePolicy("tencent", read_timeout_s=30.0))
        client.get("https://example.test/a", source="tencent")
        client.get("https://example.test/a", source="new")
        client.get("https://example.test/a", source="new")
    assert timeouts[0] == {"connect": 5.0, "read": 20.0, "write": 30.0, "pool": 30.0}
    assert timeouts[1] == {"connect": 5.0, "read": 30.0, "write": 30.0, "pool": 30.0}
    assert sum(record.getMessage() == "http.unknown_source" for record in caplog.records) == 1


def test_logs_remove_sensitive_query_and_never_include_body(
    caplog: pytest.LogCaptureFixture,
) -> None:
    import json
    import logging

    from sentinel.logging_setup import JsonFormatter

    caplog.set_level(logging.INFO, logger="sentinel")
    url = "https://user:password@example.test/a?TOKEN=private-token&key=private-key&apikey=private-api&x=ok"
    with HttpClient(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(200, content=b"private response body")
        )
    ) as client:
        client.get(url, source="nasdaq")
    entries = [
        json.loads(JsonFormatter().format(record))
        for record in caplog.records
        if record.getMessage() == "http.get"
    ]
    assert len(entries) == 1
    log = json.dumps(entries)
    for secret in [
        "private-token",
        "private-key",
        "private-api",
        "password",
        "private response body",
    ]:
        assert secret not in log
    assert entries[0]["url"] == "https://example.test/a?x=ok"
    assert {
        "ts",
        "level",
        "module",
        "request_id",
        "method",
        "duration_ms",
        "error_code",
        "source",
        "url",
        "status",
        "attempts",
        "from_cache",
    } <= entries[0].keys()


def test_half_open_client_has_one_probe_across_retries(clock: FakeClock) -> None:
    import threading
    from concurrent.futures import ThreadPoolExecutor

    from sentinel.http import SourcePolicy, register_policy

    register_policy(SourcePolicy("probe"))
    entered = threading.Event()
    release = threading.Event()
    calls: list[httpx.Request] = []

    def respond(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        if len(calls) == 1:
            entered.set()
            assert release.wait(2.0)
            return httpx.Response(503)
        return httpx.Response(200, content=b"probe success")

    with HttpClient(
        transport=httpx.MockTransport(respond),
        sleeper=clock.sleep,
        monotonic=clock.monotonic,
        uniform=lambda a, b: a,
    ) as client:
        client._source("probe").breaker.record_failure(force_open=True)
        clock.value = 600.0
        with ThreadPoolExecutor(max_workers=1) as pool:
            pending = pool.submit(client.get, "https://example.test/a", source="probe")
            try:
                assert entered.wait(2.0)
                with pytest.raises(SourceError) as exc:
                    client.get("https://example.test/a", source="probe")
                assert exc.value.reason == "CIRCUIT_OPEN"
            finally:
                release.set()
            result = pending.result(timeout=2.0)
        assert result.attempts == 2
        assert len(calls) == 2
        assert client._source("probe").breaker.state == "closed"


def test_late_sec_success_does_not_close_forced_circuit(clock: FakeClock) -> None:
    import threading
    from concurrent.futures import ThreadPoolExecutor

    entered = threading.Event()
    release = threading.Event()

    def respond(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/slow":
            entered.set()
            assert release.wait(2.0)
            return httpx.Response(200, content=b"late")
        return httpx.Response(403)

    with HttpClient(
        transport=httpx.MockTransport(respond), sleeper=clock.sleep, monotonic=clock.monotonic
    ) as client:
        with ThreadPoolExecutor(max_workers=1) as pool:
            pending = pool.submit(client.get, "https://example.test/slow", source="sec")
            try:
                assert entered.wait(2.0)
                with pytest.raises(SourceError) as exc:
                    client.get("https://example.test/forbidden", source="sec")
                assert exc.value.reason == "SEC_FORBIDDEN"
            finally:
                release.set()
            assert pending.result(timeout=2.0).content == b"late"
        assert client._source("sec").breaker.state == "open"


def test_offline_between_retries_stops_next_attempt(
    clock: FakeClock, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[httpx.Request] = []

    def sleep(seconds: float) -> None:
        clock.sleep(seconds)
        monkeypatch.setenv("SENTINEL_OFFLINE", "1")

    with HttpClient(
        transport=httpx.MockTransport(lambda request: calls.append(request) or httpx.Response(503)),
        sleeper=sleep,
        monotonic=clock.monotonic,
    ) as client:
        with pytest.raises(SourceError) as exc:
            client.get("https://example.test/a", source="sec")
        assert exc.value.reason == "OFFLINE"
    assert len(calls) == 1


def test_retry_after_60_is_independent_of_attempt_budget(clock: FakeClock) -> None:
    calls: list[httpx.Request] = []

    def respond(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return (
            httpx.Response(429, headers={"Retry-After": "60"})
            if len(calls) == 1
            else httpx.Response(200)
        )

    with HttpClient(
        transport=httpx.MockTransport(respond), sleeper=clock.sleep, monotonic=clock.monotonic
    ) as client:
        result = client.get("https://example.test/a", source="nasdaq")
    assert result.attempts == 2 and result.elapsed_ms == 60_000


@pytest.mark.parametrize(
    "options",
    [
        {"max_attempts": 0},
        {"max_attempts": 5},
        {"max_attempts": 1.5},
        {"read_timeout_s": float("nan")},
        {"rate_per_s": 0.0, "burst": 1},
        {"rate_per_s": 5.0, "burst": 0},
        {"max_bytes": 5_242_881},
        {"jitter": (1.0, 0.5)},
        {"rate_wait_max_s": -1.0},
    ],
)
def test_policy_rejects_out_of_bounds_values(options: dict[str, object]) -> None:
    from sentinel.http import SourcePolicy

    with pytest.raises(ValueError):
        SourcePolicy("invalid", **options)


@pytest.mark.parametrize(
    "charset, body, expected",
    [
        (None, b"\x81", None),
        ("utf-8", b"\xff", None),
        ("utf-8", b"a\xe2\x82\xacmore", "a"),
    ],
)
def test_decode_failure_and_truncated_character_boundaries(
    charset: str | None, body: bytes, expected: str | None, clock: FakeClock
) -> None:
    from sentinel.http import SourcePolicy, register_policy

    register_policy(SourcePolicy("encoding", max_bytes=3))
    headers = {} if charset is None else {"Content-Type": f"text/plain; charset={charset}"}
    with HttpClient(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(200, headers=headers, content=body)
        ),
        sleeper=clock.sleep,
        monotonic=clock.monotonic,
    ) as client:
        if expected is None:
            with pytest.raises(SourceError) as exc:
                client.get("https://example.test/a", source="encoding")
            assert exc.value.reason == "DECODE_FAILED"
        else:
            result = client.get("https://example.test/a", source="encoding")
            assert result.text == expected and len(result.content) == 3


def test_half_open_http_failure_reopens_for_ten_minutes(clock: FakeClock) -> None:
    with HttpClient(
        transport=httpx.MockTransport(lambda request: httpx.Response(405)),
        sleeper=clock.sleep,
        monotonic=clock.monotonic,
    ) as client:
        breaker = client._source("nasdaq").breaker
        breaker.record_failure(force_open=True)
        clock.value = 600.0
        with pytest.raises(SourceError) as exc:
            client.get("https://example.test/a", source="nasdaq")
        assert exc.value.reason == "HTTP_405"
        assert breaker.state == "open"
        clock.value = 1199.999
        assert not breaker.allow()
        clock.value = 1200.0
        assert breaker.allow()


def test_transport_library_does_not_log_raw_secret_urls(
    caplog: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    import logging

    caplog.set_level(logging.INFO)
    monkeypatch.setattr(logging.getLogger("httpx"), "level", logging.INFO)
    with HttpClient(transport=httpx.MockTransport(lambda request: httpx.Response(200))) as client:
        client.get("https://example.test/a?token=private-transport-secret", source="nasdaq")
    assert "private-transport-secret" not in caplog.text


@pytest.mark.parametrize(
    "value", [True, False, -1, 0, 5, 1.5, 3.0, float("nan"), float("inf"), "3", None]
)
def test_max_attempts_rejects_non_integer_or_out_of_range(value: object) -> None:
    from sentinel.http import SourcePolicy

    with pytest.raises(ValueError):
        SourcePolicy("invalid", max_attempts=value)


@pytest.mark.parametrize("reuse_cached", [False, True])
@pytest.mark.parametrize(
    "body",
    [
        b'{"value": NaN}',
        b'{"value": Infinity}',
        b'{"value": -Infinity}',
        b'{"broken":',
        b"[" * 10000 + b"0" + b"]" * 10000,
    ],
)
def test_invalid_json_discards_cache_and_refetches(
    body: bytes, reuse_cached: bool, tmp_path: Path, clock: FakeClock
) -> None:
    calls: list[httpx.Request] = []

    def respond(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        if len(calls) == 1:
            return httpx.Response(200, headers={"ETag": "invalid"}, content=body)
        if reuse_cached and len(calls) == 2:
            assert request.headers["if-none-match"] == "invalid"
            return httpx.Response(304)
        assert "if-none-match" not in request.headers
        return httpx.Response(200, headers={"ETag": "valid"}, content=b'{"value": 2}')

    with HttpClient(
        cache_dir=tmp_path,
        transport=httpx.MockTransport(respond),
        sleeper=clock.sleep,
        monotonic=clock.monotonic,
    ) as client:
        url = "https://example.test/json"
        if reuse_cached:
            client.get_text(url, source="sec")
        with pytest.raises(SourceError) as exc:
            client.get_json(url, source="sec")
        assert exc.value.code == "SOURCE_UNAVAILABLE" and exc.value.reason == "INVALID_JSON"
        assert not list((tmp_path / "http").glob("*.meta.json"))
        assert not list((tmp_path / "http").glob("*.body"))
        assert client.get_json(url, source="sec") == {"value": 2}
    assert len(calls) == (3 if reuse_cached else 2)


def test_json_constant_names_in_strings_are_valid() -> None:
    with HttpClient(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(
                200, content=b'[true, false, null, {"literal": "NaN Infinity -Infinity"}]'
            )
        )
    ) as client:
        assert client.get_json("https://example.test/json", source="nasdaq") == [
            True,
            False,
            None,
            {"literal": "NaN Infinity -Infinity"},
        ]
