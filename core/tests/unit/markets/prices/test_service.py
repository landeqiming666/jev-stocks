import json
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta

import duckdb
import jsonschema
import pytest
from referencing import Registry, Resource

from sentinel.errors import SourceError, UserError

from .conftest import NOW, ROOT, FakeSource, client, payload, prices, seed


def test_service_fallback_and_incremental(db):
    from sentinel.markets.prices import Bar, PriceService

    seed(db, date(2026, 10, 29))
    backup = FakeSource("nasdaq", [Bar(date(2026, 10, 30), 10, 12, 9, 11, None, 100)])
    service = PriceService(
        db,
        FakeSource("tencent", error=SourceError("TIMEOUT")),
        backup,
        ROOT / "resources/calendars/us.json",
        lambda: NOW,
    )
    assert service.refresh(["us:ZZAR"]).updated == 1
    assert backup.calls[0][1] == date(2026, 10, 30)
    assert prices(db)[-1][3] == "nasdaq"


def test_service_failure_and_invalid_ohlc(db):
    from sentinel.markets.prices import Bar, PriceService

    bad = FakeSource("tencent", [Bar(date(2026, 11, 2), 10, 8, 9, 10, None, 100)])
    service = PriceService(
        db,
        bad,
        FakeSource("nasdaq", error=SourceError("TIMEOUT")),
        ROOT / "resources/calendars/us.json",
        lambda: NOW,
    )
    result = service.refresh(["us:ZZAR"])
    assert result.failed[0].code == "SOURCE_UNAVAILABLE"
    assert not prices(db)


def bar(day=date(2026, 11, 2), close=11):
    from sentinel.markets.prices import Bar

    return Bar(day, 10, 12, 9, close, None, 100)


def service(db, primary, backup=None, now=NOW, path=None):
    from sentinel.markets.prices import PriceService

    return PriceService(
        db,
        primary,
        backup or FakeSource("nasdaq"),
        path or ROOT / "resources/calendars/us.json",
        lambda: now,
    )


def test_partial_primary_selects_more_complete_backup_without_mixing(db, caplog):
    seed(db, date(2026, 10, 28))
    primary = FakeSource("tencent", [bar(date(2026, 11, 2), 10)])
    backup = FakeSource("nasdaq", [bar(date(2026, 10, 29)), bar(date(2026, 10, 30)), bar()])
    result = service(db, primary, backup).refresh(["us:ZZAR"])
    assert result.updated == 1
    assert len(backup.calls) == 1
    assert all(row[2:] == (11, "nasdaq") for row in prices(db)[1:])
    assert "coverage_incomplete" not in caplog.text


def test_full_primary_skips_backup(db):
    seed(db, date(2026, 10, 29))
    backup = FakeSource("nasdaq")
    assert (
        service(db, FakeSource("tencent", [bar(date(2026, 10, 30)), bar()]), backup)
        .refresh(["us:ZZAR"])
        .updated
        == 1
    )
    assert not backup.calls


def test_two_partial_sources_save_one_and_warn(db, caplog):
    primary = FakeSource("tencent", [bar(date(2026, 10, 30), 10), bar()])
    backup = FakeSource("nasdaq", [bar(date(2026, 10, 29), 12)])
    result = service(db, primary, backup).refresh(["us:ZZAR"])
    assert result.updated == 1 and not result.failed
    assert len(prices(db)) == 2
    assert {row[3] for row in prices(db)} == {"tencent"}
    assert "coverage_incomplete" in caplog.text


def test_partial_primary_survives_backup_error(db, caplog):
    result = service(
        db, FakeSource("tencent", [bar()]), FakeSource("nasdaq", error=SourceError("RATE_LIMITED"))
    ).refresh(["us:ZZAR"])
    assert result.updated == 1 and not result.failed
    assert "coverage_incomplete" in caplog.text


def test_invalid_primary_filtered_before_coverage_check(db):
    seed(db, date(2026, 10, 29))
    primary = FakeSource(
        "tencent", [replace(bar(date(2026, 10, 30)), high=8), bar(), bar(date(2026, 11, 3))]
    )
    backup = FakeSource("nasdaq", [bar(date(2026, 10, 30)), bar()])
    service(db, primary, backup).refresh(["us:ZZAR"])
    assert backup.calls
    assert {row[3] for row in prices(db)[1:]} == {"nasdaq"}


