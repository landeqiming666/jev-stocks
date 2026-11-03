from datetime import datetime, timedelta
from pathlib import Path

import pytest

from sentinel.errors import InternalError, SourceError, UserError
from sentinel.markets.instruments import (
    InstrumentRepository,
    InstrumentService,
    SearchResult,
    TickerRow,
)
from sentinel.storage import Database

from .conftest import NOW
from .test_repository import snapshot


class FakeSource:
    def __init__(self, rows: list[TickerRow] | Exception) -> None:
        self.rows = rows
        self.calls = 0

    def fetch(self) -> list[TickerRow]:
        self.calls += 1
        if isinstance(self.rows, Exception):
            raise self.rows
        return self.rows


def test_search_scores_exact_symbol_highest(repo: InstrumentRepository) -> None:
    rows = [TickerRow("1", "Berkshire", "BRK-B", "NYSE"), TickerRow("2", "BRK B", "OTHER", "NYSE")]
    repo.replace_from_sec(rows, fetched_at=NOW)
    source = FakeSource([])
    hits = InstrumentService(repo, source, lambda: NOW).search("ＢＲＫ．Ｂ")
    assert [(h.instrument.instrument_id, h.score) for h in hits] == [
        ("us:BRK.B", 120),
        ("us:OTHER", 100),
    ]
    wire = SearchResult.from_hits(hits).to_wire()
    assert set(wire) == {"items"}
    assert set(wire["items"][0]) == {
        "instrumentId",
        "market",
        "symbol",
        "name",
        "nameZh",
        "exchange",
        "currency",
        "isActive",
    }
    assert wire["items"][0]["isActive"] is True
    assert source.calls == 0


def test_search_chinese_alias_and_sort(repo: InstrumentRepository) -> None:
    rows = [
        TickerRow("1", "Apple", "AAPL", "Nasdaq"),
        TickerRow("2", "Apple Corp", "ABC", "NYSE"),
        TickerRow("3", "Example Apple", "ZXY", "CBOE"),
    ]
    repo.replace_from_sec(rows, fetched_at=NOW)
    service = InstrumentService(repo, FakeSource([]), lambda: NOW)
    assert [(h.instrument.symbol, h.score) for h in service.search("苹果")] == [("AAPL", 100)]
    assert service.search("苹果公司")[0].score == 100
    assert [(h.instrument.symbol, h.score) for h in service.search("a", 2)] == [
        ("AAPL", 80),
        ("ABC", 80),
    ]
    assert [(h.instrument.symbol, h.score) for h in service.search("apple")] == [
        ("AAPL", 100),
        ("ABC", 60),
        ("ZXY", 30),
    ]
    assert service.search("%' OR 1=1 --") == []
    assert service.search("a_%")[0].score == 80


@pytest.mark.parametrize("offline,email", [(False, False), (True, True), (True, False)])
def test_ensure_fresh_skips_without_email(
    repo: InstrumentRepository, offline: bool, email: bool
) -> None:
    source = FakeSource([])
    assert (
        InstrumentService(repo, source, lambda: NOW).ensure_fresh(
            offline=offline, has_sec_email=email
        )
        is None
    )
    assert source.calls == 0


@pytest.mark.parametrize(
    "age,fetches",
    [
        (timedelta(days=7) - timedelta(microseconds=1), 0),
        (timedelta(days=7), 0),
        (timedelta(days=7, microseconds=1), 1),
    ],
)
def test_strict_seven_days(repo: InstrumentRepository, age: timedelta, fetches: int) -> None:
    rows = [TickerRow("1", "Apple", "AAPL", "Nasdaq")]
    repo.replace_from_sec(rows, fetched_at=NOW)
    source = FakeSource(rows)
    InstrumentService(repo, source, lambda: NOW + age).ensure_fresh(
        offline=False, has_sec_email=True
    )
    assert source.calls == fetches


