from __future__ import annotations

import base64
import binascii
import logging
import os
import threading
import time
from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Literal, Protocol, cast

from sentinel import clock
from sentinel.errors import (
    CancelledError,
    ErrorCode,
    InternalError,
    SentinelError,
    SourceError,
    UserError,
)
from sentinel.ids import new_id
from sentinel.markets.instruments.models import Instrument
from sentinel.markets.sec.models import FetchedEvent
from sentinel.messages.scan import MESSAGES
from sentinel.rpc.cancel import CancelToken
from sentinel.semantic.base import ThesisInput
from sentinel.semantic.cache import QUESTION_SET_VERSION, thesis_content_hash, used_today
from sentinel.semantic.pipeline import BatchContext, BatchOutcome, DecisionPipeline
from sentinel.semantic.pricing import cost_usd
from sentinel.storage.db import Database, SqlExecutor

from .models import (
    MODEL_ID,
    ScanBatchView,
    ScanBudget,
    ScanConfiguration,
    ScanDetailView,
    ScanHistoryPage,
    ScanRunView,
)
from .passages import persist_passages
from .watermark import ScanWindow, advance_in, compute_window, read_from, utc

PROGRESS_MIN_INTERVAL_MS = 500
RETRY_TIMEOUT_SECONDS = 60
DEFAULT_HISTORY_LIMIT = 50
MAX_HISTORY_LIMIT = 200
_LOG = logging.getLogger(__name__)
_RUN_COLUMNS = [
    "run_id",
    "trigger",
    "market",
    "status",
    "window_start",
    "window_end",
    "engine",
    "model_id",
    "question_set_version",
    "instruments",
    "skipped_no_thesis",
    "filings",
    "passages",
    "decisions",
    "cached_decisions",
    "requests",
    "input_tokens",
    "est_cost_usd",
    "duration_ms",
    "error_code",
    "error_message",
    "started_at",
    "finished_at",
    "created_at",
]
_BATCH_COLUMNS = [
    "batch_id",
    "run_id",
    "instrument_id",
    "event_id",
    "status",
    "attempts",
    "passages",
    "decisions",
    "input_tokens",
    "error_code",
    "error_message",
    "started_at",
    "finished_at",
]


class SettingsSnapshot(Protocol):
    @property
    def engine(self) -> Literal["auto", "jevdb", "jev_direct"]: ...
    @property
    def model_id(self) -> Literal["jev-1.14.0"]: ...
    @property
    def sec_contact_email(self) -> str | None: ...
    @property
    def daily_token_budget(self) -> int: ...
    @property
    def first_scan_lookback_days(self) -> int: ...


class ThesisSnapshot(Protocol):
    @property
    def thesis_id(self) -> str: ...
    @property
    def version(self) -> int: ...
    @property
    def statement(self) -> str: ...
    @property
    def kill_condition(self) -> str | None: ...


class HoldingsProvider(Protocol):
    def list_scannable_instruments(self) -> list[str]: ...
    def count_holdings(self) -> int: ...
    def list_active_theses(self, instrument_id: str) -> Sequence[ThesisSnapshot]: ...


class FilingsProvider(Protocol):
    def fetch_for_instrument(
        self,
        instrument: Instrument,
        *,
        since: datetime,
        until: datetime,
    ) -> list[FetchedEvent]: ...


class _ScanFailure(SentinelError):
    def to_wire(self, request_id: str | None = None) -> dict[str, object]:
        result = super().to_wire(request_id)
        result["message"] = MESSAGES.get(f"scan.{self.code}", MESSAGES["scan.failed"])
        if self.reason == "SCAN_ENGINE_CHANGED":
            result["message"] = MESSAGES["scan.retry_configuration"]
        return result


def _safe_error(exc: Exception) -> SentinelError:
    if isinstance(exc, SentinelError):
        params: dict[str, object] = {}
        missing = exc.params.get("missing")
        if isinstance(missing, list) and all(v in ("jevKey", "secEmail") for v in missing):
            params["missing"] = missing
        retry = exc.params.get("retryAfterSec")
        if type(retry) is int and retry >= 0:
            params["retryAfterSec"] = retry
        field_name = (
            exc.field
            if exc.field in ("market", "from", "cursor", "limit", "runId", "batchId")
            else None
        )
        reason = (
            exc.reason
            if exc.reason in ("OFFLINE", "SEC_FORBIDDEN", "SCAN_ENGINE_CHANGED")
            else None
        )
        return _ScanFailure(exc.code, params=params, field=field_name, reason=reason)
    return _ScanFailure("TIMEOUT" if isinstance(exc, TimeoutError) else "INTERNAL")


@contextmanager
def _errors() -> Iterator[None]:
    try:
        yield
    except Exception as exc:
        _LOG.warning("scan operation failed error_code=%s", _safe_error(exc).code)
        raise _safe_error(exc) from None


