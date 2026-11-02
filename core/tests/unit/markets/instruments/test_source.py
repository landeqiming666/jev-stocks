import json

import httpx
import pytest

from sentinel import __version__
from sentinel.errors import SourceError, UserError
from sentinel.http import HttpClient
from sentinel.markets.instruments import InstrumentRepository, SecTickerSource
from sentinel.markets.instruments.source import TICKERS_URL

from .conftest import FIXTURES, NOW


class FakeHTTP:
    def __init__(self, payload: object) -> None:
        self.payload = payload
        self.calls: list[tuple[str, str, dict[str, str]]] = []

    def get_json(self, url: str, *, source: str, headers: dict[str, str]) -> object:
        self.calls.append((url, source, headers))
        if isinstance(self.payload, Exception):
            raise self.payload
        return self.payload


def test_fetch_maps_exchange_whitelist(repo: InstrumentRepository) -> None:
    payload = json.loads((FIXTURES / "company_tickers_exchange.sample.json").read_text())
    http = FakeHTTP(payload)
    rows = SecTickerSource(http, email_provider=lambda: "test@example.com").fetch()
    assert len(rows) == 25
    assert {row.exchange for row in rows} >= {"OTC", "Nasdaq", "NYSE", "CBOE", "NYSE American"}
    assert http.calls == [
        (TICKERS_URL, "sec", {"User-Agent": f"Sentinel/{__version__} test@example.com"})
    ]
    stats = repo.replace_from_sec(rows, fetched_at=NOW)
    assert stats.total == 25 and stats.kept == 13
    assert stats.skipped_exchange == 2 and stats.skipped_symbol == 9 and stats.duplicates == 1
    assert repo.get("us:AAPL").exchange == "NASDAQ"


@pytest.mark.parametrize(
    "email",
    [
        None,
        "",
        " ",
        "bad",
        "a@b",
        "@example.com",
        "a b@example.com",
        "a\r\n@example.com",
        "a@-example.com",
        "a@example..com",
        "a..b@example.com",
        True,
    ],
)
def test_no_valid_email_never_calls_http(email: object) -> None:
    http = FakeHTTP(None)
    source = SecTickerSource(http, email_provider=lambda: email)
    with pytest.raises(UserError) as error:
        source.fetch()
    assert error.value.to_wire()["data"]["missing"] == ["secEmail"]
    assert error.value.code == "CONFIG_REQUIRED"
    assert http.calls == []


def test_default_provider_requires_configuration() -> None:
    http = FakeHTTP(None)
    with pytest.raises(UserError, match="CONFIG_REQUIRED"):
        SecTickerSource(http).fetch()
    assert not http.calls


def test_actual_header_and_dynamic_email(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SENTINEL_OFFLINE", raising=False)
    requests: list[httpx.Request] = []

    def handle(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200, json={"fields": ["cik", "name", "ticker", "exchange"], "data": []}
        )

    settings = {"email": "first@example.com"}
    with HttpClient(transport=httpx.MockTransport(handle)) as http:
        source = SecTickerSource(http, email_provider=lambda: settings["email"])
        assert source.fetch() == []
        settings["email"] = "second@example.com"
        assert source.fetch() == []
        settings["email"] = ""
        with pytest.raises(UserError):
            source.fetch()
    assert [r.headers["User-Agent"] for r in requests] == [
        f"Sentinel/{__version__} first@example.com",
        f"Sentinel/{__version__} second@example.com",
    ]
    assert all(str(r.url) == TICKERS_URL for r in requests)


@pytest.mark.parametrize(
    "payload",
    [
        None,
        [],
        {},
        {"fields": ["name", "cik", "ticker", "exchange"], "data": []},
        {"fields": ["cik", "name", "ticker"], "data": []},
        {"fields": ["cik", "name", "ticker", "exchange"], "data": [[1, "X", "X"]]},
        {"fields": ["cik", "name", "ticker", "exchange"], "data": [[1, "X", "X", "NYSE", 5]]},
        {"fields": ["cik", "name", "ticker", "exchange"], "data": ["abcd"]},
        {"fields": ["cik", "name", "ticker", "exchange"], "data": None},
    ],
)
def test_fetch_schema_and_empty(payload: object) -> None:
    with pytest.raises(SourceError) as error:
        SecTickerSource(FakeHTTP(payload), email_provider=lambda: "test@example.com").fetch()
    assert error.value.reason == "TICKER_SCHEMA"
    assert (
        SecTickerSource(
            FakeHTTP({"fields": ["cik", "name", "ticker", "exchange"], "data": []}),
            email_provider=lambda: "test@example.com",
        ).fetch()
        == []
    )


@pytest.mark.parametrize("reason", ["DECODE_FAILED", "INVALID_JSON", "SEC_FORBIDDEN"])
def test_fetch_rate_limit_and_decode_map(reason: str) -> None:
    failure = SourceError("SOURCE_UNAVAILABLE", reason=reason)
    with pytest.raises(SourceError) as error:
        SecTickerSource(FakeHTTP(failure), email_provider=lambda: "test@example.com").fetch()
    assert error.value is failure
    failure = SourceError("RATE_LIMITED", params={"retryAfterSec": 2})
    with pytest.raises(SourceError) as error:
        SecTickerSource(FakeHTTP(failure), email_provider=lambda: "test@example.com").fetch()
    assert error.value is failure and error.value.retryable
