"""SEC ticker transport; filtering and counts belong to the repository."""

from collections.abc import Callable
from typing import cast

from sentinel import __version__
from sentinel.domain.contact import is_valid_sec_email
from sentinel.errors import SourceError, UserError
from sentinel.http import HttpClient

from .models import TickerRow

TICKERS_URL = "https://www.sec.gov/files/company_tickers_exchange.json"
EXCHANGE_MAP = {
    "Nasdaq": "NASDAQ",
    "NYSE": "NYSE",
    "NYSE American": "NYSE American",
    "CBOE": "CBOE",
}
_FIELDS = ["cik", "name", "ticker", "exchange"]


class SecTickerSource:
    def __init__(
        self,
        http: HttpClient,
        *,
        email_provider: Callable[[], str | None] | None = None,
    ) -> None:
        self._http = http
        self._email_provider = email_provider

    def fetch(self) -> list[TickerRow]:
        email = self._email_provider() if self._email_provider is not None else None
        if not isinstance(email, str) or not is_valid_sec_email(email):
            raise UserError("CONFIG_REQUIRED", params={"missing": ["secEmail"]})
        payload = self._http.get_json(
            TICKERS_URL,
            source="sec",
            headers={"User-Agent": f"Sentinel/{__version__} {email}"},
        )
        if (
            not isinstance(payload, dict)
            or payload.get("fields") != _FIELDS
            or not isinstance(payload.get("data"), list)
        ):
            raise SourceError("SOURCE_UNAVAILABLE", reason="TICKER_SCHEMA")
        rows: list[TickerRow] = []
        for row in payload["data"]:
            if not isinstance(row, list) or len(row) != 4:
                raise SourceError("SOURCE_UNAVAILABLE", reason="TICKER_SCHEMA")
            if not isinstance(row[1], str) or not row[1].strip():
                raise SourceError("SOURCE_UNAVAILABLE", reason="TICKER_SCHEMA")
            # CIK 的整数用文本无损承载；bool、浮点和非法文本仍由仓储计为跳过。
            rows.append(TickerRow(str(row[0]), *cast(tuple[str, str, str], tuple(row[1:]))))
        return rows