@pytest.mark.parametrize("old", [False, True])
@pytest.mark.parametrize(
    "failure",
    [
        SourceError("SOURCE_UNAVAILABLE", reason="TICKER_SCHEMA"),
        SourceError("RATE_LIMITED", params={"retryAfterSec": 2}),
        [],
    ],
)
def test_network_failure_and_empty_keep_watermark(
    repo: InstrumentRepository,
    db: Database,
    old: bool,
    failure: object,
    caplog: pytest.LogCaptureFixture,
) -> None:
    if old:
        repo.replace_from_sec([TickerRow("1", "Apple", "AAPL", "Nasdaq")], fetched_at=NOW)
    before = snapshot(db)
    source = FakeSource(failure)
    assert (
        InstrumentService(repo, source, lambda: NOW + timedelta(days=8)).ensure_fresh(
            offline=False, has_sec_email=True
        )
        is None
    )
    assert snapshot(db) == before and source.calls == 1
    assert any(
        getattr(r, "sentinel", {}).get("event")
        in {"instruments.refresh_failed", "instruments.refresh_empty"}
        for r in caplog.records
    )


def test_refreshes_empty_table_even_with_watermark(repo: InstrumentRepository) -> None:
    repo.replace_from_sec([], fetched_at=NOW)
    source = FakeSource([TickerRow("1", "Apple", "AAPL", "Nasdaq")])
    result = InstrumentService(repo, source, lambda: NOW).ensure_fresh(
        offline=False, has_sec_email=True
    )
    assert result.kept == 1 and source.calls == 1


def test_internal_errors_are_not_network_failures(
    repo: InstrumentRepository, alias_path: Path, db: Database
) -> None:
    rows = [TickerRow("1", "Apple", "AAPL", "Nasdaq")]
    repo.replace_from_sec(rows, fetched_at=NOW)
    before = snapshot(db)
    alias_path.write_text("broken")
    with pytest.raises(InternalError):
        InstrumentService(repo, FakeSource(rows), lambda: NOW + timedelta(days=8)).ensure_fresh(
            offline=False, has_sec_email=True
        )
    assert snapshot(db) == before
    with pytest.raises(InternalError):
        InstrumentService(
            repo, FakeSource(InternalError()), lambda: NOW + timedelta(days=8)
        ).ensure_fresh(offline=False, has_sec_email=True)
    with db.write() as tx:
        tx.execute("DROP TABLE instrument")
    with pytest.raises(InternalError):
        InstrumentService(repo, FakeSource(rows), lambda: NOW + timedelta(days=8)).ensure_fresh(
            offline=False, has_sec_email=True
        )


def test_email_changed_to_missing_during_refresh(repo: InstrumentRepository) -> None:
    source = FakeSource(UserError("CONFIG_REQUIRED", params={"missing": ["secEmail"]}))
    assert (
        InstrumentService(repo, source, lambda: NOW).ensure_fresh(offline=False, has_sec_email=True)
        is None
    )


@pytest.mark.parametrize("value", [datetime(2026, 11, 3), True, None])
def test_invalid_clock(repo: InstrumentRepository, value: object) -> None:
    with pytest.raises(InternalError):
        InstrumentService(repo, FakeSource([]), lambda: value).ensure_fresh(
            offline=False, has_sec_email=True
        )


@pytest.mark.parametrize("old", [False, True])
@pytest.mark.parametrize(
    "rows",
    [
        [TickerRow("1", "Bad ticker", "A_%", "NYSE")],
        [TickerRow("bad", "Bad CIK", "X", "NYSE")],
        [TickerRow("1", "OTC", "X", "OTC")],
        [TickerRow("1", "Null exchange", "X", None)],
    ],
)
def test_background_all_filtered_preserves_table_and_watermark(
    repo: InstrumentRepository,
    db: Database,
    old: bool,
    rows: list[TickerRow],
    caplog: pytest.LogCaptureFixture,
) -> None:
    if old:
        repo.replace_from_sec([TickerRow("1", "Apple", "AAPL", "Nasdaq")], fetched_at=NOW)
    before = snapshot(db)
    source = FakeSource(rows)
    service = InstrumentService(repo, source, lambda: NOW + timedelta(days=8))
    assert service.ensure_fresh(offline=False, has_sec_email=True) is None
    assert source.calls == 1 and snapshot(db) == before
    events = [getattr(record, "sentinel", {}) for record in caplog.records]
    assert any(
        event.get("event") == "instruments.refresh_failed"
        and event.get("reason") == "TICKER_SCHEMA"
        and event.get("error_code") == "SOURCE_UNAVAILABLE"
        for event in events
    )
