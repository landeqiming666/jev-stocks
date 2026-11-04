from __future__ import annotations

import logging
from datetime import date, datetime
from urllib.parse import quote, urlencode

from sentinel.http.client import HttpClient

from .models import Bar
from .source import MAX_ROWS, clean_bars, fetch_json, price, schema_error, us_symbol, volume

NASDAQ_URL = "https://api.nasdaq.com/api/quote/{symbol}/historical"
_logger = logging.getLogger(__name__)


class NasdaqPriceSource:
    name = "nasdaq"

    def __init__(self, http: HttpClient) -> None:
        self._http = http

    def fetch_daily(self, symbol: str, start: date, end: date) -> list[Bar]:
        symbol = us_symbol(symbol)
        if start > end:
            return []
        query = urlencode(
            {"assetclass": "stocks", "fromdate": start.isoformat(), "limit": MAX_ROWS}
        )
        payload = fetch_json(
            self._http,
            NASDAQ_URL.format(symbol=quote(symbol, safe="")) + "?" + query,
            self.name,
            {"User-Agent": "Mozilla/5.0", "Accept": "application/json"},
        )
        data = payload.get("data") if isinstance(payload, dict) else None
        if not isinstance(data, dict):
            raise schema_error()
        if data.get("symbol", symbol) != symbol:
            raise schema_error()
        table = data.get("tradesTable")
        rows = table.get("rows") if isinstance(table, dict) else None
        if not isinstance(rows, list):
            raise schema_error()
        bars: list[Bar] = []
        malformed = 0
        for row in rows:
            try:
                if not isinstance(row, dict) or not isinstance(row.get("date"), str):
                    raise ValueError("unknown shape")
                day = datetime.strptime(row["date"], "%m/%d/%Y").date()
                if day.strftime("%m/%d/%Y") != row["date"]:
                    raise ValueError("invalid date")
                bars.append(
                    Bar(
                        day,
                        price(row.get("open"), dollar=True),
                        price(row.get("high"), dollar=True),
                        price(row.get("low"), dollar=True),
                        price(row.get("close"), dollar=True),
                        None,
                        volume(row.get("volume")),
                    )
                )
            except (ValueError, TypeError):
                malformed += 1
        if malformed:
            _logger.warning("prices.schema_rows count=%d", malformed)
            if not bars:
                raise schema_error()
        return clean_bars(bars, start, end)
