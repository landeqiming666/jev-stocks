from datetime import date

import pytest

from sentinel.errors import SourceError

from .conftest import client, payload

START, END = date(2011, 1, 1), date(2026, 11, 3)


def test_tencent_maps_close_before_high():
    from sentinel.markets.prices.tencent import TencentPriceSource

    row = ["2026-10-30", "346.72", "344.63", "349.19", "334.35", "67841555"]
    with client({"data": {"usZZAR": {"day": [row]}}}) as http:
        bar = TencentPriceSource(http).fetch_daily("us:ZZAR", START, END)[0]
    assert (bar.open, bar.close, bar.high, bar.low) == (346.72, 344.63, 349.19, 334.35)


def test_tencent_adjustment_keys():
    from sentinel.markets.prices.tencent import TencentPriceSource

    for market, symbol in (("cn", "sh600519"), ("us", "usAAPL")):
        with client(payload(f"prices_tencent_{market}.sample.json")) as http:
            bars = TencentPriceSource(http).fetch_daily(symbol, START, END)
        assert bars
        assert all(b.adj_close == (b.close if market == "cn" else None) for b in bars)


def test_tencent_empty_returns_empty():
    from sentinel.markets.prices.tencent import TencentPriceSource

    with client({"data": {"usZZAR": {"day": []}}}) as http:
        assert TencentPriceSource(http).fetch_daily("us:ZZAR", START, END) == []


def test_tencent_missing_field_and_errors():
    from sentinel.markets.prices.tencent import TencentPriceSource

    with client({"data": {"usZZAR": {"day": [["2026-10-30", "1", "1", "1", "1"]]}}}) as http:
        with pytest.raises(SourceError) as caught:
            TencentPriceSource(http).fetch_daily("us:ZZAR", START, END)
        assert caught.value.code == "SOURCE_UNAVAILABLE"
        assert caught.value.reason == "PRICE_SCHEMA"
    for code, reason in (("RATE_LIMITED", None), ("SOURCE_UNAVAILABLE", "DECODE_FAILED")):
        error = SourceError(code, reason=reason)

        class BrokenHttp:
            def get_text(self, *args, error=error, **kwargs):
                raise error

        with pytest.raises(SourceError) as caught:
            TencentPriceSource(BrokenHttp()).fetch_daily("us:ZZAR", START, END)
        assert caught.value is error


@pytest.mark.parametrize(
    "market,symbol,count", [("us", "usAAPL", 2), ("hk", "hk00700", 30), ("cn", "sh600519", 30)]
)
def test_recorded_clips_keep_dates_and_integer_volumes(market, symbol, count):
    from sentinel.markets.prices.tencent import TencentPriceSource

    with client(payload(f"prices_tencent_{market}.sample.json")) as http:
        bars = TencentPriceSource(http).fetch_daily(symbol, START, END)
    assert len(bars) == count
    assert bars == sorted(bars, key=lambda bar: bar.trade_date)
    assert all(type(bar.volume) is int or bar.volume is None for bar in bars)
    if market == "us":
        assert bars[0].trade_date == date(2011, 6, 2)
        assert all(bar.adj_close is None for bar in bars)


@pytest.mark.parametrize(
    "value,expected",
    [
        ("100.000", 100),
        ("100.00000000000000000001", None),
        ("1.5", None),
        (True, None),
        ("-1", None),
        ("NaN", None),
        ("Infinity", None),
        ("1,000", 1000),
        ("10,00", None),
        (str(2**63), None),
        ("--", None),
        (None, None),
        ("0", 0),
    ],
)
def test_volume_keeps_precision_and_never_truncates(value, expected):
    from sentinel.markets.prices.tencent import TencentPriceSource

    row = ["2026-10-30", "10", "11", "12", "9", value]
    with client({"data": {"usZZAR": {"day": [row]}}}) as http:
        bars = TencentPriceSource(http).fetch_daily("ZZAR", START, END)
    assert bars[0].volume == expected


@pytest.mark.parametrize(
    "extra",
    [
        {"cqr": "2026-10-30", "unknown": "x"},
        {"cqr": "2026-10-30", "FHcontent": 1},
        {"cqr": "2026-10-29"},
        {},
        "action",
        ["action"],
        None,
    ],
)
def test_unknown_hk_action_shape_is_rejected(extra):
    from sentinel.markets.prices.tencent import TencentPriceSource

    row = ["2026-10-30", "10", "11", "12", "9", "100", extra]
    with (
        client({"data": {"hk00700": {"day": [row]}}}) as http,
        pytest.raises(SourceError, match="SOURCE_UNAVAILABLE"),
    ):
        TencentPriceSource(http).fetch_daily("hk00700", START, END)


def test_known_hk_action_only_and_unknown_eighth_column():
    from sentinel.markets.prices.tencent import TencentPriceSource

    row = ["2026-10-30", "10", "11", "12", "9", "100", {"cqr": "2026-10-30", "FHcontent": ""}]
    for symbol, raw, accepted in [
        ("hk00700", row, True),
        ("usZZAR", row, False),
        ("sh600519", row, False),
        ("hk00700", row + ["x"], False),
    ]:
        with client({"data": {symbol: {"day": [raw]}}}) as http:
            if accepted:
                assert TencentPriceSource(http).fetch_daily(symbol, START, END)[0].close == 11
            else:
                with pytest.raises(SourceError):
                    TencentPriceSource(http).fetch_daily(symbol, START, END)


