from __future__ import annotations

import threading
import time
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any, cast

import pytest

from sentinel import clock
from sentinel.errors import EngineError, SentinelError
from sentinel.markets.instruments.models import Instrument
from sentinel.markets.sec import EventFileDraft, FetchedEvent, FilingRef, SecFilingsRepository
from sentinel.portfolio.service import PortfolioService
from sentinel.scan.orchestrator import ScanService
from sentinel.scan.passages import persist_passages
from sentinel.semantic.pipeline import BatchOutcome, DecisionPipeline
from sentinel.settings.models import MODEL_ID, SettingsPatch
from sentinel.settings.repository import SettingsRepository
from sentinel.settings.service import SettingsService
from sentinel.storage.db import Database

NOW = datetime(2026, 11, 3, tzinfo=UTC)
INSTRUMENT = Instrument(
    "us:ZZAR",
    "us",
    "ZZAR",
    "NASDAQ",
    "Zenith Arc Robotics Inc.",
    None,
    "USD",
    "0001234567",
    True,
)


@pytest.fixture
def db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Database]:
    monkeypatch.setenv("SENTINEL_CLOCK", clock.to_iso(NOW))
    monkeypatch.delenv("SENTINEL_OFFLINE", raising=False)
    value = Database(tmp_path / "scan.duckdb")
    value.open()
    value.migrate()
    # 红灯时 008 尚未交付；只在表缺失时使用权威 DDL fixture。
    with value.read() as reader:
        reader.execute("SELECT 1 FROM information_schema.tables WHERE table_name='scan_run'")
        missing = reader.fetchone() is None
    if missing:
        source = Path(__file__).resolve().parents[4] / "docs/04-数据模型.md"
        text = source.read_text().split("### 3.8 ")[1].split("```sql\n")[1].split("```")[0]
        with value.write() as tx:
            tx.execute(text)
    with value.write() as tx:
        tx.execute(
            "INSERT INTO instrument VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [*INSTRUMENT.__dict__.values(), NOW, NOW],
        )
    yield value
    value.close()


def event(number: int = 1, text: str | None = "Synthetic disclosure.") -> FetchedEvent:
    accession = f"0001234567-26-{number:06d}"
    url = f"https://www.sec.gov/Archives/edgar/data/1234567/{accession.replace('-', '')}/main.htm"
    ref = FilingRef(
        "us:" + accession,
        INSTRUMENT.instrument_id,
        INSTRUMENT.cik or "",
        accession,
        "8-K",
        NOW - timedelta(hours=number),
        NOW.date(),
        None,
        "main.htm",
        "Synthetic",
    )
    file = EventFileDraft(
        0,
        "main.htm",
        "8-K",
        url,
        "extracted" if text else "empty",
        text,
        len(text) if text is not None else None,
    )
    return FetchedEvent(ref, [file], "full_text" if text else "title_only", "", NOW)


class Filings:
    def __init__(self, database: Database) -> None:
        self.repo = SecFilingsRepository(database)
        self.events = [event()]
        self.entered, self.release = threading.Event(), threading.Event()
        self.block = False
        self.calls = 0
        self.error: Exception | None = None

    def fetch_for_instrument(
        self, instrument: Instrument, *, since: datetime, until: datetime
    ) -> Any:
        self.calls += 1
        self.entered.set()
        if self.block:
            assert self.release.wait(3)
        if self.error:
            raise self.error
        for row in self.events:
            self.repo.upsert(row)
        return self.events


class Pipeline:
    def __init__(self, database: Database) -> None:
        self.db = database
        self.engine = type("SyntheticEngine", (), {"name": "jev_direct"})()
        self.model_id = MODEL_ID
        self.daily_budget = 2_000_000
        self.calls: list[str] = []
        self.errors: dict[str, Exception] = {}
        self.after: Any = None

    def process_batch(self, ctx: Any, theses: Any, passages: Any, cancel: Any) -> Any:
        cancel.raise_if_cancelled()
        self.calls.append(ctx.event_id)
        if ctx.event_id in self.errors:
            raise self.errors[ctx.event_id]
        if self.after:
            self.after()
        return BatchOutcome("succeeded", 0, 0, 0, 0, 0, False)


@pytest.fixture
def stack(db: Database) -> Any:
    portfolio = PortfolioService(db)
    portfolio.upsert_holding(INSTRUMENT.instrument_id, Decimal("0"), None, None)
    portfolio.create_thesis(INSTRUMENT.instrument_id, "Synthetic thesis.", None)
    settings = SettingsService(SettingsRepository(db), clock.now)
    settings.update(SettingsPatch(sec_contact_email="synthetic@example.invalid"))
    filings, pipeline = Filings(db), Pipeline(db)
    notices: list[tuple[str, dict[str, object]]] = []
    service = ScanService(
        db,
        settings_provider=settings.get,
        key_provider=lambda: True,
        holdings_provider=portfolio,
        instrument_provider=lambda _: INSTRUMENT,
        filings=filings,
        pipeline_resolver=lambda _: cast(DecisionPipeline, pipeline),
        emit=lambda name, payload: notices.append((name, payload)),
    )
    yield service, filings, pipeline, portfolio, settings, notices
    filings.release.set()
    service.wait_idle(3)