class _Token(CancelToken):
    def __init__(self, parent: CancelToken | None = None, *, deadline: float | None = None) -> None:
        super().__init__()
        self.parent, self.deadline = parent, deadline

    def raise_if_cancelled(self) -> None:
        super().raise_if_cancelled()
        if self.parent is not None:
            self.parent.raise_if_cancelled()
        if self.deadline is not None and time.monotonic() >= self.deadline:
            raise SourceError("TIMEOUT")

    def is_cancelled(self) -> bool:
        return (
            self.cancelled
            or (self.parent is not None and self.parent.is_cancelled())
            or (self.deadline is not None and time.monotonic() >= self.deadline)
        )


@dataclass
class _Operation:
    run_id: str
    token: _Token
    done: threading.Event = field(default_factory=threading.Event)
    error: SentinelError | None = None


_OPERATIONS: dict[tuple[Path, str], _Operation] = {}
_NOTIFICATION_TIMES: dict[tuple[Path, str, str], float] = {}
_LOCK = threading.RLock()


@contextmanager
def _lock_for(token: _Token) -> Iterator[None]:
    while not _LOCK.acquire(timeout=0.02):
        token.raise_if_cancelled()
    try:
        token.raise_if_cancelled()
        yield
    finally:
        _LOCK.release()


