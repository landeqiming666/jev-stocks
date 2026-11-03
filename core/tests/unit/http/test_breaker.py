from sentinel.http.breaker import CircuitBreaker
from tests.unit.http.conftest import FakeClock


def test_breaker_opens_after_five_failures(clock: FakeClock) -> None:
    breaker = CircuitBreaker(monotonic=clock.monotonic)
    for _ in range(5):
        breaker.record_failure()
    assert breaker.state == "open"
    assert breaker.allow() is False


def test_breaker_half_open_then_closes(clock: FakeClock) -> None:
    breaker = CircuitBreaker(monotonic=clock.monotonic)
    for _ in range(5):
        breaker.record_failure()
    clock.value = 601.0
    assert breaker.allow() is True
    assert breaker.state == "half_open"
    assert breaker.allow() is False
    breaker.record_success()
    assert breaker.state == "closed"


def test_half_open_concurrency_and_failure_reopens(clock: FakeClock) -> None:
    from concurrent.futures import ThreadPoolExecutor

    breaker = CircuitBreaker(monotonic=clock.monotonic)
    breaker.record_failure(force_open=True)
    clock.value = 600.0
    with ThreadPoolExecutor(max_workers=12) as pool:
        permits = list(pool.map(lambda _: breaker.begin(), range(24)))
    probes = [permit for permit in permits if permit is not None]
    assert len(probes) == 1
    breaker.record_failure(permit=probes[0])
    assert breaker.state == "open"
    clock.value = 1199.999
    assert not breaker.allow()
    clock.value = 1200.0
    assert breaker.allow()


def test_stale_success_cannot_close_forced_open(clock: FakeClock) -> None:
    breaker = CircuitBreaker(monotonic=clock.monotonic)
    permit = breaker.begin()
    assert permit is not None
    breaker.record_failure(force_open=True)
    breaker.record_success(permit=permit)
    assert breaker.state == "open"
    assert not breaker.allow()


def test_cancelled_probe_can_be_replaced(clock: FakeClock) -> None:
    breaker = CircuitBreaker(monotonic=clock.monotonic)
    breaker.record_failure(force_open=True)
    clock.value = 600.0
    permit = breaker.begin()
    assert permit is not None
    breaker.release(permit)
    assert breaker.allow()