@pytest.mark.parametrize(
    "field,value",
    [
        ("close", None),
        ("open", True),
        ("close", float("nan")),
        ("low", float("inf")),
        ("adj_close", float("-inf")),
        ("close", 0),
        ("open", -1),
        ("high", 8),
        ("low", 11),
        ("volume", True),
        ("volume", 1.5),
        ("volume", -1),
        ("volume", 2**63),
        ("trade_date", "2026-11-02"),
        ("trade_date", datetime(2026, 11, 2)),
        ("open", 10**1000),
    ],
)
def test_service_rejects_untrusted_bars(db, field, value):
    result = service(db, FakeSource("tencent", [replace(bar(), **{field: value})])).refresh(
        ["us:ZZAR"]
    )
    assert result.updated == 0
    assert result.failed[0].code == "SOURCE_UNAVAILABLE"
    assert not prices(db)


def test_unsorted_duplicates_conflicts_and_outside_window(db):
    seed(db, date(2026, 10, 28))
    rows = [
        bar(),
        bar(date(2026, 10, 29)),
        bar(date(2026, 10, 30)),
        bar(date(2026, 10, 29)),
        bar(date(2026, 10, 30), 12),
        bar(date(2026, 11, 3)),
        bar(date(2011, 6, 2)),
        bar(date(2026, 11, 1)),
    ]
    result = service(db, FakeSource("tencent", rows)).refresh(["us:ZZAR"])
    assert result.updated == 1
    assert [row[1] for row in prices(db)[1:]] == [date(2026, 10, 29), date(2026, 11, 2)]


@pytest.mark.parametrize(
    "now,expected",
    [
        (datetime(2026, 11, 2, 20, 59, tzinfo=UTC), date(2026, 10, 30)),
        (datetime(2026, 11, 2, 21, tzinfo=UTC), date(2026, 11, 2)),
        (datetime(2026, 11, 27, 17, 59, tzinfo=UTC), date(2026, 11, 25)),
        (datetime(2026, 11, 27, 18, tzinfo=UTC), date(2026, 11, 27)),
        (datetime(2026, 11, 28, 18, tzinfo=UTC), date(2026, 11, 27)),
        (datetime(2025, 1, 9, 22, tzinfo=UTC), date(2025, 1, 8)),
    ],
)
def test_service_asof_always_last_closed_session(db, now, expected):
    primary = FakeSource("tencent", [bar(expected), bar(expected + timedelta(days=1))])
    result = service(db, primary, now=now).refresh(["us:ZZAR"])
    assert result.as_of == expected
    assert primary.calls[0][1:] == (expected - timedelta(days=1095), expected)
    assert all(row[1] <= expected for row in prices(db))


def test_calendar_injection_changes_refresh_without_global_mutation(db, tmp_path):
    from sentinel.markets.prices.calendar import CALENDAR_PATH, is_trading_day

    custom = json.loads(CALENDAR_PATH.read_text())
    custom["holidays"].append({"date": "2026-11-02", "name": "synthetic closure"})
    path = tmp_path / "custom.json"
    path.write_text(json.dumps(custom))
    a = service(db, FakeSource("tencent", [bar()]), path=path)
    b = service(db, FakeSource("tencent", [bar()]))
    assert a.refresh([]).as_of == date(2026, 10, 30)
    assert b.refresh([]).as_of == date(2026, 11, 2)
    assert is_trading_day(date(2026, 11, 2))


def test_missing_params_only_unarchived_holding_and_empty_explicit_list(db):
    with db.write() as tx:
        for symbol, archived in (("ZZAR", None), ("ZZFD", NOW)):
            tx.execute(
                "INSERT INTO holding VALUES (?, ?, 0, NULL, NULL, ?, ?, ?)",
                [symbol, f"us:{symbol}", NOW, NOW, archived],
            )
    primary = FakeSource("tencent", [bar()])
    runner = service(db, primary)
    assert runner.refresh([]).updated == 0
    assert not primary.calls
    assert runner.refresh().updated == 1
    assert [call[0] for call in primary.calls] == ["ZZAR"]
    assert {row[0] for row in prices(db)} == {"us:ZZAR"}


def test_invalid_and_unknown_ids_are_individual_failures_with_wire_schema(db):
    result = service(db, FakeSource("tencent", [bar()])).refresh(
        ["us:zzar", "hk:ZZAR", "us:ZZMD", "us:ZZAR", "us:ZZAR"]
    )
    assert result.updated == 1
    assert [f.code for f in result.failed] == ["INVALID_ARGUMENT", "INVALID_ARGUMENT", "NOT_FOUND"]
    contract = json.loads((ROOT / "contracts/methods/prices.refresh.json").read_text())
    types = json.loads((ROOT / "contracts/types.schema.json").read_text())
    registry = Registry().with_resource("types.schema.json", Resource.from_contents(types))
    jsonschema.Draft202012Validator(contract["result"], registry=registry).validate(
        result.to_wire()
    )
    assert all(set(f["error"]) == {"code", "message"} for f in result.to_wire()["failed"])


