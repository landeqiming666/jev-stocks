from datetime import date

import pytest

from sentinel.errors import SourceError

from .conftest import client, payload


def test_nasdaq_strips_dollar_and_parses_date():
    from sentinel.markets.prices.nasdaq import NasdaqPriceSource

    data = {"data": {"tradesTable": {"rows": [{"date": "10/30/2026", "close": "$344.63"}]}}}
    with client(data) as http:
        bars = NasdaqPriceSource(http).fetch_daily("ZZAR", date(2026, 10, 1), date(2026, 11, 2))
    assert bars[0].trade_date == date(2026, 10, 30)
    assert bars[0].close == 344.63
    assert bars[0].adj_close is None


def test_nasdaq_recorded_clip_and_order():
    from sentinel.markets.prices.nasdaq import NasdaqPriceSource

    with client(payload("prices_nasdaq_us.sample.json")) as http:
        bars = NasdaqPriceSource(http).fetch_daily("us:AAPL", date(2026, 9, 1), date(2026, 11, 2))
    assert len(bars) == 30
    assert bars[0].trade_date == date(2026, 9, 22)
    assert bars[-1].trade_date == date(2026, 11, 2)
    assert bars[-1].close == 338.32
    assert all(bar.adj_close is None for bar in bars)


def test_nasdaq_commas_requests_and_window():
    import httpx

    from sentinel.http.client import HttpClient
    from sentinel.markets.prices.nasdaq import NasdaqPriceSource

    requests = []
    rows = [
        {"date": "11/02/2026", "close": "$1,234.56", "volume": "1,000,000"},
        {"date": "11/03/2026", "close": "$1,240"},
    ]

    def respond(request):
        requests.append(request)
        return httpx.Response(200, json={"data": {"tradesTable": {"rows": rows}}})

    with HttpClient(transport=httpx.MockTransport(respond)) as http:
        bars = NasdaqPriceSource(http).fetch_daily("ZZAR", date(2026, 10, 1), date(2026, 11, 2))
    assert len(bars) == 1
    assert bars[0].close == 1234.56 and bars[0].volume == 1000000
    assert dict(requests[0].url.params) == {
        "assetclass": "stocks",
        "fromdate": "2026-10-01",
        "limit": "250",
    }
    assert "/quote/ZZAR/historical" in requests[0].url.path


@pytest.mark.parametrize("day", ["02/30/2026", "2026-10-30", "1/2/2026", None, True])
def test_nasdaq_rejects_invalid_dates(day):
    from sentinel.markets.prices.nasdaq import NasdaqPriceSource

    with (
        client({"data": {"tradesTable": {"rows": [{"date": day, "close": "$10"}]}}}) as http,
        pytest.raises(SourceError),
    ):
        NasdaqPriceSource(http).fetch_daily("ZZAR", date(2026, 1, 1), date(2026, 11, 2))


@pytest.mark.parametrize(
    "data",
    [
        {},
        {"data": None},
        {"data": {"tradesTable": None}},
        {"data": {"tradesTable": {"rows": None}}},
        {"data": {"symbol": "ZZFD", "tradesTable": {"rows": []}}},
    ],
)
def test_nasdaq_schema_failure(data):
    from sentinel.markets.prices.nasdaq import NasdaqPriceSource

    with client(data) as http, pytest.raises(SourceError):
        NasdaqPriceSource(http).fetch_daily("ZZAR", date(2026, 1, 1), date(2026, 11, 2))


def test_nasdaq_empty_and_missing_close():
    from sentinel.markets.prices.nasdaq import NasdaqPriceSource

    for rows in ([], [{"date": "11/02/2026", "open": "$10"}]):
        with client({"data": {"tradesTable": {"rows": rows}}}) as http:
            assert not NasdaqPriceSource(http).fetch_daily(
                "ZZAR", date(2026, 1, 1), date(2026, 11, 2)
            )


def test_coordinator_250_response_clip_preserves_provenance():
    from sentinel.markets.prices.nasdaq import NasdaqPriceSource

    data = payload("prices_nasdaq_250_clipped.sample.json")
    assert data["_provenance"]["originalRows"] == 250
    assert data["_provenance"]["httpStatus"] == 200
    assert (
        data["_provenance"]["sha256"]
        == "07137d3fafd0ce7e971e04796a06bc035070ee24f807f0de319545879eea26ae"
    )
    with client(data) as http:
        bars = NasdaqPriceSource(http).fetch_daily("AAPL", date(2025, 1, 1), date(2026, 11, 2))
    assert len(bars) == 30
    assert bars[-1].trade_date == date(2026, 11, 2)
