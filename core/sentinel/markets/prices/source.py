from __future__ import annotations

import json
import logging
import math
import re
from collections import Counter
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Protocol

from sentinel.errors import SourceError
from sentinel.http.client import HttpClient

from .models import Bar

MAX_ROWS = 250
BIGINT_MAX = 2**63 - 1
US_SYMBOL = re.compile(r"[A-Z][A-Z0-9]*(?:\.[A-Z0-9]+)?", re.ASCII)
_NUMBER = re.compile(r"(?:[0-9]+|[0-9]{1,3}(?:,[0-9]{3})+)(?:\.[0-9]+)?", re.ASCII)
_logger = logging.getLogger(__name__)


class PriceSource(Protocol):
    name: str

    def fetch_daily(self, symbol: str, start: date, end: date) -> list[Bar]: ...


def us_symbol(symbol: str) -> str:
    value = symbol.removeprefix("us:")
    if not US_SYMBOL.fullmatch(value):
        raise SourceError("SOURCE_UNAVAILABLE", reason="INVALID_SYMBOL")
    return value


def to_tencent_symbol(symbol: str) -> str:
    if re.fullmatch(r"(?:hk[0-9]{5}|(?:sh|sz)[0-9]{6})", symbol, re.ASCII):
        return symbol
    if symbol.startswith("us") and not symbol.startswith("us:"):
        symbol = symbol[2:]
    value = us_symbol(symbol)
    # G1 对 usBRK-B 的观察为空；这里只保留该请求映射，不推断成功后缀。
    return "us" + ("BRK-B" if value == "BRK.B" else value)


def schema_error() -> SourceError:
    return SourceError("SOURCE_UNAVAILABLE", reason="PRICE_SCHEMA")


def fetch_json(http: HttpClient, url: str, source: str, headers: dict[str, str]) -> object:
    text = http.get_text(url, source=source, headers=headers)
    try:
        # get_json 的 float 转换会丢掉成交量的末尾小数，必须从原始词法值检查。
        return json.loads(text, parse_float=Decimal, parse_constant=Decimal)
    except (ValueError, RecursionError):
        raise SourceError("SOURCE_UNAVAILABLE", reason="INVALID_JSON") from None


def number(value: object, *, dollar: bool = False) -> Decimal | None:
    if value is None or value in ("", "--", "N/A"):
        return None
    if isinstance(value, bool) or not isinstance(value, (str, int, float, Decimal)):
        raise ValueError("invalid number")
    if isinstance(value, Decimal):
        if not value.is_finite():
            raise ValueError("invalid number")
        return value
    text = str(value).strip()
    if dollar:
        text = text.removeprefix("$")
    if not _NUMBER.fullmatch(text):
        raise ValueError("invalid number")
    try:
        result = Decimal(text.replace(",", ""))
    except InvalidOperation as exc:
        raise ValueError("invalid number") from exc
    if not result.is_finite():
        raise ValueError("invalid number")
    return result


def price(value: object, *, dollar: bool = False) -> float | None:
    decimal = number(value, dollar=dollar)
    if decimal is None:
        return None
    result = float(decimal)
    if decimal <= 0 or not math.isfinite(result) or result <= 0:
        raise ValueError("invalid price")
    return result


def volume(value: object) -> int | None:
    try:
        decimal = number(value)
        if decimal is None:
            return None
        if decimal < 0 or decimal != decimal.to_integral_value() or decimal > BIGINT_MAX:
            raise ValueError("unreliable volume")
        return int(decimal)
    except ValueError:
        _logger.warning("prices.unreliable_volume")
        return None


def valid_bar(bar: Bar) -> bool:
    if not isinstance(bar, Bar) or type(bar.trade_date) is not date or bar.close is None:
        return False
    for value in (bar.open, bar.high, bar.low, bar.close, bar.adj_close):
        if value is not None:
            try:
                if type(value) not in (float, int) or not math.isfinite(value) or value <= 0:
                    return False
            except OverflowError:
                return False
    if bar.volume is not None and (
        type(bar.volume) is not int or not 0 <= bar.volume <= BIGINT_MAX
    ):
        return False
    if bar.high is not None and bar.low is not None and bar.high < bar.low:
        return False
    for value in (bar.open, bar.close):
        if value is not None and (
            (bar.low is not None and value < bar.low) or (bar.high is not None and value > bar.high)
        ):
            return False
    return True


def clean_bars(bars: list[Bar], start: date, end: date) -> list[Bar]:
    by_day: dict[date, Bar] = {}
    conflicting: set[date] = set()
    counts: Counter[str] = Counter()
    for bar in bars:
        if not valid_bar(bar):
            counts["invalid"] += 1
        elif not start <= bar.trade_date <= end:
            counts["outside_window"] += 1
        elif bar.trade_date in by_day:
            counts["duplicate"] += 1
            if by_day[bar.trade_date] != bar:
                conflicting.add(bar.trade_date)
        else:
            by_day[bar.trade_date] = bar
    if counts:
        _logger.warning("prices.filtered_rows %s", dict(counts))
    return [by_day[day] for day in sorted(by_day) if day not in conflicting][-MAX_ROWS:]