@pytest.mark.parametrize(
    "data",
    [
        {"instrumentIds": None},
        {"instrumentIds": "us:ZZAR"},
        {"instrumentIds": [True]},
        {"instrumentIds": [""]},
        {"instrument_ids": ["us:ZZAR"]},
        {"extra": 1},
    ],
)
def test_params_reject_contract_invalid_shapes(data):
    from sentinel.markets.prices import RefreshParams

    with pytest.raises(UserError):
        RefreshParams.from_wire(data)


def test_params_roundtrip_and_noop_latest(db):
    from sentinel.markets.prices import RefreshParams

    assert RefreshParams.from_wire({}).to_wire() == {}
    assert RefreshParams.from_wire({"instrumentIds": []}).to_wire() == {"instrumentIds": []}
    seed(db, date(2026, 11, 2))
    primary = FakeSource("tencent")
    assert service(db, primary).refresh(["us:ZZAR"]).updated == 0
    assert not primary.calls


def test_no_http_in_database_context_short_transactions_and_timestamp(db, monkeypatch):
    from sentinel.markets.prices import PriceService

    writes = []
    original_write = db.write

    @contextmanager
    def tracked():
        writes.append("write")
        with original_write() as tx:
            yield tx

    monkeypatch.setattr(db, "write", tracked)

    def db_read():
        with db.read() as reader:
            reader.execute("SELECT 1")
            return reader.fetchone()

    class Checked(FakeSource):
        def fetch_daily(self, symbol, start, end):
            with ThreadPoolExecutor(max_workers=1) as pool:
                assert pool.submit(db_read).result(timeout=2) == (1,)
            assert not writes or len(writes) == 1
            return [bar()]

    times = iter([NOW, NOW + timedelta(seconds=1), NOW + timedelta(seconds=2)])
    runner = PriceService(
        db,
        Checked("tencent"),
        FakeSource("nasdaq"),
        ROOT / "resources/calendars/us.json",
        lambda: next(times),
    )
    assert runner.refresh(["us:ZZAR", "us:ZZFD"]).updated == 2
    assert len(writes) == 2
    with db.read() as reader:
        reader.execute("SELECT fetched_at FROM price_daily ORDER BY instrument_id")
        assert set(row[0] for row in reader.fetchall()) == {
            NOW + timedelta(seconds=1),
            NOW + timedelta(seconds=2),
        }


def test_write_failure_rolls_back_one_instrument_and_continues(db, monkeypatch):
    original = db.write
    calls = 0

    @contextmanager
    def failing():
        nonlocal calls
        calls += 1
        with original() as tx:
            if calls == 1:
                execute_many = tx.executemany

                def fail(sql, rows):
                    execute_many(sql, rows[:1])
                    raise duckdb.Error("synthetic mid-write failure")

                tx.executemany = fail
            yield tx

    monkeypatch.setattr(db, "write", failing)
    runner = service(db, FakeSource("tencent", [bar(date(2026, 10, 30)), bar()]))
    result = runner.refresh(["us:ZZAR", "us:ZZFD"])
    assert result.updated == 1
    assert result.failed[0].code == "INTERNAL"
    assert {row[0] for row in prices(db)} == {"us:ZZFD"}
    assert len(prices(db)) == 2


def test_maximum_250_rows_and_complete_backup_for_empty_database(db):
    from sentinel.markets.prices.calendar import TradingCalendar

    calendar = TradingCalendar(ROOT / "resources/calendars/us.json")
    day = date(2026, 11, 2)
    rows = []
    for _ in range(260):
        rows.append(bar(day))
        day = calendar.prev_trading_day(day)
    backup = FakeSource("nasdaq", list(reversed(rows)))
    result = service(db, FakeSource("tencent", [bar()]), backup).refresh(["us:ZZAR"])
    assert result.updated == 1
    assert len(prices(db)) == 250
    assert {row[3] for row in prices(db)} == {"nasdaq"}
    assert backup.calls[0][1:] == (date(2026, 11, 2) - timedelta(days=1095), date(2026, 11, 2))


def test_real_tencent_stale_history_filtered_and_nasdaq_clip_selected(db):
    from sentinel.markets.prices.nasdaq import NasdaqPriceSource
    from sentinel.markets.prices.tencent import TencentPriceSource

    with db.write() as tx:
        tx.execute(
            "INSERT INTO instrument VALUES ('us:AAPL', 'us', 'AAPL', 'NASDAQ', 'Apple', NULL, "
            "'USD', NULL, TRUE, 'sec_company_tickers', ?)",
            [NOW],
        )
    with (
        client(payload("prices_tencent_us.sample.json")) as a,
        client(payload("prices_nasdaq_us.sample.json")) as b,
    ):
        result = service(db, TencentPriceSource(a), NasdaqPriceSource(b)).refresh(["us:AAPL"])
    assert result.updated == 1
    assert len(prices(db)) == 30
    assert {row[3] for row in prices(db)} == {"nasdaq"}


