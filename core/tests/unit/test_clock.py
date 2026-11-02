"""UTC 时钟与 ISO 8601 转换的单元测试。"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone

import pytest

from sentinel.clock import now, parse_iso, to_iso, utc_today


def test_now_reads_sentinel_clock(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SENTINEL_CLOCK", "2026-11-02T08:35:00+08:00")

    value = now()

    assert value == datetime(2026, 11, 2, 0, 35, tzinfo=UTC)
    assert value.utcoffset() == timedelta(0)
    assert utc_today().isoformat() == "2026-11-02"


def test_parse_iso_rejects_naive_datetime(monkeypatch: pytest.MonkeyPatch) -> None:
    with pytest.raises(ValueError):
        parse_iso("2026-11-02T00:35:00")

    monkeypatch.setenv("SENTINEL_CLOCK", "2026-11-02T00:35:00")
    with pytest.raises(ValueError):
        now()


def test_to_iso_always_ends_with_z() -> None:
    value = to_iso(datetime(2026, 11, 2, 0, 35, tzinfo=UTC))

    assert value == "2026-11-02T00:35:00Z"
    assert to_iso(datetime(2026, 11, 2, 8, 35, tzinfo=timezone(timedelta(hours=8)))) == value
    with pytest.raises(ValueError):
        to_iso(datetime(2026, 11, 2, 0, 35))