def finish(service: ScanService, run_id: str) -> Any:
    assert service.wait_idle(3)
    return service.detail(run_id)


def test_start_returns_before_fetch_completes(stack: Any) -> None:
    service, filings, *_ = stack
    filings.block = True
    started = time.monotonic()
    run_id = service.start("us")
    assert time.monotonic() - started < 0.05 and len(run_id) == 26
    assert filings.entered.wait(2)
    assert service.status(run_id).status == "running"
    filings.release.set()
    assert finish(service, run_id).run.status == "succeeded"


def test_second_start_same_market_conflicts(stack: Any) -> None:
    service, filings, *_ = stack
    filings.block = True
    service.start("us")
    assert filings.entered.wait(2)
    with pytest.raises(SentinelError, match="CONFLICT"):
        service.start("us")


def test_batch_failure_does_not_stop_other_batches(stack: Any) -> None:
    service, filings, pipeline, *_ = stack
    filings.events = [event(3), event(2), event(1)]
    pipeline.errors[event(2).event.event_id] = EngineError("MODEL_ERROR")
    result = finish(service, service.start("us"))
    assert result.run.status == "partial"
    assert [b.status for b in result.batches] == ["succeeded", "failed", "succeeded"]


def test_no_successful_batch_marks_run_failed(stack: Any) -> None:
    service, _, pipeline, *_ = stack
    pipeline.errors[event().event.event_id] = EngineError("MODEL_ERROR")
    run = finish(service, service.start("us")).run
    assert run.status == "failed" and run.finished_at is not None


def test_budget_exhaustion_leaves_batch_pending(stack: Any) -> None:
    service, filings, pipeline, *_ = stack
    filings.events = [event(3), event(2), event(1)]
    pipeline.errors[event(2).event.event_id] = EngineError("BUDGET_EXCEEDED")
    result = finish(service, service.start("us"))
    assert result.run.status == "partial"
    assert [b.status for b in result.batches] == ["succeeded", "pending", "pending"]
    assert len(pipeline.calls) == 2


def test_cancel_keeps_committed_batches(stack: Any) -> None:
    service, filings, pipeline, *_ = stack
    filings.events = [event(3), event(2), event(1)]
    entered, release = threading.Event(), threading.Event()

    def second() -> None:
        if len(pipeline.calls) == 2:
            entered.set()
            assert release.wait(3)

    pipeline.after = second
    run_id = service.start("us")
    assert entered.wait(2)
    service.cancel(run_id)
    release.set()
    result = finish(service, run_id)
    assert result.run.status == "cancelled" and result.batches[0].status == "succeeded"
    assert result.batches[1].status != "succeeded" and len(pipeline.calls) == 2


def test_startup_marks_running_interrupted(stack: Any, db: Any) -> None:
    service, filings, *_ = stack
    filings.events = []
    first = service.start("us")
    finish(service, first)
    second = service.start("us")
    finish(service, second)
    with db.write() as tx:
        tx.execute(
            ("UPDATE scan_run SET status=CASE WHEN run_id=? THEN 'queued' ELSE 'running' END"),
            [first],
        )
    assert service.recover_on_startup() == 2
    assert all(r.status == "interrupted" and r.finished_at for r in service.history().items)


def test_retry_failed_batch_updates_run_to_succeeded(stack: Any) -> None:
    service, filings, pipeline, *_ = stack
    filings.events = [event(2), event(1)]
    pipeline.errors[event().event.event_id] = EngineError("MODEL_ERROR")
    result = finish(service, service.start("us"))
    assert result.run.status == "partial"
    pipeline.errors.clear()
    retried = service.retry_batch(result.batches[1].batch_id)
    assert retried.status == "succeeded" and retried.attempts == 2
    assert service.status(result.run.run_id).status == "succeeded"


def test_same_event_is_not_duplicated_within_run(stack: Any) -> None:
    service, filings, *_ = stack
    filings.events = [event(), event()]
    assert len(finish(service, service.start("us")).batches) == 1


def test_persist_passages_is_idempotent(db: Any) -> None:
    row = event()
    SecFilingsRepository(db).upsert(row)
    assert persist_passages(db, row) == persist_passages(db, row)
    with db.read() as reader:
        reader.execute("SELECT COUNT(*) FROM event_passage")
        assert reader.fetchone() == (1,)


def test_event_without_text_succeeds_with_zero_passages(stack: Any) -> None:
    service, filings, pipeline, *_ = stack
    filings.events = [event(text=None)]
    result = finish(service, service.start("us"))
    assert result.run.status == "succeeded" and result.run.stats.passages == 0
    assert pipeline.calls == []


