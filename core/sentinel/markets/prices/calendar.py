from __future__ import annotations

import json
import logging
import threading
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from functools import lru_cache
from pathlib import Path
from types import MappingProxyType
from zoneinfo import ZoneInfo

EASTERN = ZoneInfo("America/New_York")
CALENDAR_PATH = Path(__file__).resolve().parents[4] / "resources/calendars/us.json"
_logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class MarketState:
    status: str
    next_open_at: datetime


def _time(value: object) -> time:
    if not isinstance(value, str) or len(value) != 5:
        raise ValueError("invalid session time")
    result = time.fromisoformat(value)
    if result.isoformat(timespec="minutes") != value:
        raise ValueError("invalid session time")
    return result


class TradingCalendar:
    def __init__(self, path: Path) -> None:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict) or (
            data.get("market") != "us" or data.get("timezone") != "America/New_York"
        ):
            raise ValueError("invalid US calendar identity")
        years = data.get("years")
        if (
            not isinstance(years, list)
            or not years
            or any(type(year) is not int or not 1 <= year <= 9999 for year in years)
            or years != sorted(set(years))
        ):
            raise ValueError("invalid calendar years")
        self.years = frozenset(years)
        self.pre_open = _time(data.get("pre_open"))
        self.regular_open = _time(data.get("regular_open"))
        self.regular_close = _time(data.get("regular_close"))
        self.after_close = _time(data.get("after_close"))
        if not self.pre_open < self.regular_open < self.regular_close < self.after_close:
            raise ValueError("invalid session ordering")
        holidays: set[date] = set()
        early: dict[date, time] = {}
        for key in ("holidays", "early_closes"):
            rows = data.get(key)
            if not isinstance(rows, list):
                raise ValueError("invalid calendar rows")
            for row in rows:
                if not isinstance(row, dict) or not isinstance(row.get("date"), str):
                    raise ValueError("invalid calendar row")
                day = date.fromisoformat(row["date"])
                if (
                    day.isoformat() != row["date"]
                    or day.year not in self.years
                    or day.weekday() >= 5
                ):
                    raise ValueError("invalid calendar date")
                if day in holidays or day in early:
                    raise ValueError("duplicate calendar date")
                if key == "holidays":
                    holidays.add(day)
                else:
                    closing = _time(row.get("close"))
                    if not self.regular_open < closing < self.regular_close:
                        raise ValueError("invalid early close")
                    early[day] = closing
        self.holidays = frozenset(holidays)
        self.early_closes = MappingProxyType(early)
        self._warned: set[int] = set()
        self._lock = threading.Lock()

    def is_trading_day(self, day: date) -> bool:
        if day.year not in self.years:
            with self._lock:
                if day.year not in self._warned:
                    self._warned.add(day.year)
                    _logger.warning("calendar.out_of_range year=%d", day.year)
            return day.weekday() < 5
        return day.weekday() < 5 and day not in self.holidays

    def next_trading_day(self, day: date) -> date:
        day += timedelta(days=1)
        while not self.is_trading_day(day):
            day += timedelta(days=1)
        return day

    def prev_trading_day(self, day: date) -> date:
        day -= timedelta(days=1)
        while not self.is_trading_day(day):
            day -= timedelta(days=1)
        return day

    def session_close(self, day: date) -> datetime:
        if not self.is_trading_day(day):
            raise ValueError("non-trading day has no session")
        return datetime.combine(
            day, self.early_closes.get(day, self.regular_close), EASTERN
        ).astimezone(UTC)

    def latest_closed_day(self, now: datetime) -> date:
        now = _utc(now)
        day = now.astimezone(EASTERN).date()
        if self.is_trading_day(day) and now >= self.session_close(day):
            return day
        return self.prev_trading_day(day)

    def market_state(self, now: datetime) -> MarketState:
        local = _utc(now).astimezone(EASTERN)
        day, hour = local.date(), local.time()
        trading = self.is_trading_day(day)
        next_day = day if trading and hour < self.regular_open else self.next_trading_day(day)
        next_open = datetime.combine(next_day, self.regular_open, EASTERN).astimezone(UTC)
        if not trading:
            status = "holiday"
        elif hour < self.pre_open or hour >= self.after_close:
            status = "closed"
        elif hour < self.regular_open:
            status = "pre"
        elif local < self.session_close(day).astimezone(EASTERN):
            status = "open"
        else:
            status = "after"
        return MarketState(status, next_open)


def _utc(now: datetime) -> datetime:
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("clock must be timezone-aware")
    return now.astimezone(UTC)


@lru_cache(maxsize=1)
def _default() -> TradingCalendar:
    return TradingCalendar(CALENDAR_PATH)


def is_trading_day(d: date) -> bool:
    return _default().is_trading_day(d)


def next_trading_day(d: date) -> date:
    return _default().next_trading_day(d)


def prev_trading_day(d: date) -> date:
    return _default().prev_trading_day(d)


def session_close(d: date) -> datetime:
    return _default().session_close(d)


def market_state(now: datetime) -> MarketState:
    return _default().market_state(now)
