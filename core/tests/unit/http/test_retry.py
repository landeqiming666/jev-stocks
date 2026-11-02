import httpx
import pytest
from conftest import FakeClock

from sentinel.errors import SourceError
from sentinel.http import HttpClient


def test_retry_stops_after_three_attempts(clock: FakeClock) -> None:
    calls = []

    def respond(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(503)

    client = HttpClient(
        transport=httpx.MockTransport(respond),
        sleeper=clock.sleep,
        monotonic=clock.monotonic,
        uniform=lambda a, b: a,
    )
    with pytest.raises(SourceError) as exc:
        client.get("https://example.test/a", source="nasdaq")
    assert exc.value.code == "SOURCE_UNAVAILABLE"
    assert len(calls) == 3
    assert clock.sleeps == [0.5, 1.0]


def test_retry_honors_retry_after_and_skips_405(clock: FakeClock) -> None:
    calls = []

    def respond(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(
            405 if request.url.path == "/405" else 429, headers={"Retry-After": "120"}
        )

    client = HttpClient(
        transport=httpx.MockTransport(respond),
        sleeper=clock.sleep,
        monotonic=clock.monotonic,
        uniform=lambda a, b: a,
    )
    with pytest.raises(SourceError) as exc:
        client.get("https://example.test/429", source="nasdaq")
    assert exc.value.params == {"retryAfterSec": 60}
    assert clock.sleeps == [60.0, 60.0]
    with pytest.raises(SourceError) as exc:
        client.get("https://example.test/405", source="nasdaq")
    assert exc.value.reason == "HTTP_405"
    assert len(calls) == 4


@pytest.mark.parametrize("status", [429, 500, 503, 529, 599])
def test_retryable_status_then_success(status: int, clock: FakeClock) -> None:
    calls: list[httpx.Request] = []

    def respond(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(status if len(calls) < 3 else 200, content=b"ok")

    with HttpClient(
        transport=httpx.MockTransport(respond),
        sleeper=clock.sleep,
        monotonic=clock.monotonic,
        uniform=lambda a, b: a,
    ) as client:
        result = client.get("https://example.test/a", source="nasdaq")
    assert result.attempts == 3
    assert result.text == "ok"


@pytest.mark.parametrize("exception", [httpx.ConnectError, httpx.ConnectTimeout, httpx.ReadTimeout])
def test_transport_failures_retry(exception: type[httpx.HTTPError], clock: FakeClock) -> None:
    calls: list[httpx.Request] = []

    def respond(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        raise exception("private server error")

    with (
        HttpClient(
            transport=httpx.MockTransport(respond),
            sleeper=clock.sleep,
            monotonic=clock.monotonic,
            uniform=lambda a, b: a,
        ) as client,
        pytest.raises(SourceError) as exc,
    ):
        client.get("https://example.test/a", source="nasdaq")
    assert len(calls) == 3
    assert exc.value.code == (
        "SOURCE_UNAVAILABLE" if exception is httpx.ConnectError else "TIMEOUT"
    )


def test_retry_after_invalid_and_jitter_boundaries() -> None:
    from sentinel.http.retry import is_retryable, parse_retry_after, retry_delay

    for value in ["Wed, 21 Oct 2015 07:28:00 GMT", "nan", "inf", "-1", "private"]:
        assert parse_retry_after(value) == 0.0
    assert parse_retry_after("120") == 60.0
    assert parse_retry_after("2.5") == 2.5
    assert retry_delay(1, uniform=lambda a, b: a) == 0.5
    assert retry_delay(2, uniform=lambda a, b: b) == 2.0
    assert not is_retryable(405)
    assert not is_retryable(httpx.WriteError("no retry"))


@pytest.mark.parametrize("configured", [False, True])
def test_default_three_and_configured_four_attempts(configured: bool, clock: FakeClock) -> None:
    from sentinel.http import SourcePolicy, register_policy

    policy = SourcePolicy("attempts", max_attempts=4) if configured else SourcePolicy("attempts")
    assert policy.max_attempts == (4 if configured else 3)
    register_policy(policy)
    calls: list[httpx.Request] = []

    def respond(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(503)

    with (
        HttpClient(
            transport=httpx.MockTransport(respond),
            sleeper=clock.sleep,
            monotonic=clock.monotonic,
            uniform=lambda a, b: a,
        ) as client,
        pytest.raises(SourceError),
    ):
        client.get("https://example.test/attempts", source="attempts")
    assert len(calls) == policy.max_attempts
    assert clock.sleeps == ([0.5, 1.0, 2.0] if configured else [0.5, 1.0])


def test_configured_fourth_attempt_can_succeed(clock: FakeClock) -> None:
    from sentinel.http import SourcePolicy, register_policy

    register_policy(SourcePolicy("fourth", max_attempts=4))
    calls: list[httpx.Request] = []

    def respond(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200 if len(calls) == 4 else 503, content=b"ok")

    with HttpClient(
        transport=httpx.MockTransport(respond),
        sleeper=clock.sleep,
        monotonic=clock.monotonic,
        uniform=lambda a, b: a,
    ) as client:
        response = client.get("https://example.test/fourth", source="fourth")
    assert response.attempts == 4 and response.text == "ok"


@pytest.mark.parametrize(
    "header, expected, waits",
    [
        ("2.25", 3, [2.25, 2.25]),
        (None, 0, [0.5, 1.0]),
        ("2", 2, [2.0, 2.0]),
        ("60.25", 60, [60.0, 60.0]),
        ("-0.25", 0, [0.5, 1.0]),
        ("0", 0, [0.5, 1.0]),
    ],
)
def test_429_wire_retry_after_is_integer_while_waits_stay_fractional(
    header: str | None,
    expected: int,
    waits: list[float],
    clock: FakeClock,
) -> None:
    headers = {} if header is None else {"Retry-After": header}
    with (
        HttpClient(
            transport=httpx.MockTransport(lambda request: httpx.Response(429, headers=headers)),
            sleeper=clock.sleep,
            monotonic=clock.monotonic,
            uniform=lambda a, b: a,
        ) as client,
        pytest.raises(SourceError) as exc,
    ):
        client.get("https://example.test/rate-limited", source="nasdaq")
    wire = exc.value.to_wire()
    retry_after = wire["data"]["retryAfterSec"]
    assert type(retry_after) is int and retry_after == expected
    assert clock.sleeps == waits