@pytest.mark.parametrize("key,email", [(False, False), (False, True), (True, False)])
def test_missing_configuration_creates_no_run(stack: Any, key: bool, email: bool) -> None:
    service, filings, _, _, settings, _ = stack
    service.key_provider = lambda: key
    if not email:
        settings.update(SettingsPatch(sec_contact_email=None))
    with pytest.raises(SentinelError) as error:
        service.start("us")
    assert error.value.code == "CONFIG_REQUIRED"
    assert error.value.params["missing"] == ([] if key else ["jevKey"]) + (
        [] if email else ["secEmail"]
    )
    assert service.history().items == [] and filings.calls == 0


def test_offline_guard_blocks_resolver_and_filings(
    stack: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    service, filings, *_ = stack
    service.pipeline_resolver = lambda _: pytest.fail("offline resolver must not run")
    monkeypatch.setenv("SENTINEL_OFFLINE", "1")
    with pytest.raises(SentinelError, match="SOURCE_UNAVAILABLE"):
        service.start("us")
    assert not service.history().items and filings.calls == 0


def test_no_automatic_scan_on_construction_and_recovery(stack: Any) -> None:
    service, filings, *_ = stack
    assert service.recover_on_startup() == 0
    assert filings.calls == 0 and service.history().items == []


def test_cross_handle_concurrent_starts_only_one_wins(stack: Any, db: Database) -> None:
    from concurrent.futures import ThreadPoolExecutor

    service, filings, *_ = stack
    filings.block = True
    other_db = Database(db.path)
    other_db.open()
    other = clone(service, other_db)
    barrier = threading.Barrier(2)

    def start(s: ScanService) -> str:
        barrier.wait(2)
        try:
            return s.start("us")
        except SentinelError as error:
            return error.code.value

    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(start, [service, other]))
        assert results.count("CONFLICT") == 1
        assert filings.entered.wait(2)
        other.cancel(next(r for r in results if r != "CONFLICT"))
        filings.release.set()
        assert service.wait_idle(3)
        assert len(service.history().items) == 1
        assert service.history().items[0].status == "cancelled"
    finally:
        filings.release.set()
        service.wait_idle(3)
        other_db.close()


def clone(service: ScanService, db: Database) -> ScanService:
    return ScanService(
        db,
        settings_provider=service.settings_provider,
        key_provider=service.key_provider,
        holdings_provider=service.holdings,
        instrument_provider=service.instrument_provider,
        filings=service.filings,
        pipeline_resolver=service.pipeline_resolver,
    )


def test_fetch_failure_does_not_advance_watermark_and_is_sanitized(
    stack: Any, db: Database
) -> None:
    from sentinel.errors import SourceError
    from sentinel.scan.watermark import read_watermark

    service, filings, *_ = stack
    filings.error = SourceError("SOURCE_UNAVAILABLE", detail="synthetic-key secret body")
    run = finish(service, service.start("us")).run
    assert run.status == "failed" and run.error.code == "SOURCE_UNAVAILABLE"
    assert read_watermark(db, "us") is None
    assert "synthetic-key" not in run.model_dump_json()


def test_one_issuer_failure_keeps_other_success_and_watermark_unchanged(
    stack: Any, db: Database
) -> None:
    from sentinel.errors import SourceError
    from sentinel.scan.watermark import read_watermark

    service, filings, pipeline, portfolio, *_ = stack
    from dataclasses import replace

    second = replace(INSTRUMENT, instrument_id="us:ZZFD", symbol="ZZFD", name="Zephyr Foods Corp.")
    with db.write() as tx:
        tx.execute(
            "INSERT INTO instrument VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            [*second.__dict__.values(), NOW, NOW],
        )
    portfolio.upsert_holding(second.instrument_id, Decimal("0"), None, None)
    portfolio.create_thesis(second.instrument_id, "Synthetic second thesis.", None)
    filings.events = [event(2), event(1)]
    pipeline.errors[event(1).event.event_id] = EngineError("MODEL_ERROR")
    original = filings.fetch_for_instrument

    def fetch(i: Instrument, *, since: datetime, until: datetime) -> Any:
        if i.instrument_id == second.instrument_id:
            raise SourceError("TIMEOUT")
        return original(i, since=since, until=until)

    filings.fetch_for_instrument = fetch
    service.instrument_provider = lambda i: INSTRUMENT if i == INSTRUMENT.instrument_id else second
    result = finish(service, service.start("us"))
    assert result.run.status == "partial" and result.batches[0].status == "succeeded"
    assert result.run.stats.instruments == 2 and read_watermark(db, "us") is None
    pipeline.errors.clear()
    assert service.retry_batch(result.batches[1].batch_id).status == "succeeded"
    assert service.status(result.run.run_id).status == "partial"