def test_migration_is_exact_document_sql():
    content = (ROOT / "docs/04-数据模型.md").read_text()
    sql = content.split("### 3.5 `005_prices.sql`")[1].split("```sql\n")[1].split("```")[0]
    assert (ROOT / "core/sentinel/storage/migrations/005_prices.sql").read_text() == sql


@pytest.mark.parametrize("waits,expected", [((5, 17), 17), ((None, 12), 12), ((None, None), None)])
def test_dual_rate_limits_to_wire_and_schema(db, waits, expected):
    primary = FakeSource(
        "tencent",
        error=SourceError(
            "RATE_LIMITED", params={} if waits[0] is None else {"retryAfterSec": waits[0]}
        ),
    )
    backup = FakeSource(
        "nasdaq",
        error=SourceError(
            "RATE_LIMITED", params={} if waits[1] is None else {"retryAfterSec": waits[1]}
        ),
    )
    result = service(db, primary, backup).refresh(["us:ZZAR"])
    wire = result.to_wire()
    assert result.failed[0].retry_after_sec == expected
    error = wire["failed"][0]["error"]
    assert error["code"] == "RATE_LIMITED"
    assert error["message"] == (
        f"请求过于频繁，请在 {expected} 秒后重试。"
        if expected is not None
        else "行情源请求过于频繁，请稍后重试。"
    )
    assert set(wire["failed"][0]) == {"instrumentId", "error"}
    assert set(error) == {"code", "message"}
    contract = json.loads((ROOT / "contracts/methods/prices.refresh.json").read_text())
    types = json.loads((ROOT / "contracts/types.schema.json").read_text())
    registry = Registry().with_resource("types.schema.json", Resource.from_contents(types))
    jsonschema.Draft202012Validator(contract["result"], registry=registry).validate(wire)


def test_mock_http_dual_429_preserves_retry_after_to_wire(db):
    import httpx

    from sentinel.http.client import HttpClient
    from sentinel.markets.prices.nasdaq import NasdaqPriceSource
    from sentinel.markets.prices.tencent import TencentPriceSource

    calls = []
    elapsed = [200.0]

    def sleep(delay):
        elapsed[0] += delay

    def respond(request):
        calls.append(request)
        return httpx.Response(429, headers={"Retry-After": "7"})

    with HttpClient(
        transport=httpx.MockTransport(respond), sleeper=sleep, monotonic=lambda: elapsed[0]
    ) as http:
        result = service(db, TencentPriceSource(http), NasdaqPriceSource(http)).refresh(["us:ZZAR"])
    wire = result.to_wire()
    assert len(calls) == 6
    assert wire["failed"][0]["error"] == {
        "code": "RATE_LIMITED",
        "message": "请求过于频繁，请在 7 秒后重试。",
    }
    contract = json.loads((ROOT / "contracts/methods/prices.refresh.json").read_text())
    types = json.loads((ROOT / "contracts/types.schema.json").read_text())
    registry = Registry().with_resource("types.schema.json", Resource.from_contents(types))
    jsonschema.Draft202012Validator(contract["result"], registry=registry).validate(wire)


def test_refresh_failure_from_error_preserves_known_wait():
    from sentinel.markets.prices import RefreshFailure

    failure = RefreshFailure.from_error(
        "us:ZZAR", SourceError("RATE_LIMITED", reason="HTTP_429", params={"retryAfterSec": 4})
    )
    assert (failure.instrument_id, failure.code, failure.reason) == (
        "us:ZZAR",
        "RATE_LIMITED",
        "HTTP_429",
    )
    assert failure.retry_after_sec == 4
    assert failure.to_wire()["error"]["message"] == "请求过于频繁，请在 4 秒后重试。"
    assert RefreshFailure("us:ZZAR", "RATE_LIMITED", "HTTP_429").to_wire()["error"]["message"] == (
        "行情源请求过于频繁，请稍后重试。"
    )


@pytest.mark.parametrize("wait", [True, -1, float("nan"), float("inf"), "5"])
def test_invalid_retry_after_is_unknown_without_guessing(wait):
    from sentinel.markets.prices import RefreshFailure

    failure = RefreshFailure.from_error(
        "us:ZZAR", SourceError("RATE_LIMITED", params={"retryAfterSec": wait})
    )
    assert failure.retry_after_sec is None
    assert failure.to_wire()["error"]["message"] == "行情源请求过于频繁，请稍后重试。"
