from __future__ import annotations

import base64
import binascii
import json
import logging
import re
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Annotated, Literal, Protocol, cast

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    PrivateAttr,
    ValidationError,
    field_validator,
)
from pydantic.alias_generators import to_camel

from sentinel import clock, ids
from sentinel.errors import InternalError, UserError
from sentinel.logging_setup import get_logger, log_event
from sentinel.markets.prices.calendar import market_state
from sentinel.messages.inbox import MESSAGES
from sentinel.rpc.dispatcher import Handler, RequestContext
from sentinel.storage import Database, SqlExecutor

PROCESSED_DAYS = 30
DEFAULT_LIMIT = 50
MAX_LIMIT = 200
MAX_NOTE_CODEPOINTS = 200
RELATION_RANK = {"overturn": 0, "weaken": 1, "uncertain": 2}
DEFAULT_TOKEN_BUDGET = 2_000_000

ActionType = Literal["still_valid", "revise", "exit_intent", "ignore"]
StoredAction = Literal["still_valid", "revise", "exit_intent", "ignore", "reopen"]
Relation = Literal["none", "support", "weaken", "overturn", "uncertain"]
Engine = Literal["jevdb", "jev_direct"]
Market = Literal["us", "cn", "hk"]
ScanStatus = Literal[
    "queued", "running", "succeeded", "partial", "failed", "cancelled", "interrupted"
]
Identifier = Annotated[str, Field(min_length=1)]
Count = Annotated[int, Field(ge=0)]
Probability = Annotated[float, Field(ge=0, le=1, allow_inf_nan=False)]


def _iso(value: str) -> str:
    clock.parse_iso(value)
    if not value.endswith("Z"):
        raise ValueError("UTC Z timestamp required")
    return value


