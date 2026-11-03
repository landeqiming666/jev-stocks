from __future__ import annotations

import logging
import threading
from collections.abc import Callable, Sequence
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import cast

import duckdb

from sentinel.errors import InternalError, SentinelError, SourceError, UserError
from sentinel.storage.db import Database

from .calendar import TradingCalendar, _utc
from .models import Bar, RefreshFailure, RefreshParams, RefreshResult
from .source import MAX_ROWS, US_SYMBOL, PriceSource, clean_bars

DEFAULT_LOOKBACK_DAYS = 1095
_logger = logging.getLogger(__name__)
_UPSERT = """INSERT INTO price_daily VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
ON CONFLICT (instrument_id, trade_date) DO UPDATE SET
open=excluded.open, high=excluded.high, low=excluded.low, close=excluded.close,
adj_close=excluded.adj_close, volume=excluded.volume, source=excluded.source,
fetched_at=excluded.fetched_at"""


class PriceService:
    def __init__(
        self,
        db: Database,
        primary: PriceSource,
        backup: PriceSource,
        calendar_path: Path,
        clock: Callable[[], datetime],
    ) -> None:
        self._db, self._primary, self._backup, self._clock = db, primary, backup, clock
        self.calendar = TradingCalendar(calendar_path)
        self._lock = threading.Lock()

    def refresh(self, instrument_ids: Sequence[str] | None = None) -> RefreshResult:
        params = RefreshParams(instrument_ids)
        with self._lock:
            as_of = self.calendar.latest_closed_day(self._clock())
            if params.instrument_ids is None:
                with self._db.read() as reader:
                    reader.execute(
                        "SELECT instrument_id FROM holding "
                        "WHERE archived_at IS NULL ORDER BY instrument_id"
                    )
                    ids = [cast(str, row[0]) for row in reader.fetchall()]
            else:
                ids = list(dict.fromkeys(params.instrument_ids))
            updated = 0
            failed: list[RefreshFailure] = []
            for instrument_id in ids:
                try:
                    updated += self._refresh_one(instrument_id, as_of)
                except SentinelError as exc:
                    failed.append(RefreshFailure.from_error(instrument_id, exc))
                except duckdb.Error:
                    failed.append(RefreshFailure(instrument_id, "INTERNAL", "PRICE_WRITE_FAILED"))
                except Exception:
                    # 不输出源异常文本，它可能带请求参数或用户持仓。
                    failed.append(RefreshFailure(instrument_id, "INTERNAL", "PRICE_REFRESH_FAILED"))
            return RefreshResult(updated, failed, as_of)

    def _refresh_one(self, instrument_id: str, as_of: date) -> int:
        if not instrument_id.startswith("us:") or not US_SYMBOL.fullmatch(instrument_id[3:]):
            raise UserError("INVALID_ARGUMENT", reason="INVALID_INSTRUMENT_ID")
        with self._db.read() as reader:
            reader.execute(
                "SELECT market, symbol FROM instrument WHERE instrument_id=?", [instrument_id]
            )
            row = reader.fetchone()
            if row is None:
                raise UserError("NOT_FOUND", reason="INSTRUMENT_NOT_FOUND")
            if row != ("us", instrument_id[3:]):
                raise UserError("INVALID_ARGUMENT", reason="INVALID_INSTRUMENT_ID")
            reader.execute(
                "SELECT MAX(trade_date) FROM price_daily WHERE instrument_id=? AND trade_date<=?",
                [instrument_id, as_of],
            )
            latest = reader.fetchone()
        last_date = cast(date | None, latest[0]) if latest else None
        start = (
            last_date + timedelta(days=1)
            if last_date
            else as_of - timedelta(days=DEFAULT_LOOKBACK_DAYS)
        )
        if start > as_of:
            return 0
        expected: list[date] = []
        for n in range((as_of - start).days + 1):
            day = start + timedelta(days=n)
            if self.calendar.is_trading_day(day):
                expected.append(day)
        wanted = frozenset(expected[-MAX_ROWS:])
        if not wanted:
            return 0
        chosen: list[Bar] = []
        source_name = ""
        errors: list[SourceError] = []
        for source in (self._primary, self._backup):
            try:
                candidates = clean_bars(
                    source.fetch_daily(instrument_id[3:], start, as_of), start, as_of
                )
                candidates = [
                    bar for bar in candidates if self.calendar.is_trading_day(bar.trade_date)
                ]
            except SourceError as exc:
                errors.append(exc)
                _logger.warning("prices.source_failed source=%s code=%s", source.name, exc.code)
                continue

            def score(bars: list[Bar]) -> tuple[int, int, date]:
                return (
                    len(wanted.intersection(bar.trade_date for bar in bars)),
                    len(bars),
                    bars[-1].trade_date if bars else date.min,
                )

            if score(candidates) > score(chosen):
                chosen, source_name = candidates, source.name
            if len(wanted.intersection(bar.trade_date for bar in chosen)) == len(wanted):
                break
        if not chosen:
            code = (
                "RATE_LIMITED"
                if errors and all(e.code == "RATE_LIMITED" for e in errors)
                else "SOURCE_UNAVAILABLE"
            )
            reason = (
                "OFFLINE"
                if errors and all(e.reason == "OFFLINE" for e in errors)
                else "NO_VALID_PRICES"
            )
            raise SourceError(code, reason=reason)
        covered = len(wanted.intersection(bar.trade_date for bar in chosen))
        if covered < len(wanted):
            _logger.warning(
                "prices.coverage_incomplete source=%s expected=%d actual=%d",
                source_name,
                len(wanted),
                covered,
            )
        fetched_at = _utc(self._clock())
        rows = [
            [
                instrument_id,
                bar.trade_date,
                bar.open,
                bar.high,
                bar.low,
                bar.close,
                bar.adj_close,
                bar.volume,
                source_name,
                fetched_at,
            ]
            for bar in chosen
        ]
        # 网络与校验已经完成；事务只包裹这一个标的的价格写入。
        try:
            with self._db.write() as tx:
                tx.executemany(_UPSERT, rows)
        except duckdb.Error as exc:
            raise InternalError(reason="PRICE_WRITE_FAILED") from exc
        return 1