def test_new_run_retries_old_failure_once_then_success_supersedes_history(stack: Any) -> None:
    service, filings, pipeline, *_ = stack
    pipeline.errors[event().event.event_id] = EngineError("MODEL_ERROR")
    original = finish(service, service.start("us"))
    assert original.batches[0].status == "failed"
    filings.events = []
    pipeline.errors.clear()
    retried = finish(service, service.start("us"))
    assert len(retried.batches) == 1 and retried.batches[0].status == "succeeded"
    for _ in range(3):
        assert finish(service, service.start("us")).batches == []
    assert len(pipeline.calls) == 2
    assert service.detail(original.run.run_id).batches[0].status == "failed"


def test_budget_pending_is_merged_into_next_run(stack: Any) -> None:
    service, filings, pipeline, *_ = stack
    filings.events = [event(2), event(1)]
    pipeline.errors[event(2).event.event_id] = EngineError("BUDGET_EXCEEDED")
    first = finish(service, service.start("us"))
    assert all(b.status == "pending" for b in first.batches)
    filings.events = []
    pipeline.errors.clear()
    second = finish(service, service.start("us"))
    assert len(second.batches) == 2 and second.run.status == "succeeded"


def test_retries_older_than_thirty_days_are_not_merged(stack: Any, db: Database) -> None:
    service, filings, pipeline, *_ = stack
    pipeline.errors[event().event.event_id] = EngineError("MODEL_ERROR")
    first = finish(service, service.start("us"))
    with db.write() as tx:
        tx.execute(
            "UPDATE scan_run SET created_at=? WHERE run_id=?",
            [NOW - timedelta(days=31), first.run.run_id],
        )
    filings.events = []
    assert finish(service, service.start("us")).batches == []


def test_real_pipeline_new_version_and_full_cache_have_exact_usage(
    stack: Any, db: Database
) -> None:
    from sentinel.semantic.base import SemanticEngine
    from sentinel.semantic.pipeline import DecisionPipeline
    from tests.unit.semantic.test_pipeline import Engine

    service, _, _, portfolio, *_ = stack
    engine = Engine()
    pipeline = DecisionPipeline(
        db, cast(SemanticEngine, engine), model_id=MODEL_ID, daily_budget=2_000_000
    )
    service.pipeline_resolver = lambda _: pipeline
    first = finish(service, service.start("us")).run
    second = finish(service, service.start("us")).run
    assert first.stats.decisions == first.stats.requests == 1 and first.stats.input_tokens == 10
    assert second.stats.decisions == second.stats.requests == second.stats.input_tokens == 0
    assert second.stats.cached_decisions == 1 and second.stats.est_cost_usd == "0.000000"
    thesis = portfolio.list_active_theses(INSTRUMENT.instrument_id)[0]
    portfolio.update_thesis(thesis.thesis_id, "Changed synthetic thesis.", None, 1)
    third = finish(service, service.start("us")).run
    assert third.stats.decisions == third.stats.requests == 1 and len(engine.pairs) == 2


@pytest.mark.parametrize("stage", ["score", "evidence", "parse"])
def test_cancel_at_each_stage_keeps_only_committed_usage(
    stack: Any, db: Database, monkeypatch: pytest.MonkeyPatch, stage: str
) -> None:
    import sentinel.scan.orchestrator as module
    from sentinel.semantic.base import SemanticEngine
    from sentinel.semantic.pipeline import DecisionPipeline
    from tests.unit.semantic.test_pipeline import OVERTURN, Engine

    service, _, _, _, _, _ = stack
    engine = Engine()
    engine.probabilities = OVERTURN
    entered, release = threading.Event(), threading.Event()

    def block() -> None:
        entered.set()
        assert release.wait(3)

    if stage == "score":
        engine.after_score = block
    elif stage == "evidence":
        engine.after_evidence = block
    else:
        from sentinel.scan.passages import persist_passages

        original = persist_passages

        def parse(*args: Any) -> Any:
            block()
            return original(*args)

        monkeypatch.setattr(module, "persist_passages", parse)
    pipeline = DecisionPipeline(
        db, cast(SemanticEngine, engine), model_id=MODEL_ID, daily_budget=2_000_000
    )
    service.pipeline_resolver = lambda _: pipeline
    run_id = service.start("us")
    assert entered.wait(2)
    service.cancel(run_id)
    release.set()
    result = finish(service, run_id)
    assert result.run.status == "cancelled" and result.batches[0].status != "succeeded"
    if stage == "evidence":
        assert result.run.stats.decisions == result.run.stats.requests == 1
        assert result.run.stats.input_tokens == 10
        engine.after_evidence = None
        resumed = finish(service, service.start("us", NOW - timedelta(days=7)))
        assert resumed.run.stats.input_tokens == resumed.run.stats.requests == 0
        assert resumed.run.stats.cached_decisions == 1
        with db.read() as reader:
            reader.execute("SELECT evidence_kind FROM decision")
            assert reader.fetchone() == ("passage",)
    else:
        assert (
            result.run.stats.decisions
            == result.run.stats.requests
            == result.run.stats.input_tokens
            == 0
        )