IsoTime = Annotated[
    str,
    Field(pattern=r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(?:\.[0-9]+)?Z$"),
    AfterValidator(_iso),
]


class WireModel(BaseModel):
    model_config = ConfigDict(
        strict=True,
        extra="forbid",
        frozen=True,
        revalidate_instances="always",
        regex_engine="python-re",
        alias_generator=to_camel,
        validate_by_alias=True,
        validate_by_name=True,
    )


class Instrument(WireModel):
    instrument_id: Identifier
    market: Market
    symbol: Identifier
    name: str
    name_zh: str | None
    exchange: str
    currency: Literal["USD", "CNY", "HKD"]
    is_active: bool


class Probabilities(WireModel):
    relevant: Probability
    against: Probability
    contradicts: Probability
    kill_met: Probability | None
    supports: Probability


class EventRef(WireModel):
    event_id: Identifier
    instrument_id: Identifier
    title: str
    form_type: Literal["8-K", "8-K/A", "6-K"]
    published_at: IsoTime
    url: Annotated[str, Field(pattern=r"^https://[^/\s?#]+(?:[/\?#][^\s]*)?(?![\s\S])")]


class Evidence(WireModel):
    kind: Literal["sentence", "passage", "title"]
    text: str
    passage_text: str
    sentence_start: Count | None
    sentence_end: Count | None
    file_part: str


class ActionRecord(WireModel):
    action: StoredAction
    note: Annotated[str, Field(max_length=MAX_NOTE_CODEPOINTS)] | None
    acted_at: IsoTime


class DecisionSummary(WireModel):
    decision_id: Identifier
    thesis_id: Identifier
    thesis_version: Annotated[int, Field(ge=1)]
    thesis_current_version: Annotated[int, Field(ge=1)]
    instrument: Instrument
    thesis_statement: Annotated[str, Field(min_length=1, max_length=500, pattern=r"\S")]
    kill_condition: Annotated[str, Field(max_length=300)] | None
    relation: Relation
    headline: Probability
    probabilities: Probabilities
    engine: Engine
    model_id: str
    question_set_version: str
    event: EventRef
    evidence: Evidence
    content_status: Literal["full_text", "title_only"]
    created_at: IsoTime
    action: ActionRecord | None


class DecisionDetail(DecisionSummary):
    actions: list[ActionRecord]
    thesis_is_latest: bool


class InboxCounts(WireModel):
    pending_count: Count
    overturn_count: Count
    weaken_count: Count
    uncertain_count: Count
    processed_count: Count


class Setup(WireModel):
    holdings: Count
    active_theses: Count
    scannable_instruments: Count


class SourceStatus(WireModel):
    name: str
    state: Literal["ok", "degraded", "down"]
    last_success_at: IsoTime | None
    message: str | None


class EngineStatus(WireModel):
    active: Engine | None
    model_id: str
    state: Literal["ok", "degraded", "unconfigured"]


class BudgetStatus(WireModel):
    used_tokens: Count
    limit_tokens: Annotated[int, Field(ge=10_000, le=50_000_000)]
    reset_at: IsoTime


class StatusSnapshot(WireModel):
    source: SourceStatus
    engine: EngineStatus
    offline: bool


StatusProvider = Callable[[SqlExecutor, datetime], StatusSnapshot]


class DataStatus(StatusSnapshot):
    market: Market
    market_state: Literal["open", "pre", "after", "closed", "holiday"]
    next_open_at: IsoTime | None
    budget: BudgetStatus


class ScanStats(WireModel):
    instruments: Count
    skipped_no_thesis: Count
    filings: Count
    passages: Count
    decisions: Count


class ScanError(WireModel):
    code: str
    message: str


class LastScan(WireModel):
    run_id: Identifier
    status: ScanStatus
    finished_at: IsoTime | None
    stats: ScanStats
    error: ScanError | None


class InboxPage(WireModel):
    as_of: IsoTime
    summary: InboxCounts
    items: list[DecisionSummary]
    uncertain: list[DecisionSummary]
    processed: list[DecisionSummary]
    last_scan: LastScan | None
    data_status: DataStatus
    setup: Setup
    _next_cursor: str | None = PrivateAttr(default=None)

    @property
    def next_cursor(self) -> str | None:
        """分页只供 Python 调用方；40 方法机器契约不含游标字段。"""
        return self._next_cursor


class EmptyParams(WireModel):
    pass


class DecisionIdParams(WireModel):
    decision_id: Identifier


def _note(value: object) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise UserError("INVALID_ARGUMENT", field="note")
    value = value.strip()
    if len(value) > MAX_NOTE_CODEPOINTS:
        raise UserError(
            "INVALID_ARGUMENT",
            message_key="inbox.note_too_long",
            field="note",
            params={"max": MAX_NOTE_CODEPOINTS},
        )
    return value or None


class ActParams(DecisionIdParams):
    action: ActionType
    note: str | None = None

    @field_validator("note", mode="before")
    @classmethod
    def normalize_note(cls, value: object) -> str | None:
        return _note(value)


# 先选代表再校验证据；缺证据不能把另一条较弱判定冒充代表。
_RANKED_SQL = """
WITH ranked AS (
    SELECT d.decision_id,
           ROW_NUMBER() OVER (
               PARTITION BY d.thesis_id, d.event_id
               ORDER BY CASE d.relation WHEN 'overturn' THEN 0 WHEN 'weaken' THEN 1 ELSE 2 END,
                        d.headline DESC, p.seq ASC, d.decision_id ASC
           ) AS rk
    FROM decision d
    LEFT JOIN event_passage p ON p.passage_id=d.passage_id
    JOIN thesis t ON t.thesis_id=d.thesis_id
                 AND t.status='active' AND t.archived_at IS NULL
    JOIN holding h ON h.instrument_id=t.instrument_id AND h.archived_at IS NULL
    WHERE d.relation IN ('overturn', 'weaken', 'uncertain')
)
"""

_ROW_SQL = """
SELECT d.decision_id, d.thesis_id, d.thesis_version, t.current_version,
       tv.statement, tv.kill_condition, d.relation, d.headline,
       d.p_relevant, d.p_against, d.p_contradicts, d.p_kill_met, d.p_supports,
       d.engine, d.model_id, d.question_set_version, d.content_status, d.created_at,
       i.instrument_id, i.market, i.symbol, i.name, i.name_zh, i.exchange, i.currency, i.is_active,
       e.event_id, e.instrument_id, e.title, e.form_type, e.published_at, e.url,
       p.text, p.file_seq, p.event_id, f.doc_type, f.text_status, f.text,
       d.evidence_kind, d.evidence_start, d.evidence_end,
       la.action, la.note, la.acted_at, a.action_id,
       d.instrument_id, t.instrument_id, e.content_status
FROM decision d
LEFT JOIN thesis t ON t.thesis_id=d.thesis_id
LEFT JOIN thesis_version tv ON tv.thesis_id=d.thesis_id AND tv.version=d.thesis_version
LEFT JOIN instrument i ON i.instrument_id=d.instrument_id
LEFT JOIN event_doc e ON e.event_id=d.event_id
LEFT JOIN event_passage p ON p.passage_id=d.passage_id
LEFT JOIN event_file f ON f.event_id=p.event_id AND f.seq=p.file_seq
LEFT JOIN v_last_action la ON la.decision_id=d.decision_id
LEFT JOIN thesis_action a ON a.decision_id=la.decision_id AND a.created_at=la.acted_at
                         AND a.action_id=(SELECT MAX(x.action_id) FROM thesis_action x
                                          WHERE x.decision_id=la.decision_id
                                            AND x.created_at=la.acted_at)
"""

_ROW_COLUMNS = (
    "decision_id",
    "thesis_id",
    "thesis_version",
    "current_version",
    "statement",
    "kill_condition",
    "relation",
    "headline",
    "relevant",
    "against",
    "contradicts",
    "kill_met",
    "supports",
    "engine",
    "model_id",
    "question_set_version",
    "content_status",
    "created_at",
    "instrument_id",
    "market",
    "symbol",
    "name",
    "name_zh",
    "exchange",
    "currency",
    "is_active",
    "event_id",
    "event_instrument_id",
    "title",
    "form_type",
    "published_at",
    "url",
    "passage_text",
    "file_seq",
    "passage_event_id",
    "doc_type",
    "text_status",
    "file_text",
    "evidence_kind",
    "evidence_start",
    "evidence_end",
    "last_action",
    "action_note",
    "acted_at",
    "action_id",
    "decision_instrument_id",
    "thesis_instrument_id",
    "event_content_status",
)


def _time(value: object) -> str:
    if not isinstance(value, datetime):
        raise InternalError(detail="inbox: missing timestamp")
    return clock.to_iso(value)


def _action(value: object, note: object, at: object) -> ActionRecord | None:
    if value is None:
        if note is not None or at is not None:
            raise InternalError(detail="inbox: incomplete action")
        return None
    return ActionRecord.model_validate({"action": value, "note": note, "acted_at": _time(at)})


def _evidence(row: dict[str, object]) -> Evidence:
    text, kind, file_seq = row["passage_text"], row["evidence_kind"], row["file_seq"]
    if not isinstance(text, str) or not text.strip() or type(file_seq) is not int:
        raise InternalError(detail="inbox: missing passage")
    if row["event_id"] is None or row["event_id"] != row["passage_event_id"]:
        raise InternalError(detail="inbox: inconsistent event")
    instrument_id = row["decision_instrument_id"]
    if instrument_id != row["thesis_instrument_id"] or instrument_id != row["event_instrument_id"]:
        raise InternalError(detail="inbox: inconsistent instrument")
    if row["content_status"] != row["event_content_status"]:
        raise InternalError(detail="inbox: inconsistent content status")
    start, end = row["evidence_start"], row["evidence_end"]
    if kind in ("title", "passage") and (start is not None or end is not None):
        raise InternalError(detail="inbox: unexpected evidence offsets")
    if kind == "title":
        if file_seq != -1 or row["content_status"] != "title_only" or text != row["title"]:
            raise InternalError(detail="inbox: invalid title evidence")
        return Evidence.model_validate(
            {
                "kind": kind,
                "text": row["title"],
                "passage_text": text,
                "sentence_start": None,
                "sentence_end": None,
                "file_part": MESSAGES["inbox.file_title"],
            }
        )
    if (
        file_seq < 0
        or row["content_status"] != "full_text"
        or row["text_status"] != "extracted"
        or not isinstance(row["file_text"], str)
        or not row["file_text"].strip()
        or not isinstance(row["doc_type"], str)
        or not row["doc_type"].strip()
    ):
        raise InternalError(detail="inbox: missing source file")
    part = MESSAGES["inbox.file_main"] if file_seq == 0 else row["doc_type"]
    if kind == "sentence":
        if type(start) is not int or type(end) is not int or not 0 <= start < end <= len(text):
            raise InternalError(detail="inbox: evidence offset out of range")
        excerpt = text[start:end]
        if not excerpt.strip():
            raise InternalError(detail="inbox: empty sentence evidence")
    elif kind == "passage":
        excerpt, start, end = text, None, None
    else:
        raise InternalError(detail="inbox: missing or unknown evidence kind")
    return Evidence.model_validate(
        {
            "kind": kind,
            "text": excerpt,
            "passage_text": text,
            "sentence_start": start,
            "sentence_end": end,
            "file_part": part,
        }
    )


def _summary(row: dict[str, object]) -> DecisionSummary:
    try:
        evidence = _evidence(row)
        return DecisionSummary.model_validate(
            {
                "decision_id": row["decision_id"],
                "thesis_id": row["thesis_id"],
                "thesis_version": row["thesis_version"],
                "thesis_current_version": row["current_version"],
                "thesis_statement": row["statement"],
                "kill_condition": row["kill_condition"],
                "relation": row["relation"],
                "headline": row["headline"],
                "probabilities": {
                    key: row[key]
                    for key in ("relevant", "against", "contradicts", "kill_met", "supports")
                },
                "engine": row["engine"],
                "model_id": row["model_id"],
                "question_set_version": row["question_set_version"],
                "content_status": row["content_status"],
                "created_at": _time(row["created_at"]),
                "instrument": {
                    key: row[key]
                    for key in (
                        "instrument_id",
                        "market",
                        "symbol",
                        "name",
                        "name_zh",
                        "exchange",
                        "currency",
                        "is_active",
                    )
                },
                "event": {
                    "event_id": row["event_id"],
                    "instrument_id": row["event_instrument_id"],
                    "title": row["title"],
                    "form_type": row["form_type"],
                    "published_at": _time(row["published_at"]),
                    "url": row["url"],
                },
                "evidence": evidence,
                "action": _action(row["last_action"], row["action_note"], row["acted_at"]),
            }
        )
    except ValidationError as exc:
        raise InternalError(detail="inbox: invalid decision row") from exc


def _cursor_encode(at: datetime, action_id: str) -> str:
    return base64.urlsafe_b64encode(f"{clock.to_iso(at)}|{action_id}".encode()).decode().rstrip("=")


def _cursor_decode(cursor: str | None) -> tuple[datetime, str] | None:
    if cursor is None:
        return None
    try:
        if not isinstance(cursor, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,200}", cursor):
            raise ValueError("invalid cursor encoding")
        raw = base64.b64decode(cursor + "=" * (-len(cursor) % 4), altchars=b"-_", validate=True)
        moment, action_id = raw.decode("ascii").split("|")
        at = clock.parse_iso(moment)
        if not ids.is_ulid(action_id) or _cursor_encode(at, action_id) != cursor:
            raise ValueError("noncanonical cursor")
        return at, action_id
    except (ValueError, UnicodeError, binascii.Error):
        raise UserError("INVALID_ARGUMENT", field="cursor") from None


def _new_action_id(tx: SqlExecutor, at: datetime) -> str:
    timestamp_ms = (at - datetime(1970, 1, 1, tzinfo=UTC)) // timedelta(milliseconds=1)
    candidate = ids.new_id(timestamp_ms=timestamp_ms)
    tx.execute("SELECT MAX(action_id) FROM thesis_action WHERE created_at=?", [at])
    row = tx.fetchone()
    last = None if row is None else row[0]
    # ULID 默认随机熵；同一时刻连续点击必须仍让最新追加的一行排在最前。
    if isinstance(last, str) and candidate <= last:
        if not ids.is_ulid(last) or ids.ulid_to_timestamp_ms(last) != timestamp_ms:
            raise InternalError(detail="inbox: inconsistent action ULID timestamp")
        number = 0
        for char in last:
            number = number * 32 + ids.CROCKFORD.index(char)
        entropy = (number & ((1 << 80) - 1)) + 1
        if entropy >= 1 << 80:
            raise InternalError(detail="inbox: action ULID entropy exhausted")
        candidate = ids.new_id(timestamp_ms=timestamp_ms, entropy=entropy.to_bytes(10, "big"))
    return candidate


class InboxService:
    def __init__(self, db: Database, *, status_provider: StatusProvider) -> None:
        self._db = db
        self._status_provider = status_provider

    def list_inbox(self, *, limit: int = DEFAULT_LIMIT, cursor: str | None = None) -> InboxPage:
        if type(limit) is not int or not 1 <= limit <= MAX_LIMIT:
            raise UserError("INVALID_ARGUMENT", field="limit")
        after = _cursor_decode(cursor)
        with self._db.read() as reader:
            as_of = clock.now()
            reader.execute(
                _RANKED_SQL
                + _ROW_SQL
                + " WHERE d.decision_id IN (SELECT decision_id FROM ranked WHERE rk=1)"
            )
            rows = [dict(zip(_ROW_COLUMNS, row, strict=True)) for row in reader.fetchall()]
            items: list[DecisionSummary] = []
            uncertain: list[DecisionSummary] = []
            processed: list[tuple[datetime, str, DecisionSummary]] = []
            for row in rows:
                try:
                    item = _summary(row)
                except InternalError as exc:
                    log_event(
                        get_logger(__name__),
                        logging.ERROR,
                        event="inbox.invalid_decision",
                        error_code="INTERNAL",
                        decision_id=row["decision_id"],
                        detail=exc.detail,
                    )
                    continue
                if item.action is None or item.action.action == "reopen":
                    (uncertain if item.relation == "uncertain" else items).append(item)
                else:
                    at, action_id = cast(datetime, row["acted_at"]), cast(str, row["action_id"])
                    if at >= as_of - timedelta(days=PROCESSED_DAYS):
                        processed.append((at, action_id, item))
            items.sort(
                key=lambda item: (
                    RELATION_RANK[item.relation],
                    -item.headline,
                    -clock.parse_iso(item.event.published_at).timestamp(),
                    item.decision_id,
                )
            )
            uncertain.sort(
                key=lambda item: (
                    -item.headline,
                    -clock.parse_iso(item.event.published_at).timestamp(),
                    item.decision_id,
                )
            )
            processed.sort(key=lambda entry: entry[:2], reverse=True)
            if after is not None:
                processed = [entry for entry in processed if entry[:2] < after]
            shown = processed[:limit]
            last_scan = self._last_scan(reader)
            setup = self._setup(reader)
            data_status = self._data_status(reader, as_of)
            page = InboxPage(
                as_of=clock.to_iso(as_of),
                summary=InboxCounts(
                    pending_count=len(items) + len(uncertain),
                    overturn_count=sum(item.relation == "overturn" for item in items),
                    weaken_count=sum(item.relation == "weaken" for item in items),
                    uncertain_count=len(uncertain),
                    processed_count=len(shown),
                ),
                items=items,
                uncertain=uncertain,
                processed=[entry[2] for entry in shown],
                last_scan=last_scan,
                setup=setup,
                data_status=data_status,
            )
            if len(processed) > limit:
                page._next_cursor = _cursor_encode(shown[-1][0], shown[-1][1])
            return page

    def _get_summary(self, reader: SqlExecutor, decision_id: str) -> DecisionSummary:
        reader.execute(_ROW_SQL + " WHERE d.decision_id=?", [decision_id])
        row = reader.fetchone()
        if row is None:
            raise UserError("NOT_FOUND", message_key="inbox.decision_not_found")
        return _summary(dict(zip(_ROW_COLUMNS, row, strict=True)))

    def get_decision(self, decision_id: str) -> DecisionDetail:
        with self._db.read() as reader:
            summary = self._get_summary(reader, decision_id)
            reader.execute(
                "SELECT action, note, created_at FROM thesis_action WHERE decision_id=? "
                "ORDER BY created_at DESC, action_id DESC",
                [decision_id],
            )
            try:
                actions = [_action(*row) for row in reader.fetchall()]
                return DecisionDetail.model_validate(
                    summary.model_dump()
                    | {
                        "actions": actions,
                        "thesis_is_latest": summary.thesis_version
                        == summary.thesis_current_version,
                    }
                )
            except ValidationError as exc:
                raise InternalError(detail="inbox: invalid action history") from exc

    def act(self, decision_id: str, action: ActionType, note: str | None = None) -> DecisionSummary:
        if action not in ("still_valid", "revise", "exit_intent", "ignore"):
            raise UserError("INVALID_ARGUMENT", field="action")
        normalized = _note(note)
        with self._db.write() as tx:
            self._get_summary(tx, decision_id)
            at = clock.now()
            tx.execute(
                "INSERT INTO thesis_action VALUES (?, ?, ?, ?, ?)",
                [_new_action_id(tx, at), decision_id, action, normalized, at],
            )
            return self._get_summary(tx, decision_id)

    def reopen(self, decision_id: str) -> DecisionSummary:
        with self._db.write() as tx:
            summary = self._get_summary(tx, decision_id)
            if summary.action is None or summary.action.action == "reopen":
                return summary
            at = clock.now()
            tx.execute(
                "INSERT INTO thesis_action VALUES (?, ?, 'reopen', NULL, ?)",
                [_new_action_id(tx, at), decision_id, at],
            )
            return self._get_summary(tx, decision_id)

    @staticmethod
    def _last_scan(reader: SqlExecutor) -> LastScan | None:
        reader.execute(
            "SELECT run_id, status, finished_at, instruments, skipped_no_thesis, filings, "
            "passages, decisions, error_code, error_message FROM scan_run WHERE market='us' "
            "ORDER BY created_at DESC, run_id DESC LIMIT 1"
        )
        row = reader.fetchone()
        if row is None:
            return None
        (
            run_id,
            status,
            finished,
            instruments,
            skipped,
            filings,
            passages,
            decisions,
            code,
            message,
        ) = row
        if (code is None) != (message is None):
            raise InternalError(detail="inbox: incomplete scan error")
        try:
            return LastScan.model_validate(
                {
                    "run_id": run_id,
                    "status": status,
                    "finished_at": None if finished is None else _time(finished),
                    "stats": {
                        "instruments": instruments,
                        "skipped_no_thesis": skipped,
                        "filings": filings,
                        "passages": passages,
                        "decisions": decisions,
                    },
                    "error": None if code is None else {"code": code, "message": message},
                }
            )
        except ValidationError as exc:
            raise InternalError(detail="inbox: invalid scan snapshot") from exc

    @staticmethod
    def _setup(reader: SqlExecutor) -> Setup:
        reader.execute("""
            SELECT (SELECT COUNT(*) FROM holding WHERE archived_at IS NULL),
                   (SELECT COUNT(*) FROM thesis t JOIN holding h USING (instrument_id)
                    WHERE t.status='active' AND t.archived_at IS NULL AND h.archived_at IS NULL),
                   (SELECT COUNT(DISTINCT t.instrument_id) FROM thesis t
                    JOIN holding h USING (instrument_id)
                    WHERE t.status='active' AND t.archived_at IS NULL AND h.archived_at IS NULL)
        """)
        row = reader.fetchone()
        assert row is not None
        return Setup.model_validate(
            dict(zip(("holdings", "active_theses", "scannable_instruments"), row, strict=True))
        )

    def _data_status(self, reader: SqlExecutor, as_of: datetime) -> DataStatus:
        snapshot = StatusSnapshot.model_validate(self._status_provider(reader, as_of))
        reader.execute(
            "SELECT COALESCE(SUM(input_tokens + estimated_tokens), 0) FROM usage_daily "
            "WHERE usage_date=?",
            [as_of.date()],
        )
        used = reader.fetchone()
        assert used is not None
        reader.execute("SELECT value_json FROM setting WHERE key='dailyTokenBudget'")
        stored = reader.fetchone()
        try:
            limit = DEFAULT_TOKEN_BUDGET if stored is None else json.loads(cast(str, stored[0]))
            budget = BudgetStatus.model_validate(
                {
                    "used_tokens": used[0],
                    "limit_tokens": limit,
                    "reset_at": clock.to_iso(
                        (as_of + timedelta(days=1)).replace(
                            hour=0, minute=0, second=0, microsecond=0
                        )
                    ),
                }
            )
            state = market_state(as_of)
            return DataStatus.model_validate(
                snapshot.model_dump()
                | {
                    "market": "us",
                    "market_state": state.status,
                    "next_open_at": clock.to_iso(state.next_open_at),
                    "budget": budget,
                }
            )
        except (ValueError, TypeError) as exc:
            raise InternalError(detail="inbox: invalid data status snapshot") from exc


class HandlerRegistrar(Protocol):
    def register(
        self,
        method: str,
        handler: Handler,
        params_model: type[BaseModel],
        result_model: type[BaseModel] | None = None,
        timeout_ms: int = 30_000,
    ) -> None: ...


def register_handlers(registrar: HandlerRegistrar, service: InboxService) -> None:
    def list_inbox(params: BaseModel, ctx: RequestContext) -> BaseModel:
        return service.list_inbox()

    def get(params: BaseModel, ctx: RequestContext) -> BaseModel:
        return service.get_decision(cast(DecisionIdParams, params).decision_id)

    def act(params: BaseModel, ctx: RequestContext) -> BaseModel:
        p = cast(ActParams, params)
        return service.act(p.decision_id, p.action, p.note)

    def reopen(params: BaseModel, ctx: RequestContext) -> BaseModel:
        return service.reopen(cast(DecisionIdParams, params).decision_id)

    for method, handler, params_model, result_model in (
        ("inbox.list", list_inbox, EmptyParams, InboxPage),
        ("decision.get", get, DecisionIdParams, DecisionDetail),
        ("decision.act", act, ActParams, DecisionSummary),
        ("decision.reopen", reopen, DecisionIdParams, DecisionSummary),
    ):
        registrar.register(method, handler, params_model, result_model)