class ScanService:
    def __init__(
        self,
        db: Database,
        *,
        settings_provider: Callable[[], SettingsSnapshot],
        key_provider: Callable[[], bool],
        holdings_provider: HoldingsProvider,
        instrument_provider: Callable[[str], Instrument | None],
        filings: FilingsProvider,
        pipeline_resolver: Callable[[ScanConfiguration], DecisionPipeline],
        emit: Callable[[str, dict[str, object]], None] | None = None,
        theses_provider: Callable[[str], Sequence[ThesisInput]] | None = None,
        pending_count_provider: Callable[[], int] | None = None,
    ) -> None:
        self.db = db
        self.settings_provider, self.key_provider = settings_provider, key_provider
        self.holdings, self.instrument_provider = holdings_provider, instrument_provider
        self.filings, self.pipeline_resolver = filings, pipeline_resolver
        self.emit = emit
        self.theses_provider, self.pending_count_provider = theses_provider, pending_count_provider

    def _key(self, market: str) -> tuple[Path, str]:
        return self.db.path, market

    def _check_idle(self, reader: SqlExecutor, market: str) -> None:
        if self._key(market) in _OPERATIONS:
            raise UserError("CONFLICT")
        reader.execute(
            ("SELECT 1 FROM scan_run WHERE market=? AND status IN ('queued','running') LIMIT 1"),
            [market],
        )
        if reader.fetchone() is not None:
            raise UserError("CONFLICT")

    def before_config_change(self) -> None:
        with _errors(), _LOCK, self.db.read() as reader:
            if any(path == self.db.path for path, _ in _OPERATIONS):
                raise UserError("CONFLICT")
            reader.execute("SELECT 1 FROM scan_run WHERE status IN ('queued','running') LIMIT 1")
            if reader.fetchone() is not None:
                raise UserError("CONFLICT")

    @contextmanager
    def configuration_guard(self) -> Iterator[None]:
        # 组合根包住整次配置写入，消除只调用 before_change 的检查/写入竞态。
        with _errors(), _LOCK:
            self.before_config_change()
            yield

    def _settings(self) -> ScanConfiguration:
        current = self.settings_provider()
        return ScanConfiguration(
            engine=current.engine,
            model_id=current.model_id,
            sec_contact_email=current.sec_contact_email,
            daily_token_budget=current.daily_token_budget,
            first_scan_lookback_days=current.first_scan_lookback_days,
        )

    def _configuration(self) -> ScanConfiguration:
        settings = self._settings()
        missing = ([] if self.key_provider() is True else ["jevKey"]) + (
            [] if settings.sec_contact_email else ["secEmail"]
        )
        if missing:
            raise UserError("CONFIG_REQUIRED", params={"missing": missing})
        self._network()
        return settings

    @staticmethod
    def _network() -> None:
        if os.environ.get("SENTINEL_OFFLINE") == "1":
            raise SourceError("SOURCE_UNAVAILABLE", reason="OFFLINE")

    def _resolve(self, settings: ScanConfiguration) -> DecisionPipeline:
        self._network()
        pipeline = self.pipeline_resolver(settings)
        if (
            pipeline.db.path != self.db.path
            or pipeline.model_id != MODEL_ID
            or pipeline.daily_budget != settings.daily_token_budget
            or pipeline.engine.name not in ("jev_direct", "jevdb")
            or (settings.engine != "auto" and settings.engine != pipeline.engine.name)
        ):
            raise InternalError(detail="scan pipeline configuration mismatch")
        return pipeline

    def recover_on_startup(self) -> int:
        with _errors(), _LOCK, self.db.write() as tx:
            if any(path == self.db.path for path, _ in _OPERATIONS):
                raise UserError("CONFLICT")
            tx.execute(
                "UPDATE scan_run SET status='interrupted', finished_at=?, "
                "error_code=NULL, error_message=NULL WHERE status IN "
                "('queued','running') RETURNING run_id",
                [clock.now()],
            )
            return len(tx.fetchall())

    def start(self, market: str, requested_from: datetime | None = None) -> str:
        with _errors(), _LOCK:
            if market != "us":
                raise UserError("INVALID_ARGUMENT", field="market")
            with self.db.read() as reader:
                self._check_idle(reader, market)
                old = read_from(reader, market)
            settings = self._configuration()
            window = compute_window(
                now=clock.now(),
                watermark=old,
                first_lookback_days=settings.first_scan_lookback_days,
                explicit_from=requested_from,
            )
            pipeline = self._resolve(settings)
            run_id = new_id()
            op = _Operation(run_id, _Token())
            with self.db.write() as tx:
                self._check_idle(tx, market)
                tx.execute(
                    "INSERT INTO scan_run (run_id, trigger, market, status, window_start,"
                    " window_end, engine, model_id, question_set_version, created_at) "
                    "VALUES (?, 'manual', ?, 'queued', ?, ?, ?, ?, ?, ?)",
                    [
                        run_id,
                        market,
                        window.start,
                        window.end,
                        pipeline.engine.name,
                        MODEL_ID,
                        QUESTION_SET_VERSION,
                        clock.now(),
                    ],
                )
            _OPERATIONS[self._key(market)] = op
            try:
                threading.Thread(
                    target=self._run,
                    args=(op, market, window, pipeline),
                    name="sentinel-scan",
                    daemon=True,
                ).start()
            except Exception:
                try:
                    self._finish(op, "failed", _safe_error(InternalError()))
                finally:
                    self._release(market, op)
                raise
            return run_id

    def cancel(self, run_id: str) -> None:
        with _errors(), _LOCK, self.db.read() as reader:
            row = self._run_row(reader, run_id)
            op = _OPERATIONS.get(self._key(cast(str, row["market"])))
            if op is not None and op.run_id == run_id:
                op.token.cancel()

    def wait_idle(self, timeout: float = 3) -> bool:
        deadline = time.monotonic() + timeout
        while True:
            with _LOCK:
                ops = [v for (path, _), v in _OPERATIONS.items() if path == self.db.path]
            if not ops:
                return True
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return False
            ops[0].done.wait(min(remaining, 0.02))

    def _release(self, market: str, op: _Operation) -> None:
        with _LOCK:
            if _OPERATIONS.get(self._key(market)) is op:
                del _OPERATIONS[self._key(market)]
            op.done.set()

    def _notify(self, name: str, payload: dict[str, object]) -> None:
        if self.emit is not None:
            try:
                self.emit(name, payload)
            except Exception:
                _LOG.warning("scan notification failed event=%s", name)

    def _progress(self, op: _Operation, stage: str, done: int, total: int) -> None:
        if not self._allow_notify("scan.progress", PROGRESS_MIN_INTERVAL_MS / 1000, op.run_id):
            return
        self._notify(
            "scan.progress",
            dict(
                runId=op.run_id,
                market="us",
                stage=stage,
                done=done,
                total=total,
                message=MESSAGES["scan." + stage],
            ),
        )

    def _allow_notify(self, name: str, interval: float, run_id: str = "") -> bool:
        key, moment = (self.db.path, name, run_id), time.monotonic()
        with _LOCK:
            previous = _NOTIFICATION_TIMES.get(key)
            if previous is not None and moment - previous < interval:
                return False
            _NOTIFICATION_TIMES[key] = moment
            if len(_NOTIFICATION_TIMES) > 2048:
                oldest = min(_NOTIFICATION_TIMES, key=lambda k: _NOTIFICATION_TIMES[k])
                del _NOTIFICATION_TIMES[oldest]
        return True

    def _theses(self, instrument_id: str) -> list[ThesisInput]:
        if self.theses_provider is not None:
            return list(self.theses_provider(instrument_id))
        return [
            ThesisInput(
                f"t{index}",
                t.thesis_id,
                t.version,
                t.statement,
                t.kill_condition,
                thesis_content_hash(t.statement, t.kill_condition),
            )
            for index, t in enumerate(self.holdings.list_active_theses(instrument_id), start=1)
        ]

    def _instrument(self, instrument_id: str) -> Instrument:
        value = self.instrument_provider(instrument_id)
        if (
            value is None
            or value.instrument_id != instrument_id
            or value.market != "us"
            or not value.is_active
        ):
            raise UserError("NOT_FOUND")
        return value

    def _fetch(
        self, op: _Operation, instrument: Instrument, since: datetime, until: datetime
    ) -> list[FetchedEvent]:
        op.token.raise_if_cancelled()
        self._network()
        events = self.filings.fetch_for_instrument(instrument, since=since, until=until)
        op.token.raise_if_cancelled()
        for event in events:
            if event.event.instrument_id != instrument.instrument_id:
                raise InternalError(detail="scan filing identity mismatch")
            utc(event.event.published_at, "publishedAt")
        return events

    def _old_pairs(self, window: ScanWindow) -> list[tuple[str, str]]:
        # 固定时钟的 ULID 随机尾部不表示先后；内部同刻去重采用运行插入顺序。
        with self.db.read() as reader:
            reader.execute(
                "SELECT instrument_id, event_id FROM (SELECT b.*, row_number() OVER ("
                "PARTITION BY b.instrument_id,b.event_id ORDER BY "
                "coalesce(b.finished_at,b.started_at,r.created_at) DESC,r.rowid DESC)"
                " AS rank "
                "FROM scan_batch b JOIN scan_run r ON r.run_id=b.run_id JOIN "
                "event_doc e ON e.event_id=b.event_id "
                "WHERE r.created_at>=? AND e.published_at>=? AND e.published_at<=? "
                "AND (b.status IN ('succeeded','failed') OR "
                "(b.status='pending' AND b.error_code='BUDGET_EXCEEDED'))) "
                "WHERE rank=1 AND (status='failed' OR (status='pending' AND "
                "error_code='BUDGET_EXCEEDED'))",
                [window.end - timedelta(days=30), window.end - timedelta(days=30), window.end],
            )
            return [(cast(str, row[0]), cast(str, row[1])) for row in reader.fetchall()]

    def _create_batch(self, op: _Operation, instrument_id: str, event_id: str) -> None:
        op.token.raise_if_cancelled()
        with self.db.write() as tx:
            op.token.raise_if_cancelled()
            tx.execute(
                "INSERT INTO scan_batch "
                "(batch_id,run_id,instrument_id,event_id,status) VALUES "
                "(?,?,?,?,'pending') "
                "ON CONFLICT(run_id,instrument_id,event_id) DO NOTHING",
                [new_id(), op.run_id, instrument_id, event_id],
            )
            tx.execute(
                (
                    "UPDATE scan_run SET filings=(SELECT count(*) FROM scan_batch WHERE "
                    "run_id=?) WHERE run_id=?"
                ),
                [op.run_id, op.run_id],
            )

    def _run(
        self, op: _Operation, market: str, window: ScanWindow, pipeline: DecisionPipeline
    ) -> None:
        failure: SentinelError | None = None
        list_failure: SentinelError | None = None
        try:
            op.token.raise_if_cancelled()
            with self.db.write() as tx:
                op.token.raise_if_cancelled()
                tx.execute(
                    "UPDATE scan_run SET status='running',started_at=? WHERE run_id=?",
                    [clock.now(), op.run_id],
                )
            ids = sorted(set(self.holdings.list_scannable_instruments()))
            ids = [i for i in ids if i.startswith(market + ":") and self._theses(i)]
            holding_count = self.holdings.count_holdings()
            with self.db.write() as tx:
                tx.execute(
                    "UPDATE scan_run SET instruments=?,skipped_no_thesis=? WHERE run_id=?",
                    [len(ids), max(0, holding_count - len(ids)), op.run_id],
                )
            pairs: set[tuple[str, str]] = set()
            for index, instrument_id in enumerate(ids):
                self._progress(op, "fetch", index, len(ids))
                try:
                    events = self._fetch(
                        op, self._instrument(instrument_id), window.start, window.end
                    )
                except Exception as exc:
                    op.token.raise_if_cancelled()
                    failure = _safe_error(exc)
                    list_failure = _ScanFailure(failure.code, reason="SCAN_LIST_INCOMPLETE")
                    continue
                for event in events:
                    pair = instrument_id, event.event.event_id
                    if pair not in pairs:
                        self._create_batch(op, *pair)
                        pairs.add(pair)
            # 列表成功才推进；正文/模型失败由批历史恢复，不改变列表覆盖语义。
            op.token.raise_if_cancelled()
            if failure is None:
                with self.db.write() as tx:
                    op.token.raise_if_cancelled()
                    advance_in(tx, market, window.end)
            discovered_pairs = pairs.copy()
            for pair in self._old_pairs(window):
                if pair[0] in ids and pair not in pairs:
                    self._create_batch(op, *pair)
                    pairs.add(pair)
            with self.db.read() as reader:
                batches = self._batches(reader, op.run_id)
            for index, batch in enumerate(batches):
                op.token.raise_if_cancelled()
                self._progress(op, "decide", index, len(batches))
                error = self._execute(
                    op,
                    batch,
                    pipeline,
                    recover=(batch.instrument_id, batch.event_id) not in discovered_pairs,
                )
                if error is not None:
                    failure = error
                    if error.code == "BUDGET_EXCEEDED":
                        with self.db.write() as tx:
                            tx.execute(
                                (
                                    "UPDATE scan_batch SET error_code=?,error_message=? "
                                    "WHERE run_id=? AND status='pending'"
                                ),
                                [error.code.value, self._message(error), op.run_id],
                            )
                        break
                    if error.code == "CANCELLED":
                        raise CancelledError()
            op.token.raise_if_cancelled()
            with self.db.read() as reader:
                states = [b.status for b in self._batches(reader, op.run_id)]
            success = states.count("succeeded")
            status = (
                "succeeded"
                if not failure and all(s == "succeeded" for s in states)
                else "partial"
                if success
                else "failed"
            )
            self._finish(op, status, list_failure or failure)
        except Exception as exc:
            error = _safe_error(exc)
            try:
                self._finish(
                    op,
                    "cancelled" if error.code == "CANCELLED" else "failed",
                    None if error.code == "CANCELLED" else error,
                )
            except Exception:
                _LOG.error("scan finalization failed run_id=%s", op.run_id)
        finally:
            self._release(market, op)

    @staticmethod
    def _message(error: SentinelError) -> str:
        if error.reason == "SCAN_LIST_INCOMPLETE":
            return MESSAGES["scan.list_failed"]
        return MESSAGES.get("scan." + error.code.value, MESSAGES["scan.failed"])

    def _finish(self, op: _Operation, status: str, error: SentinelError | None) -> None:
        with self.db.write() as tx:
            row = self._run_row(tx, op.run_id)
            start = cast(datetime | None, row["started_at"]) or cast(datetime, row["created_at"])
            duration = max(0, int((clock.now() - start).total_seconds() * 1000))
            tx.execute(
                (
                    "UPDATE scan_run SET "
                    "status=?,finished_at=?,duration_ms=?,error_code=?,error_message=? "
                    "WHERE run_id=?"
                ),
                [
                    status,
                    clock.now(),
                    min(duration, 2_147_483_647),
                    error.code.value if error else None,
                    self._message(error) if error else None,
                    op.run_id,
                ],
            )
            view = self._view(tx, op.run_id)
        self._progress(op, "finish", view.batch_summary.succeeded, view.batch_summary.total)
        self._notify("scan.finished", view.model_dump(mode="json", by_alias=True))

    def _event(self, batch: ScanBatchView) -> FetchedEvent:
        from sentinel.markets.sec.models import ContentStatus, FilingRef
        from sentinel.markets.sec.repository import file_drafts

        with self.db.read() as reader:
            reader.execute(
                (
                    "SELECT "
                    "instrument_id,form_type,published_at,filing_date,items,url,content_status,title,fetched_at"
                    " FROM event_doc WHERE event_id=?"
                ),
                [batch.event_id],
            )
            row = reader.fetchone()
            if row is None or row[0] != batch.instrument_id:
                raise InternalError(detail="scan event missing")
            reader.execute(
                (
                    "SELECT seq,file_name,doc_type,url,text_status,text,char_count FROM "
                    "event_file WHERE event_id=? ORDER BY seq"
                ),
                [batch.event_id],
            )
            files = file_drafts(reader.fetchall())
        url = cast(str, row[5])
        ref = FilingRef(
            batch.event_id,
            batch.instrument_id,
            url.split("/")[-3].zfill(10),
            batch.event_id.removeprefix("us:"),
            cast(str, row[1]),
            cast(datetime, row[2]),
            cast(date, row[3]),
            cast(str | None, row[4]),
            url.rsplit("/", 1)[1],
            None,
        )
        return FetchedEvent(
            ref, files, cast(ContentStatus, row[6]), cast(str, row[7]), cast(datetime, row[8])
        )

    def _usage(self, pipeline: DecisionPipeline) -> tuple[int, int]:
        with self.db.read() as reader:
            reader.execute(
                (
                    "SELECT "
                    "COALESCE(sum(input_tokens+estimated_tokens),0),COALESCE(sum(requests),0)"
                    " FROM usage_daily WHERE engine=? AND model_id=?"
                ),
                [pipeline.engine.name, pipeline.model_id],
            )
            row = reader.fetchone()
            assert row is not None
            return cast(int, row[0]), cast(int, row[1])

    def _decision_ids(self, batch: ScanBatchView) -> set[str]:
        with self.db.read() as reader:
            reader.execute(
                "SELECT decision_id FROM decision WHERE instrument_id=? AND event_id=?",
                [batch.instrument_id, batch.event_id],
            )
            return {cast(str, row[0]) for row in reader.fetchall()}

    def _execute(
        self,
        op: _Operation,
        batch: ScanBatchView,
        pipeline: DecisionPipeline,
        *,
        recover: bool = True,
    ) -> SentinelError | None:
        error: SentinelError | None = None
        outcome: BatchOutcome | None = None
        before = self._usage(pipeline)
        decisions = self._decision_ids(batch)
        pending_before = self.pending_count_provider() if self.pending_count_provider else 0
        records = []
        with self.db.write() as tx:
            tx.execute(
                (
                    "UPDATE scan_batch SET "
                    "attempts=attempts+1,started_at=?,finished_at=NULL,error_code=NULL,error_message=NULL"
                    " WHERE batch_id=?"
                ),
                [clock.now(), batch.batch_id],
            )
        try:
            op.token.raise_if_cancelled()
            event = self._event(batch)
            if recover and (
                event.content_status == "fetch_failed"
                or any(f.text_status == "failed" for f in event.files)
            ):
                events = self._fetch(
                    op,
                    self._instrument(batch.instrument_id),
                    event.event.published_at - timedelta(seconds=1),
                    clock.now(),
                )
                event = next((e for e in events if e.event.event_id == batch.event_id), event)
            op.token.raise_if_cancelled()
            self._progress(op, "parse", 0, 1)
            records = persist_passages(self.db, event)
            op.token.raise_if_cancelled()
            theses = self._theses(batch.instrument_id)
            if records and theses:
                self._network()
                ctx = BatchContext(
                    op.run_id,
                    batch.batch_id,
                    batch.event_id,
                    batch.instrument_id,
                    self._instrument(batch.instrument_id).name,
                )
                outcome = pipeline.process_batch(ctx, theses, records, op.token)
                if not isinstance(outcome, BatchOutcome) or outcome.status != "succeeded":
                    raise InternalError(detail="invalid scan batch outcome")
            op.token.raise_if_cancelled()
        except Exception as exc:
            error = _safe_error(exc)
            try:
                op.token.raise_if_cancelled()
            except Exception as stopped:
                error = _safe_error(stopped)
        # 两阶段 S-05 可能抛出但已提交评分；统计以真实提交差额为准。
        after = self._usage(pipeline)
        tokens, requests = after[0] - before[0], after[1] - before[1]
        new_decisions = len(self._decision_ids(batch) - decisions)
        cached = outcome.cached_decisions if outcome is not None else 0
        with self.db.write() as tx:
            if error is None:
                try:
                    op.token.raise_if_cancelled()
                except Exception as exc:
                    error = _safe_error(exc)
            status = (
                "succeeded"
                if error is None
                else "pending"
                if error.code == "BUDGET_EXCEEDED"
                else "cancelled"
                if error.code == "CANCELLED"
                else "failed"
            )
            tx.execute(
                (
                    "UPDATE scan_batch SET "
                    "status=?,passages=?,decisions=decisions+?,input_tokens=input_tokens+?,error_code=?,error_message=?,finished_at=?"
                    " WHERE batch_id=?"
                ),
                [
                    status,
                    len(records),
                    new_decisions,
                    tokens,
                    error.code.value if error else None,
                    self._message(error) if error else None,
                    clock.now() if status != "pending" else None,
                    batch.batch_id,
                ],
            )
            tx.execute(
                (
                    "UPDATE scan_run SET passages=(SELECT COALESCE(sum(passages),0) FROM "
                    "scan_batch WHERE "
                    "run_id=?),decisions=decisions+?,cached_decisions=cached_decisions+?,requests=requests+?,input_tokens=input_tokens+?"
                    " WHERE run_id=?"
                ),
                [
                    op.run_id,
                    new_decisions,
                    cached,
                    requests,
                    tokens,
                    op.run_id,
                ],
            )
            row = self._run_row(tx, op.run_id)
            tx.execute(
                "UPDATE scan_run SET est_cost_usd=? WHERE run_id=?",
                [cost_usd(cast(int, row["input_tokens"]), pipeline.model_id), op.run_id],
            )
        if requests and self._allow_notify("budget.updated", 2):
            self._notify("budget.updated", self.budget().model_dump(mode="json", by_alias=True))
        if error is None and self.pending_count_provider is not None:
            pending = self.pending_count_provider()
            if pending > pending_before and self._allow_notify("inbox.updated", 1):
                self._notify(
                    "inbox.updated", dict(newItems=pending - pending_before, pendingCount=pending)
                )
        return error

    def retry_batch(self, batch_id: str, cancel: CancelToken | None = None) -> ScanBatchView:
        token = _Token(cancel, deadline=time.monotonic() + RETRY_TIMEOUT_SECONDS)
        with _errors():
            with _lock_for(token):
                with self.db.read() as reader:
                    batch = self._batch(reader, batch_id)
                    run = self._run_row(reader, batch.run_id)
                    market = cast(str, run["market"])
                    self._check_idle(reader, market)
                if batch.status != "failed":
                    raise UserError("CONFLICT")
                token.raise_if_cancelled()
                op = _Operation(batch.run_id, token)
                _OPERATIONS[self._key(market)] = op
                try:
                    threading.Thread(
                        target=self._retry,
                        args=(op, market, batch, cast(str, run["engine"])),
                        name="sentinel-scan-retry",
                        daemon=True,
                    ).start()
                except Exception:
                    self._release(market, op)
                    raise
            while not op.done.wait(0.02):
                op.token.raise_if_cancelled()
            op.token.raise_if_cancelled()
            if op.error is not None:
                raise op.error
            with self.db.read() as reader:
                return self._batch(reader, batch_id)

    def _retry(
        self, op: _Operation, market: str, batch: ScanBatchView, original_engine: str
    ) -> None:
        prepared = False
        try:
            op.token.raise_if_cancelled()
            pipeline = self._resolve(self._configuration())
            op.token.raise_if_cancelled()
            # 一个历史运行只有一个 engine 字段，不能混入另一个引擎的用量。
            if pipeline.engine.name != original_engine:
                raise UserError("CONFLICT", reason="SCAN_ENGINE_CHANGED")
            with self.db.write() as tx:
                op.token.raise_if_cancelled()
                tx.execute(
                    "UPDATE scan_batch SET status='pending' WHERE batch_id=? "
                    "AND status='failed' RETURNING batch_id",
                    [batch.batch_id],
                )
                if tx.fetchone() is None:
                    raise UserError("CONFLICT")
            prepared = True
            op.error = self._execute(op, batch, pipeline)
            with self.db.write() as tx:
                row = self._run_row(tx, op.run_id)
                states = [b.status for b in self._batches(tx, op.run_id)]
                if (
                    row["status"] == "partial"
                    and row["error_message"] != MESSAGES["scan.list_failed"]
                    and all(s == "succeeded" for s in states)
                ):
                    tx.execute(
                        (
                            "UPDATE scan_run SET "
                            "status='succeeded',error_code=NULL,error_message=NULL WHERE run_id=?"
                        ),
                        [op.run_id],
                    )
            # 重试不是新运行，不重复发送 scan.finished。
        except Exception as exc:
            op.error = _safe_error(exc)
            if not prepared:
                return
            try:
                with self.db.write() as tx:
                    tx.execute(
                        (
                            "UPDATE scan_batch SET "
                            "status='failed',error_code=?,error_message=?,finished_at=? WHERE "
                            "batch_id=?"
                        ),
                        [op.error.code.value, self._message(op.error), clock.now(), batch.batch_id],
                    )
            except Exception:
                _LOG.error("scan retry finalization failed batch_id=%s", batch.batch_id)
        finally:
            self._release(market, op)

    def budget(self) -> ScanBudget:
        with _errors():
            moment = clock.now()
            settings = self._settings()
            with self.db.read() as reader:
                used = used_today(reader, moment.date())
            reset = datetime.combine(
                moment.date() + timedelta(days=1), datetime.min.time(), tzinfo=UTC
            )
            return ScanBudget(
                used_tokens=used,
                limit_tokens=settings.daily_token_budget,
                reset_at=clock.to_iso(reset),
            )

    def status(self, run_id: str) -> ScanRunView:
        with _errors(), self.db.read() as reader:
            return self._view(reader, run_id)

    def detail(self, run_id: str) -> ScanDetailView:
        with _errors(), self.db.read() as reader:
            return ScanDetailView(
                run=self._view(reader, run_id), batches=self._batches(reader, run_id)
            )

    def history(
        self, limit: int = DEFAULT_HISTORY_LIMIT, cursor: str | None = None
    ) -> ScanHistoryPage:
        with _errors():
            if type(limit) is not int or not 1 <= limit <= MAX_HISTORY_LIMIT:
                raise UserError("INVALID_ARGUMENT", field="limit")
            where, params = "", []
            if cursor is not None:
                moment, run_id = self._decode_cursor(cursor)
                where, params = (
                    " WHERE created_at<? OR (created_at=? AND run_id<?)",
                    [moment, moment, run_id],
                )
            with self.db.read() as reader:
                reader.execute(
                    "SELECT run_id,created_at FROM scan_run"
                    + where
                    + " ORDER BY created_at DESC,run_id DESC LIMIT ?",
                    [*params, limit + 1],
                )
                rows = reader.fetchall()
                items = [self._view(reader, cast(str, row[0])) for row in rows[:limit]]
            next_cursor = None
            if len(rows) > limit:
                last = rows[limit - 1]
                next_cursor = (
                    base64.urlsafe_b64encode(
                        (clock.to_iso(cast(datetime, last[1])) + "|" + cast(str, last[0])).encode()
                    )
                    .decode()
                    .rstrip("=")
                )
            return ScanHistoryPage(items=items, next_cursor=next_cursor, budget=self.budget())

    @staticmethod
    def _decode_cursor(cursor: str) -> tuple[datetime, str]:
        try:
            if not isinstance(cursor, str) or not cursor or len(cursor) > 256:
                raise ValueError
            raw = base64.b64decode(cursor + "=" * (-len(cursor) % 4), altchars=b"-_", validate=True)
            text, identity = raw.decode().split("|")
            from sentinel.ids import is_ulid

            if not is_ulid(identity) or not text.endswith("Z"):
                raise ValueError
            return clock.parse_iso(text), identity
        except (ValueError, UnicodeError, binascii.Error):
            raise UserError("INVALID_ARGUMENT", field="cursor") from None

    @staticmethod
    def _run_row(reader: SqlExecutor, run_id: str) -> dict[str, object]:
        if not isinstance(run_id, str) or not run_id:
            raise UserError("INVALID_ARGUMENT", field="runId")
        reader.execute("SELECT * FROM scan_run WHERE run_id=?", [run_id])
        row = reader.fetchone()
        if row is None:
            raise UserError("NOT_FOUND")
        return dict(zip(_RUN_COLUMNS, row, strict=True))

    def _view(self, reader: SqlExecutor, run_id: str) -> ScanRunView:
        row = self._run_row(reader, run_id)
        batches = self._batches(reader, run_id)
        stats = {
            k: row[k]
            for k in (
                "instruments",
                "skipped_no_thesis",
                "filings",
                "passages",
                "decisions",
                "cached_decisions",
                "requests",
                "input_tokens",
            )
        }
        start = cast(datetime | None, row["started_at"])
        duration = row["duration_ms"] or (
            max(0, int((clock.now() - start).total_seconds() * 1000)) if start else 0
        )
        stats.update(est_cost_usd=format(row["est_cost_usd"], ".6f"), duration_ms=duration)
        values = {
            k: row[k] for k in ("run_id", "trigger", "market", "status", "engine", "model_id")
        }
        values.update(
            window_start=clock.to_iso(cast(datetime, row["window_start"])),
            window_end=clock.to_iso(cast(datetime, row["window_end"])),
            started_at=clock.to_iso(start) if start else None,
            finished_at=clock.to_iso(cast(datetime, row["finished_at"]))
            if row["finished_at"]
            else None,
            stats=stats,
            error=self._error_view(row),
            batch_summary=dict(
                total=len(batches),
                succeeded=sum(b.status == "succeeded" for b in batches),
                failed=sum(b.status == "failed" for b in batches),
                pending=sum(b.status == "pending" for b in batches),
            ),
        )
        return ScanRunView.model_validate(values)

    @staticmethod
    def _error_view(row: dict[str, object]) -> dict[str, str] | None:
        if row["error_code"] is None:
            return None
        code = ErrorCode(cast(str, row["error_code"])).value
        if row["error_message"] == MESSAGES["scan.list_failed"]:
            return dict(code=code, message=MESSAGES["scan.list_failed"])
        return dict(code=code, message=MESSAGES.get("scan." + code, MESSAGES["scan.failed"]))

    def _batch(self, reader: SqlExecutor, batch_id: str) -> ScanBatchView:
        if not isinstance(batch_id, str) or not batch_id:
            raise UserError("INVALID_ARGUMENT", field="batchId")
        reader.execute(
            (
                "SELECT b.*,e.title FROM scan_batch b JOIN event_doc e ON "
                "e.event_id=b.event_id WHERE b.batch_id=?"
            ),
            [batch_id],
        )
        row = reader.fetchone()
        if row is None:
            raise UserError("NOT_FOUND")
        values = dict(zip([*_BATCH_COLUMNS, "event_title"], row, strict=True))
        view = {
            k: values[k]
            for k in (
                "batch_id",
                "run_id",
                "instrument_id",
                "event_id",
                "event_title",
                "status",
                "attempts",
                "passages",
                "decisions",
                "input_tokens",
            )
        }
        view["error"] = self._error_view(values)
        return ScanBatchView.model_validate(view)

    def _batches(self, reader: SqlExecutor, run_id: str) -> list[ScanBatchView]:
        reader.execute(
            (
                "SELECT b.batch_id FROM scan_batch b JOIN event_doc e ON "
                "e.event_id=b.event_id WHERE b.run_id=? ORDER BY "
                "e.published_at,e.event_id,b.batch_id"
            ),
            [run_id],
        )
        ids = [cast(str, row[0]) for row in reader.fetchall()]
        return [self._batch(reader, identity) for identity in ids]