def test_retry_timeout_is_bounded_and_keeps_mutex_until_external_call_returns(
    stack: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    from concurrent.futures import ThreadPoolExecutor

    import sentinel.scan.orchestrator as module

    service, _, pipeline, *_ = stack
    pipeline.errors[event().event.event_id] = EngineError("MODEL_ERROR")
    batch = finish(service, service.start("us")).batches[0]
    pipeline.errors.clear()
    entered, release = threading.Event(), threading.Event()

    def block() -> None:
        entered.set()
        assert release.wait(3)

    pipeline.after = block
    monkeypatch.setattr(module, "RETRY_TIMEOUT_SECONDS", 0.1)
    try:
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(service.retry_batch, batch.batch_id)
            assert entered.wait(2)
            with pytest.raises(SentinelError, match="TIMEOUT"):
                future.result(timeout=1)
            with pytest.raises(SentinelError, match="CONFLICT"):
                service.start("us")
            assert not service.wait_idle(0.01)
            release.set()
        assert service.wait_idle(3)
        updated = service.detail(batch.run_id).batches[0]
        assert updated.status == "failed" and updated.error.code == "TIMEOUT"
    finally:
        release.set()


def test_request_cancel_during_retry_shared_mutex_and_terminal_state(
    stack: Any, db: Database
) -> None:
    from concurrent.futures import ThreadPoolExecutor

    from sentinel.rpc.cancel import CancelToken

    service, _, pipeline, *_ = stack
    pipeline.errors[event().event.event_id] = EngineError("MODEL_ERROR")
    batch = finish(service, service.start("us")).batches[0]
    pipeline.errors.clear()
    entered, release = threading.Event(), threading.Event()

    def block() -> None:
        entered.set()
        assert release.wait(3)

    pipeline.after = block
    token = CancelToken()
    try:
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(service.retry_batch, batch.batch_id, token)
            assert entered.wait(2)
            with pytest.raises(SentinelError, match="CONFLICT"):
                service.before_config_change()
            with pytest.raises(SentinelError, match="CONFLICT"):
                service.retry_batch(batch.batch_id)
            token.cancel()
            with pytest.raises(SentinelError, match="CANCELLED"):
                future.result(timeout=1)
            release.set()
        assert service.wait_idle(3)
        assert service.detail(batch.run_id).batches[0].status == "cancelled"
        assert service.status(batch.run_id).status == "failed"
    finally:
        release.set()


def test_history_cursor_same_timestamp_has_no_gap_or_duplicates(stack: Any) -> None:
    service, filings, *_ = stack
    filings.events = []
    ids = [finish(service, service.start("us")).run.run_id for _ in range(7)]
    seen: list[str] = []
    cursor = None
    while True:
        page = service.history(2, cursor)
        seen.extend(r.run_id for r in page.items)
        cursor = page.next_cursor
        if cursor is None:
            break
    assert seen == sorted(ids, reverse=True)
    assert page.budget.reset_at == "2026-11-04T00:00:00Z"


@pytest.mark.parametrize("cursor", ["", "junk", "a" * 300, "!!!"])
def test_bad_cursor_is_safe_invalid_argument(stack: Any, cursor: str) -> None:
    service, *_ = stack
    with pytest.raises(SentinelError) as error:
        service.history(cursor=cursor)
    assert error.value.code == "INVALID_ARGUMENT" and error.value.field == "cursor"


def test_live_resolver_uses_changed_engine_and_budget_and_guard_rejects_active_changes(
    stack: Any,
) -> None:
    service, filings, pipeline, _, settings, _ = stack
    snapshots = []

    def resolve(current: Any) -> Any:
        snapshots.append((current.engine, current.daily_token_budget))
        pipeline.engine.name = "jevdb" if current.engine == "jevdb" else "jev_direct"
        pipeline.daily_budget = current.daily_token_budget
        return pipeline

    service.pipeline_resolver = resolve
    filings.events = []
    finish(service, service.start("us"))
    service.before_config_change()
    settings.update(SettingsPatch(engine="jevdb", daily_token_budget=20_000))
    assert finish(service, service.start("us")).run.engine == "jevdb"
    assert snapshots == [("auto", 2_000_000), ("jevdb", 20_000)]
    filings.block = True
    service.start("us")
    assert filings.entered.wait(2)
    with pytest.raises(SentinelError, match="CONFLICT"):
        service.before_config_change()
    assert settings.get().engine == "jevdb"


def test_aggregate_cost_uses_total_tokens_once(stack: Any, db: Database) -> None:
    from sentinel.semantic.base import SemanticEngine
    from sentinel.semantic.pipeline import DecisionPipeline
    from tests.unit.semantic.test_pipeline import Engine

    service, filings, *_ = stack
    filings.events = [event(2), event(1)]
    engine = Engine()
    service.pipeline_resolver = lambda _: DecisionPipeline(
        db, cast(SemanticEngine, engine), model_id=MODEL_ID, daily_budget=2_000_000
    )
    result = finish(service, service.start("us")).run
    assert result.stats.input_tokens == 20 and result.stats.requests == 2
    assert result.stats.est_cost_usd == "0.000001"


@pytest.mark.parametrize(
    "method",
    ["scan.start", "scan.cancel", "scan.status", "scan.history", "scan.detail", "scan.retryBatch"],
)
def test_six_rpc_models_roundtrip_authoritative_examples(stack: Any, method: str) -> None:
    from sentinel.rpc import Dispatcher
    from sentinel.scan.rpc import register_handlers
    from tests.unit.portfolio.test_handlers import Contract

    service, *_ = stack
    dispatcher = Dispatcher()
    register_handlers(dispatcher, service)
    assert len(dispatcher.methods()) == 6
    spec = dispatcher.lookup(method)
    contract = Contract(method)
    assert spec is not None and spec.result_model is not None
    assert spec.cancellable == (method == "scan.retryBatch")
    for example in contract.document["examples"]:
        contract.params.validate(example["params"])
        spec.params_model.model_validate(example["params"], by_alias=True, by_name=False)
        if "result" in example:
            parsed = spec.result_model.model_validate(example["result"])
            contract.result.validate(parsed.model_dump(mode="json", by_alias=True))
            assert parsed.model_dump(mode="json", by_alias=True) == example["result"]


def test_actual_six_rpc_handlers_and_notifications_pass_machine_contracts(stack: Any) -> None:
    import json

    from jsonschema import Draft202012Validator  # type: ignore[import-untyped]

    from sentinel.rpc import CancelToken, Dispatcher
    from sentinel.rpc.dispatcher import RequestContext
    from sentinel.rpc.protocol import serialize
    from sentinel.scan.rpc import register_handlers
    from tests.unit.portfolio.test_handlers import CONTRACTS, REGISTRY, Contract

    service, filings, pipeline, _, _, notices = stack
    dispatcher = Dispatcher()
    register_handlers(dispatcher, service)

    def call(method: str, params: dict[str, object]) -> dict[str, Any]:
        response = dispatcher.dispatch(
            dispatcher.lookup(method), params, RequestContext("rpc-p02", method, CancelToken(), NOW)
        )
        decoded = json.loads(serialize(response))
        contract = Contract(method)
        assert "result" in decoded, decoded
        contract.result.validate(decoded["result"])
        return cast(dict[str, Any], decoded["result"])

    pipeline.errors[event().event.event_id] = EngineError("MODEL_ERROR")
    run_id = call("scan.start", {"market": "us"})["runId"]
    finish(service, run_id)
    call("scan.status", {"runId": run_id})
    call("scan.history", {})
    batch = call("scan.detail", {"runId": run_id})["batches"][0]
    pipeline.errors.clear()
    assert call("scan.retryBatch", {"batchId": batch["batchId"]})["status"] == "succeeded"
    assert call("scan.cancel", {"runId": run_id}) == {"ok": True}
    for invalid in [{"run_id": run_id}, {"runId": run_id, "run_id": run_id}]:
        result = dispatcher.dispatch(
            dispatcher.lookup("scan.status"),
            invalid,
            RequestContext("bad", "scan.status", CancelToken(), NOW),
        )
        assert cast(dict[str, Any], result["error"])["code"] == "INVALID_ARGUMENT"
    document = json.loads((CONTRACTS / "notifications.json").read_text())
    for name, payload in notices:
        Draft202012Validator(document[name]["params"], registry=REGISTRY).validate(payload)
    assert sum(name == "scan.finished" for name, _ in notices) == 1


def test_progress_throttles_at_five_hundred_ms_and_finished_is_last(stack: Any) -> None:
    service, filings, pipeline, _, _, _ = stack
    filings.events = [event(2), event(1)]
    recorded = []
    service.emit = lambda name, payload: recorded.append((name, time.monotonic(), payload))
    entered, release = threading.Event(), threading.Event()

    def block() -> None:
        if len(pipeline.calls) == 1:
            entered.set()
            assert release.wait(3)

    pipeline.after = block
    run_id = service.start("us")
    assert entered.wait(2)
    time.sleep(0.52)
    release.set()
    finish(service, run_id)
    moments = [stamp for name, stamp, _ in recorded if name == "scan.progress"]
    assert len(moments) >= 2
    assert all(b - a >= 0.5 for a, b in zip(moments, moments[1:], strict=False))
    assert recorded[-1][0] == "scan.finished"


def test_actual_settings_rpc_guard_preserves_configuration_and_key(
    stack: Any, db: Database
) -> None:
    from sentinel.rpc import CancelToken, Dispatcher
    from sentinel.rpc.dispatcher import RequestContext
    from sentinel.secrets import MemorySecretStore, SecretsService
    from sentinel.settings.models import EngineSnapshot
    from sentinel.settings.rpc import register
    from tests.unit.settings.conftest import FakeProbe

    service, filings, _, _, settings, _ = stack
    secrets = SecretsService(MemorySecretStore(), clock.now)
    secrets.set_jev_key("synthetic-guard-key")
    service.key_provider = lambda: secrets.status()["jevKey"]
    dispatcher = Dispatcher()
    register(
        dispatcher,
        settings,
        secrets,
        db,
        "macos",
        lambda: EngineSnapshot(settings.get().engine, "jev_direct", False),
        FakeProbe(),
        before_change=service.before_config_change,
    )
    filings.block = True
    run_id = service.start("us")
    assert filings.entered.wait(2)
    old = settings.get()

    def call(method: str, params: dict[str, object]) -> dict[str, Any]:
        return dispatcher.dispatch(
            dispatcher.lookup(method),
            params,
            RequestContext("settings-p02", method, CancelToken(), NOW),
        )

    mutations: list[tuple[str, dict[str, object]]] = [
        ("settings.update", {"dailyTokenBudget": 20_000}),
        ("secrets.clear", {"name": "jevKey"}),
    ]
    for method, params in mutations:
        assert call(method, params)["error"]["code"] == "CONFLICT"
    assert settings.get() == old and secrets.get_jev_key() == "synthetic-guard-key"
    service.cancel(run_id)
    filings.release.set()
    finish(service, run_id)
    assert call("secrets.clear", {"name": "jevKey"})["result"]["ok"] is True
    with pytest.raises(SentinelError, match="CONFIG_REQUIRED"):
        service.start("us")
    assert service.history().items[0].run_id == run_id


def test_cancel_queued_starts_no_fetch(stack: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    service, filings, *_ = stack
    queued = []
    original = threading.Thread.start
    with monkeypatch.context() as patch:
        patch.setattr(threading.Thread, "start", lambda self: queued.append(self))
        run_id = service.start("us")
        assert service.status(run_id).status == "queued"
        service.cancel(run_id)
    original(queued[0])
    assert finish(service, run_id).run.status == "cancelled"
    assert filings.calls == 0


@pytest.mark.parametrize(
    "error",
    [
        EngineError("MODEL_ERROR", detail="synthetic-secret"),
        EngineError("UNAUTHENTICATED"),
        EngineError("RATE_LIMITED"),
        EngineError("TIMEOUT"),
        RuntimeError("synthetic-secret"),
        TimeoutError("synthetic-secret"),
    ],
)
def test_batch_errors_keep_code_without_raw_details(
    stack: Any, caplog: pytest.LogCaptureFixture, error: Exception
) -> None:
    service, _, pipeline, *_ = stack
    pipeline.errors[event().event.event_id] = error
    result = finish(service, service.start("us"))
    expected = (
        error.code.value
        if isinstance(error, SentinelError)
        else "TIMEOUT"
        if isinstance(error, TimeoutError)
        else "INTERNAL"
    )
    assert result.batches[0].error.code == expected
    assert "synthetic-secret" not in result.model_dump_json() + caplog.text


def test_immediate_retry_does_not_reset_progress_throttle(stack: Any) -> None:
    service, _, pipeline, *_ = stack
    notices = []
    service.emit = lambda name, payload: notices.append((name, time.monotonic()))
    pipeline.errors[event().event.event_id] = EngineError("MODEL_ERROR")
    result = finish(service, service.start("us"))
    pipeline.errors.clear()
    service.retry_batch(result.batches[0].batch_id)
    moments = [stamp for name, stamp in notices if name == "scan.progress"]
    assert all(b - a >= 0.5 for a, b in zip(moments, moments[1:], strict=False))


def test_inbox_notifications_read_injected_provider_after_real_pipeline_commit(
    stack: Any, db: Database
) -> None:
    from sentinel.semantic.base import SemanticEngine
    from tests.unit.semantic.test_pipeline import OVERTURN, Engine

    service, _, _, _, _, notices = stack
    engine = Engine()
    engine.probabilities = OVERTURN
    service.pipeline_resolver = lambda _: DecisionPipeline(
        db, cast(SemanticEngine, engine), model_id=MODEL_ID, daily_budget=2_000_000
    )

    def pending() -> int:
        with db.read() as reader:
            reader.execute("SELECT count(*) FROM decision WHERE evidence_kind IS NOT NULL")
            row = reader.fetchone()
            assert row is not None
            return cast(int, row[0])

    service.pending_count_provider = pending
    finish(service, service.start("us"))
    updates = [payload for name, payload in notices if name == "inbox.updated"]
    assert updates == [{"newItems": 1, "pendingCount": 1}]
    finish(service, service.start("us"))
    assert sum(name == "inbox.updated" for name, _ in notices) == 1


def test_configuration_guard_serializes_whole_write_against_start(stack: Any) -> None:
    from concurrent.futures import ThreadPoolExecutor

    service, filings, pipeline, _, settings, _ = stack
    entered, release = threading.Event(), threading.Event()

    def change() -> None:
        with service.configuration_guard():
            entered.set()
            assert release.wait(3)
            settings.update(SettingsPatch(daily_token_budget=20_000))

    def resolve(current: Any) -> DecisionPipeline:
        pipeline.daily_budget = current.daily_token_budget
        return cast(DecisionPipeline, pipeline)

    service.pipeline_resolver = resolve
    filings.events = []
    with ThreadPoolExecutor(max_workers=2) as pool:
        editing = pool.submit(change)
        assert entered.wait(2)
        starting = pool.submit(service.start, "us")
        assert not starting.done()
        release.set()
        editing.result(timeout=2)
        finish(service, starting.result(timeout=2))
    assert pipeline.daily_budget == 20_000


def test_jevdb_estimated_usage_is_counted_once_and_cache_is_free(stack: Any, db: Database) -> None:
    from sentinel.semantic.base import SemanticEngine
    from tests.unit.semantic.test_pipeline import Engine

    service, _, _, _, settings, _ = stack
    settings.update(SettingsPatch(engine="jevdb"))
    engine = Engine()
    engine.name = "jevdb"
    service.pipeline_resolver = lambda _: DecisionPipeline(
        db, cast(SemanticEngine, engine), model_id=MODEL_ID, daily_budget=2_000_000
    )
    first = finish(service, service.start("us")).run
    assert first.engine == "jevdb" and first.stats.input_tokens == 10 and first.stats.requests == 1
    with db.read() as reader:
        reader.execute("SELECT input_tokens,estimated_tokens,requests FROM usage_daily")
        assert reader.fetchone() == (0, 10, 1)
    cached = finish(service, service.start("us")).run
    assert cached.stats.input_tokens == cached.stats.requests == 0
    assert len(engine.pairs) == 1


def test_retry_current_engine_change_requires_new_run_without_mixing_stats(stack: Any) -> None:
    service, _, pipeline, _, settings, _ = stack
    pipeline.errors[event().event.event_id] = EngineError("MODEL_ERROR")
    first = finish(service, service.start("us"))
    before = first.batches[0]
    settings.update(SettingsPatch(engine="jevdb"))
    pipeline.engine.name = "jevdb"
    with pytest.raises(SentinelError) as error:
        service.retry_batch(before.batch_id)
    wire = error.value.to_wire("retry-engine")
    assert (
        wire["code"] == "CONFLICT"
        and cast(dict[str, Any], wire["data"])["reason"] == "SCAN_ENGINE_CHANGED"
    )
    assert service.detail(first.run.run_id) == first
    pipeline.errors.clear()
    assert finish(service, service.start("us")).run.engine == "jevdb"


@pytest.mark.parametrize("stop", ["cancel", "timeout"])
def test_retry_resolver_is_cancellable_and_inside_total_deadline(
    stack: Any, monkeypatch: pytest.MonkeyPatch, stop: str
) -> None:
    from concurrent.futures import ThreadPoolExecutor

    import sentinel.scan.orchestrator as module
    from sentinel.rpc.cancel import CancelToken

    service, _, pipeline, *_ = stack
    pipeline.errors[event().event.event_id] = EngineError("MODEL_ERROR")
    first = finish(service, service.start("us"))
    entered, release = threading.Event(), threading.Event()

    def resolve(current: Any) -> DecisionPipeline:
        entered.set()
        assert release.wait(3)
        return cast(DecisionPipeline, pipeline)

    service.pipeline_resolver = resolve
    token = CancelToken()
    if stop == "timeout":
        monkeypatch.setattr(module, "RETRY_TIMEOUT_SECONDS", 0.1)
    try:
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(service.retry_batch, first.batches[0].batch_id, token)
            assert entered.wait(2)
            if stop == "cancel":
                token.cancel()
            with pytest.raises(SentinelError, match="CANCELLED" if stop == "cancel" else "TIMEOUT"):
                future.result(timeout=1)
            assert not service.wait_idle(0.01)
            assert service.detail(first.run.run_id) == first
            release.set()
        assert service.wait_idle(3)
        assert service.detail(first.run.run_id) == first
    finally:
        release.set()


def test_daemon_start_failure_finalizes_run_and_releases_market(
    stack: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    service, *_ = stack

    def fail(self: Any) -> None:
        raise RuntimeError("synthetic-scheduler-secret")

    with monkeypatch.context() as patch:
        patch.setattr(threading.Thread, "start", fail)
        with pytest.raises(SentinelError, match="INTERNAL"):
            service.start("us")
    assert service.history().items[0].status == "failed"
    service.before_config_change()
    assert finish(service, service.start("us")).run.status == "succeeded"
