from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import cast

import duckdb

from sentinel import clock
from sentinel.errors import InternalError, UserError
from sentinel.storage.db import Database, SqlExecutor, WriteTx

STARTUP_CATCH_UP_HOURS = 72
MAX_EXPLICIT_LOOKBACK_DAYS = 30


def utc(value: datetime, field: str = "from") -> datetime:
    if not isinstance(value, datetime) or value.utcoffset() is None:
        raise UserError("INVALID_ARGUMENT", field=field)
    return value.astimezone(UTC)


@dataclass(frozen=True)
class ScanWindow:
    start: datetime
    end: datetime
    used_startup_catch_up: bool


def compute_window(
    *,
    now: datetime,
    watermark: datetime | None,
    first_lookback_days: int,
    explicit_from: datetime | None,
) -> ScanWindow:
    end = utc(now, "now")
    if type(first_lookback_days) is not int or not 1 <= first_lookback_days <= 30:
        raise UserError("INVALID_ARGUMENT", field="firstScanLookbackDays")
    if explicit_from is not None:
        start = utc(explicit_from)
        if not end - timedelta(days=MAX_EXPLICIT_LOOKBACK_DAYS) <= start <= end:
            raise UserError("INVALID_ARGUMENT", field="from")
        return ScanWindow(start, end, False)
    if watermark is None:
        return ScanWindow(end - timedelta(days=first_lookback_days), end, False)
    old = utc(watermark, "watermark")
    if old > end:
        raise InternalError(detail="watermark is later than scan clock")
    floor = end - timedelta(hours=STARTUP_CATCH_UP_HOURS)
    return ScanWindow(max(old, floor), end, old < floor)


def read_from(executor: SqlExecutor, market: str) -> datetime | None:
    executor.execute("SELECT covered_until FROM watermark WHERE market=?", [market])
    row = executor.fetchone()
    return None if row is None else utc(cast(datetime, row[0]), "watermark")


def advance_in(tx: WriteTx, market: str, covered_until: datetime) -> datetime:
    value = utc(covered_until, "coveredUntil")
    tx.execute(
        "INSERT INTO watermark VALUES (?, ?, ?) ON CONFLICT(market) DO UPDATE SET "
        "covered_until=greatest(watermark.covered_until, excluded.covered_until), "
        "updated_at=CASE WHEN excluded.covered_until>watermark.covered_until "
        "THEN excluded.updated_at ELSE watermark.updated_at END",
        [market, value, clock.now()],
    )
    result = read_from(tx, market)
    assert result is not None
    return result


def read_watermark(db: Database, market: str) -> datetime | None:
    try:
        with db.read() as reader:
            return read_from(reader, market)
    except duckdb.Error:
        raise InternalError(detail="scan watermark read failed") from None


def advance_watermark(db: Database, market: str, covered_until: datetime) -> datetime:
    try:
        with db.write() as tx:
            return advance_in(tx, market, covered_until)
    except duckdb.Error:
        raise InternalError(detail="scan watermark write failed") from None