@pytest.mark.parametrize(
    "bad", [True, False, "NaN", "Infinity", "0", "-1", "1e999", {}, [], "--", None]
)
def test_invalid_close_dropped_with_valid_neighbor(bad):
    from sentinel.markets.prices.tencent import TencentPriceSource

    rows = [
        ["2026-10-29", "10", bad, "12", "9", "100"],
        ["2026-10-30", "10", "11", "12", "9", "100"],
    ]
    with client({"data": {"usZZAR": {"day": rows}}}) as http:
        bars = TencentPriceSource(http).fetch_daily("ZZAR", START, END)
    assert [bar.trade_date for bar in bars] == [date(2026, 10, 30)]


def test_tencent_request_policy_mapping_and_qfq_preference():
    import httpx

    from sentinel.http.client import HttpClient
    from sentinel.http.policy import get_policy
    from sentinel.markets.prices.source import to_tencent_symbol
    from sentinel.markets.prices.tencent import TencentPriceSource

    requests = []
    row = ["2026-10-30", "10", "11", "12", "9", "100"]

    def respond(request):
        requests.append(request)
        return httpx.Response(200, json={"data": {"usZZAR": {"day": [], "qfqday": [row]}}})

    with HttpClient(transport=httpx.MockTransport(respond)) as http:
        bar = TencentPriceSource(http).fetch_daily(
            "us:ZZAR", date(2026, 10, 30), date(2026, 11, 2)
        )[0]
    assert requests[0].url.params["param"] == "usZZAR,day,,,12,qfq"
    assert requests[0].headers["referer"] == "https://gu.qq.com/"
    assert get_policy("tencent").read_timeout_s == 30
    assert get_policy("tencent").total_timeout_s == 30
    assert bar.adj_close == bar.close
    assert to_tencent_symbol("us:AAPL") == "usAAPL"
    assert to_tencent_symbol("us:BRK.B") == "usBRK-B"
    with pytest.raises(SourceError):
        to_tencent_symbol("us:AAPL.O/evil")


@pytest.mark.parametrize(
    "data",
    [
        {},
        {"data": {}},
        {"data": {"usZZAR": {}}},
        {"data": {"usZZAR": {"day": None}}},
        {"code": 1},
        [],
    ],
)
def test_invalid_tencent_envelope(data):
    from sentinel.markets.prices.tencent import TencentPriceSource

    with client(data) as http, pytest.raises(SourceError):
        TencentPriceSource(http).fetch_daily("ZZAR", START, END)


def test_real_http_offline_and_bad_encoding_json(monkeypatch):
    import httpx

    from sentinel.http.client import HttpClient
    from sentinel.markets.prices.tencent import TencentPriceSource

    calls = []

    def respond(request):
        calls.append(request)
        return httpx.Response(
            200,
            content=b"\xff\xfe\x00",
            headers={"Content-Type": "application/json; charset=utf-8"},
        )

    with HttpClient(transport=httpx.MockTransport(respond)) as http:
        source = TencentPriceSource(http)
        monkeypatch.setenv("SENTINEL_OFFLINE", "1")
        with pytest.raises(SourceError) as caught:
            source.fetch_daily("ZZAR", START, END)
        assert caught.value.reason == "OFFLINE"
        assert not calls
        monkeypatch.delenv("SENTINEL_OFFLINE")
        with pytest.raises(SourceError) as caught:
            source.fetch_daily("ZZAR", START, END)
        assert caught.value.code == "SOURCE_UNAVAILABLE"


def test_json_fractional_volume_lexeme_must_not_round_to_integer():
    import httpx

    from sentinel.http.client import HttpClient
    from sentinel.markets.prices.tencent import TencentPriceSource

    raw = b'{"data":{"usZZAR":{"day":[["2026-10-30",10,11,12,9,100.00000000000000000001]]}}}'
    with HttpClient(
        transport=httpx.MockTransport(lambda _: httpx.Response(200, content=raw))
    ) as http:
        bar = TencentPriceSource(http).fetch_daily("ZZAR", START, END)[0]
    assert bar.volume is None


@pytest.mark.parametrize("day", ["2026-W01-1", "2026-02-30", "20261030", True])
def test_tencent_date_requires_canonical_iso_date(day):
    from sentinel.markets.prices.tencent import TencentPriceSource

    row = [day, "10", "11", "12", "9", "100"]
    with client({"data": {"usZZAR": {"day": [row]}}}) as http, pytest.raises(SourceError):
        TencentPriceSource(http).fetch_daily("ZZAR", START, END)


def test_owned_synthetic_fixtures_and_generator():
    import runpy

    from sentinel.markets.prices.tencent import TencentPriceSource

    from .conftest import FIXTURES

    with (
        client(payload("prices_tencent_bad.json")["missingField"]) as http,
        pytest.raises(SourceError),
    ):
        TencentPriceSource(http).fetch_daily("ZZAR", START, END)
    with client(payload("prices_invalid_ohlc.json")) as http:
        bars = TencentPriceSource(http).fetch_daily("ZZAR", START, END)
    assert [bar.trade_date for bar in bars] == [date(2026, 10, 28), date(2026, 11, 2)]
    generate = runpy.run_path(str(FIXTURES / "prices_synthetic.py"))["generate"]
    data = generate(date(2026, 10, 1), 4)
    assert data == generate(date(2026, 10, 1), 4) and data["synthetic"] is True
    with client(data) as http:
        assert len(TencentPriceSource(http).fetch_daily("ZZAR", START, END)) == 4


def test_request_limit_uses_us_trading_days_plus_ten():
    import httpx

    from sentinel.http.client import HttpClient
    from sentinel.markets.prices.tencent import TencentPriceSource

    requests = []

    def respond(request):
        requests.append(request)
        return httpx.Response(200, json={"data": {"usZZAR": {"day": []}}})

    with HttpClient(transport=httpx.MockTransport(respond)) as http:
        TencentPriceSource(http).fetch_daily("ZZAR", date(2026, 11, 26), date(2026, 11, 27))
    assert requests[0].url.params["param"] == "usZZAR,day,,,11,qfq"
