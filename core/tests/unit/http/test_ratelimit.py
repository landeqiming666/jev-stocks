import pytest
from conftest import FakeClock

from sentinel.errors import SourceError
from sentinel.http.ratelimit import TokenBucket


def test_token_bucket_limits_and_times_out(clock: FakeClock) -> None:
    bucket = TokenBucket(rate_per_s=1.0, burst=5, sleeper=clock.sleep, monotonic=clock.monotonic)
    for _ in range(5):
        bucket.acquire(0.0)
    bucket.acquire(2.0)
    assert clock.sleeps == [1.0]
    with pytest.raises(SourceError) as exc:
        bucket.acquire(0.1)
    assert exc.value.code == "TIMEOUT"


def test_fractional_refill_exact_deadline(clock: FakeClock) -> None:
    bucket = TokenBucket(rate_per_s=5.0, burst=1, sleeper=clock.sleep, monotonic=clock.monotonic)
    bucket.acquire(0.0)
    clock.value = 0.125
    bucket.acquire(0.075)
    assert clock.value == pytest.approx(0.2)
    assert clock.sleeps == [pytest.approx(0.075)]
    with pytest.raises(SourceError):
        bucket.acquire(0.199)


def test_concurrent_acquire_never_exceeds_burst(clock: FakeClock) -> None:
    from concurrent.futures import ThreadPoolExecutor

    bucket = TokenBucket(rate_per_s=5.0, burst=5, monotonic=clock.monotonic, sleeper=clock.sleep)

    def acquire(_: int) -> bool:
        try:
            bucket.acquire(0.0)
            return True
        except SourceError:
            return False

    with ThreadPoolExecutor(max_workers=12) as pool:
        assert sum(pool.map(acquire, range(50))) == 5
