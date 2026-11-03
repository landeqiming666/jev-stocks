from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from sentinel.errors import SentinelError
from sentinel.scan.watermark import advance_watermark, compute_window
from tests.unit.scan.test_orchestrator import db as db

NOW = datetime(2026, 11, 3, tzinfo=UTC)


def test_first_scan_uses_configured_lookback() -> None:
    window = compute_window(now=NOW, watermark=None, first_lookback_days=7, explicit_from=None)
    assert window.start == NOW - timedelta(days=7)
    assert window.end == NOW and not window.used_startup_catch_up


def test_stale_watermark_is_capped_to_72_hours() -> None:
    window = compute_window(
        now=NOW, watermark=NOW - timedelta(days=10), first_lookback_days=7, explicit_from=None
    )
    assert window.start == NOW - timedelta(hours=72)
    assert window.used_startup_catch_up


def test_explicit_from_uses_30_day_floor() -> None:
    with pytest.raises(SentinelError) as error:
        compute_window(
            now=NOW,
            watermark=None,
            first_lookback_days=7,
            explicit_from=NOW - timedelta(days=31),
        )
    assert error.value.code == "INVALID_ARGUMENT" and error.value.field == "from"


def test_watermark_never_moves_backward(db: Any) -> None:
    advance_watermark(db, "us", NOW)
    assert advance_watermark(db, "us", NOW - timedelta(days=1)) == NOW


@pytest.mark.parametrize("delta", [-31, 1])
def test_explicit_outside_window_is_rejected(delta: int) -> None:
    with pytest.raises(SentinelError) as error:
        compute_window(
            now=NOW,
            watermark=None,
            first_lookback_days=7,
            explicit_from=NOW + timedelta(days=delta),
        )
    assert error.value.code == "INVALID_ARGUMENT" and error.value.field == "from"


def test_utc_offset_boundary_and_naive_rejection() -> None:
    from datetime import timezone

    requested = NOW.astimezone(timezone(timedelta(hours=8)))
    result = compute_window(now=NOW, watermark=None, first_lookback_days=7, explicit_from=requested)
    assert result.start == result.end == NOW and result.start.tzinfo is UTC
    with pytest.raises(SentinelError, match="INVALID_ARGUMENT"):
        compute_window(
            now=NOW, watermark=None, first_lookback_days=7, explicit_from=NOW.replace(tzinfo=None)
        )
