from __future__ import annotations

import logging
from dataclasses import replace
from datetime import date, timedelta
from urllib.parse import urlencode

from sentinel.http.client import HttpClient
from sentinel.http.policy import SourcePolicy, get_policy, register_policy

from .calendar import is_trading_day
from .models import Bar
from .source import MAX_ROWS, clean_bars, fetch_json, price, schema_error, to_tencent_symbol, volume

TENCENT_URL = "https://web.ifzq.gtimg.cn/appstock/app/fqkline/get"
_ACTION_KEYS = {"cqr", "FHcontent", "HGcontent", "paixiri", "hgcgContent", "ggContent"}
_logger = logging.getLogger(__name__)


def _action_valid(row: list[object], symbol: str) -> bool:
    if len(row) == 6:
        return True
    if len(row) != 7 or not symbol.startswith("hk") or not isinstance(row[6], dict):
        return False
    action = row[6]
    return (
        set(action) == _ACTION_KEYS
        and action.get("cqr") == row[0]
        and all(isinstance(value, str) for value in action.values())
    )


class TencentPriceSource:
    name = "tencent"

    def __init__(self, http: HttpClient) -> None:
        self._http = http
        policy: SourcePolicy = get_policy(self.name)
        register_policy(replace(policy, read_timeout_s=30.0, total_timeout_s=30.0))

    def fetch_daily(self, symbol: str, start: date, end: date) -> list[Bar]:
        symbol = to_tencent_symbol(symbol)
        if start > end:
            return []
        days = sum(
            is_trading_day(start + timedelta(days=n))
            if symbol.startswith("us")
            else (start + timedelta(days=n)).weekday() < 5
            for n in range((end - start).days + 1)
        )
        limit = min(MAX_ROWS, days + 10)
        query = urlencode({"param": f"{symbol},day,,,{limit},qfq"})
        payload = fetch_json(
            self._http, f"{TENCENT_URL}?{query}", self.name, {"Referer": "https://gu.qq.com/"}
        )
        if (
            not isinstance(payload, dict)
            or type(payload.get("code")) is not int
            or payload.get("code") != 0
        ):
            raise schema_error()
        data = payload.get("data")
        entry = data.get(symbol) if isinstance(data, dict) else None
        if not isinstance(entry, dict):
            raise schema_error()
        key = "qfqday" if "qfqday" in entry else "day"
        rows = entry.get(key)
        if not isinstance(rows, list):
            raise schema_error()
        bars: list[Bar] = []
        malformed = 0
        for row in rows:
            try:
                if not isinstance(row, list) or not _action_valid(row, symbol):
                    raise ValueError("unknown shape")
                if not isinstance(row[0], str) or len(row[0]) != 10:
                    raise ValueError("invalid date")
                day = date.fromisoformat(row[0])
                if day.isoformat() != row[0]:
                    raise ValueError("invalid date")
                opening, close, high, low = (price(value) for value in row[1:5])
                bars.append(
                    Bar(
                        day,
                        opening,
                        high,
                        low,
                        close,
                        close if key == "qfqday" else None,
                        volume(row[5]),
                    )
                )
            except (ValueError, TypeError):
                malformed += 1
        if malformed:
            _logger.warning("prices.schema_rows count=%d", malformed)
            if not bars:
                raise schema_error()
        if key == "qfqday" and bars:
            _logger.warning("prices.adjustment_unverified key=qfqday")
        return clean_bars(bars, start, end)
