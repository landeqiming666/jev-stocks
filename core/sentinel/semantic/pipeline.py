from __future__ import annotations

import logging
import re
import threading
from collections.abc import Sequence
from dataclasses import dataclass, replace
from datetime import date
from typing import Literal

import duckdb

from sentinel import clock
from sentinel.domain.classify import Probabilities, classify, headline, validate_probability
from sentinel.errors import EngineError, InternalError, SentinelError
from sentinel.ids import new_id
from sentinel.storage.db import Database

from .base import (
    CancelToken,
    EngineName,
    EvidenceScore,
    PairInput,
    PairScore,
    PassageInput,
    SemanticEngine,
    ThesisInput,
    validate_count,
)
from .budget import estimate_tokens, reserve_tokens
from .cache import (
    QUESTION_SET_VERSION,
    DecisionRow,
    add_usage,
    decision_cache_key,
    find_decisions,
    insert_decision,
    norm_text,
    passage_content_hash,
    thesis_content_hash,
    used_today,
)
from .evidence import (
    MAX_EVIDENCE_SENTENCES,
    EvidenceResult,
    evidence_from_score,
    fallback_evidence,
    prepare_sentences,
    select_representative,
    valid_evidence,
)
from .questions import build_evidence_questions, build_score_questions

MAX_PASSAGES = 60
_LOG = logging.getLogger(__name__)
ContentStatus = Literal["full_text", "title_only"]


@dataclass(frozen=True)
class PassageRecord:
    passage_id: str
    event_id: str
    instrument_id: str
    seq: int
    text: str
    content_hash: str
    content_status: ContentStatus

    def as_input(self) -> PassageInput:
        return PassageInput(self.passage_id, self.text, passage_content_hash(self.text))


@dataclass(frozen=True)
class BatchContext:
    run_id: str
    batch_id: str
    event_id: str
    instrument_id: str
    company: str


@dataclass(frozen=True)
class BatchOutcome:
    status: Literal["succeeded"]
    new_decisions: int
    cached_decisions: int
    input_tokens: int
    estimated_tokens: int
    evidence_failures: int
    truncated_passages: bool


def _flavor(engine: EngineName) -> Literal["direct", "jevdb"]:
    return "direct" if engine == "jev_direct" else "jevdb"


def estimate_pair_tokens(pair: PairInput, engine: EngineName) -> int:
    questions = build_score_questions([pair.thesis], flavor=_flavor(engine))
    chars = sum(
        len(q.instructions) + len(q.true_text) + len(q.false_text) for q in questions.values()
    )
    return estimate_tokens(
        len(pair.thesis.statement)
        + len(pair.thesis.kill_condition or "")
        + len(pair.passage.text)
        + chars
    )


def _identity(value: str) -> None:
    if not isinstance(value, str) or re.fullmatch(r"[A-Za-z0-9_.:-]+", value) is None:
        raise ValueError("invalid entity identity")


def _key(pair: PairInput, engine: EngineName, model: str) -> str:
    return decision_cache_key(
        engine,
        model,
        QUESTION_SET_VERSION,
        pair.thesis.content_hash,
        pair.passage.content_hash,
        thesis_id=pair.thesis.thesis_id,
        thesis_version=pair.thesis.version,
        passage_id=pair.passage.passage_id,
    )


def _pair_identity(pair: PairInput) -> tuple[str, int, str]:
    return pair.thesis.thesis_id, pair.thesis.version, pair.passage.passage_id


@dataclass
class _Usage:
    input_tokens: int = 0
    estimated_tokens: int = 0
    requests: int = 0

    def add(self, tokens: int, estimated: bool, requests: int = 1) -> None:
        validate_count(tokens)
        if estimated:
            self.estimated_tokens += tokens
        else:
            self.input_tokens += tokens
        self.requests += requests

    @property
    def total(self) -> int:
        return self.input_tokens + self.estimated_tokens


class DecisionPipeline:
    def __init__(
        self, db: Database, engine: SemanticEngine, *, model_id: str, daily_budget: int
    ) -> None:
        validate_count(daily_budget)
        if not isinstance(model_id, str) or re.fullmatch(r"jev-\d+\.\d+\.\d+", model_id) is None:
            raise ValueError("model_id must be a pinned Jev version")
        if engine.name not in ("jev_direct", "jevdb"):
            raise ValueError("unknown semantic engine")
        self.db, self.engine = db, engine
        self.model_id, self.daily_budget = model_id, daily_budget
        self._lock = threading.Lock()

    def _log(self, ctx: BatchContext, reason: str, *, warning: bool = True) -> None:
        _LOG.log(
            logging.WARNING if warning else logging.INFO,
            "run_id=%s batch_id=%s event_id=%s reason=%s",
            ctx.run_id,
            ctx.batch_id,
            ctx.event_id,
            reason,
        )

    def process_batch(
        self,
        ctx: BatchContext,
        theses: Sequence[ThesisInput],
        passages: Sequence[PassageRecord],
        cancel: CancelToken,
    ) -> BatchOutcome:
        cancel.raise_if_cancelled()
        pairs, records, truncated = self._prepare(ctx, theses, passages)
        # 同实例跨网络阶段互斥，等待者仍能及时取消；锁不占用数据库事务。
        while not self._lock.acquire(timeout=0.02):
            cancel.raise_if_cancelled()
        try:
            cancel.raise_if_cancelled()
            if truncated:
                self._log(ctx, "PASSAGES_TRUNCATED")
            try:
                return self._process(ctx, pairs, records, truncated, cancel)
            except duckdb.Error:
                self._log(ctx, "DATABASE_FAILURE")
                raise InternalError(detail="decision pipeline database operation failed") from None
        finally:
            self._lock.release()

    def _prepare(
        self, ctx: BatchContext, theses: Sequence[ThesisInput], passages: Sequence[PassageRecord]
    ) -> tuple[list[PairInput], dict[str, PassageRecord], bool]:
        for value in (ctx.run_id, ctx.batch_id, ctx.event_id, ctx.instrument_id):
            _identity(value)
        if not norm_text(ctx.company):
            raise ValueError("company must be nonempty")
        validate_count(len(theses), minimum=1, maximum=5)
        validate_count(len(passages), minimum=1)
        if len({t.thesis_id for t in theses}) != len(theses):
            raise ValueError("duplicate thesis identities")
        if len({t.ref for t in theses}) != len(theses):
            raise ValueError("duplicate thesis refs")
        if len({p.passage_id for p in passages}) != len(passages):
            raise ValueError("duplicate passage identities")
        normalized = []
        for t in theses:
            t.__post_init__()
            _identity(t.thesis_id)
            normalized.append(
                replace(t, content_hash=thesis_content_hash(t.statement, t.kill_condition))
            )
        for p in passages:
            _identity(p.passage_id)
            validate_count(p.seq)
            if p.event_id != ctx.event_id or p.instrument_id != ctx.instrument_id:
                raise ValueError("passage belongs to another batch")
            if p.content_status not in ("full_text", "title_only"):
                raise ValueError("invalid content status")
            p.as_input().__post_init__()
        limited = sorted(passages, key=lambda p: (p.seq, p.passage_id))[:MAX_PASSAGES]
        records = {p.passage_id: p for p in limited}
        pairs = [PairInput(t, p.as_input()) for t in normalized for p in limited]
        pairs.sort(key=_pair_identity)
        return pairs, records, len(passages) > MAX_PASSAGES

    def _validate_cached(
        self, row: DecisionRow, pair: PairInput, ctx: BatchContext, record: PassageRecord
    ) -> DecisionRow:
        if (
            row.thesis_id,
            row.thesis_version,
            row.passage_id,
            row.event_id,
            row.instrument_id,
            row.engine,
            row.model_id,
            row.question_set_version,
            row.cache_key,
            row.content_status,
        ) != (
            pair.thesis.thesis_id,
            pair.thesis.version,
            pair.passage.passage_id,
            ctx.event_id,
            ctx.instrument_id,
            self.engine.name,
            self.model_id,
            QUESTION_SET_VERSION,
            _key(pair, self.engine.name, self.model_id),
            record.content_status,
        ):
            raise InternalError(detail="cached decision identity mismatch")
        if row.relation not in ("none", "support", "weaken", "overturn", "uncertain"):
            raise InternalError(detail="invalid cached decision relation")
        try:
            Probabilities(
                row.p_relevant, row.p_against, row.p_contradicts, row.p_kill_met, row.p_supports
            )
            validate_probability(row.headline)
            if (
                type(row.tokens_estimated) is not bool
                or row.tokens_estimated != (self.engine.name == "jevdb")
                or (row.p_kill_met is None) != (pair.thesis.kill_condition is None)
            ):
                raise ValueError("invalid cached score shape")
            if row.input_tokens is not None:
                validate_count(row.input_tokens)
            if row.latency_ms is not None:
                validate_count(row.latency_ms)
        except (TypeError, ValueError):
            raise InternalError(detail="invalid cached score") from None
        return replace(row, seq=record.seq)

    def _budget_allowed(self, raw: int, today: date, extra: int = 0) -> bool:
        with self.db.read() as reader:
            used = used_today(reader, today)
        return used + extra + reserve_tokens(raw) <= self.daily_budget

    def _validate_scores(self, pairs: Sequence[PairInput], scores: Sequence[PairScore]) -> None:
        expected = {_pair_identity(p): p for p in pairs}
        try:
            if len(scores) != len(pairs):
                raise ValueError("wrong pair count")
            seen = set()
            for score in scores:
                if not isinstance(score, PairScore):
                    raise ValueError("invalid pair result")
                score.__post_init__()
                score.probabilities.__post_init__()
                identity = (score.thesis_id, score.version, score.passage_id)
                if identity not in expected or identity in seen or score.model_id != self.model_id:
                    raise ValueError("pair or model mismatch")
                pair = expected[identity]
                if score.tokens_estimated != (self.engine.name == "jevdb") or (
                    score.probabilities.kill_met is None
                ) != (pair.thesis.kill_condition is None):
                    raise ValueError("invalid token or probability shape")
                seen.add(identity)
        except (AttributeError, TypeError, ValueError):
            raise EngineError("MODEL_ERROR", detail="INVALID_PAIR_RESPONSE") from None

    def _new_row(
        self, score: PairScore, pair: PairInput, ctx: BatchContext, record: PassageRecord
    ) -> DecisionRow:
        p = score.probabilities
        return DecisionRow(
            new_id(),
            score.thesis_id,
            score.version,
            score.passage_id,
            ctx.event_id,
            ctx.instrument_id,
            classify(p),
            p.relevant,
            p.against,
            p.contradicts,
            p.kill_met,
            p.supports,
            headline(p),
            None,
            None,
            None,
            self.engine.name,
            score.model_id,
            QUESTION_SET_VERSION,
            _key(pair, self.engine.name, self.model_id),
            score.input_tokens,
            score.tokens_estimated,
            score.latency_ms,
            record.content_status,
            clock.now(),
            record.seq,
        )

    def _process(
        self,
        ctx: BatchContext,
        pairs: list[PairInput],
        records: dict[str, PassageRecord],
        truncated: bool,
        cancel: CancelToken,
    ) -> BatchOutcome:
        by_key = {_key(p, self.engine.name, self.model_id): p for p in pairs}
        with self.db.read() as reader:
            cached = find_decisions(reader, list(by_key))
        decisions = {
            key: self._validate_cached(
                row, by_key[key], ctx, records[by_key[key].passage.passage_id]
            )
            for key, row in cached.items()
        }
        missing = [p for key, p in by_key.items() if key not in cached]
        inserted_keys: set[str] = set()
        scoring_usage = _Usage()
        if missing:
            today = clock.now().date()
            raw = sum(estimate_pair_tokens(p, self.engine.name) for p in missing)
            if not self._budget_allowed(raw, today):
                raise EngineError("BUDGET_EXCEEDED")
            cancel.raise_if_cancelled()
            scores = self.engine.score_pairs(ctx.company, missing, cancel)
            cancel.raise_if_cancelled()
            self._validate_scores(missing, scores)
            by_identity = {_pair_identity(p): p for p in missing}
            new_rows = [
                self._new_row(
                    s,
                    by_identity[(s.thesis_id, s.version, s.passage_id)],
                    ctx,
                    records[s.passage_id],
                )
                for s in scores
            ]
            scoring_usage.add(sum(s.input_tokens for s in scores), self.engine.name == "jevdb")
            cancel.raise_if_cancelled()
            with self.db.write() as tx:
                cancel.raise_if_cancelled()
                for row in new_rows:
                    saved, inserted = insert_decision(tx, row)
                    decisions[row.cache_key] = self._validate_cached(
                        saved, by_key[row.cache_key], ctx, records[row.passage_id]
                    )
                    if inserted:
                        inserted_keys.add(row.cache_key)
                add_usage(
                    tx,
                    today,
                    self.engine.name,
                    self.model_id,
                    scoring_usage.input_tokens,
                    scoring_usage.estimated_tokens,
                    scoring_usage.requests,
                )
                cancel.raise_if_cancelled()
        cancel.raise_if_cancelled()
        grouped: dict[tuple[str, str], list[DecisionRow]] = {}
        for row in decisions.values():
            grouped.setdefault((row.thesis_id, row.event_id), []).append(row)
        representatives = [
            rep for group in grouped.values() if (rep := select_representative(group)) is not None
        ]
        plans, evidence_usage, failures = self._evidence(
            ctx, representatives, by_key, records, inserted_keys, cancel
        )
        if plans:
            cancel.raise_if_cancelled()
            with self.db.write() as tx:
                cancel.raise_if_cancelled()
                for row, evidence in plans:
                    tx.execute(
                        "UPDATE decision SET evidence_kind=?, evidence_start=?, "
                        "evidence_end=? WHERE decision_id=? AND evidence_kind IS NULL",
                        [evidence.kind, evidence.start, evidence.end, row.decision_id],
                    )
                for day, u in evidence_usage.items():
                    add_usage(
                        tx,
                        day,
                        self.engine.name,
                        self.model_id,
                        u.input_tokens,
                        u.estimated_tokens,
                        u.requests,
                    )
                # 同一 tx 回读 UPDATE 及并发胜出行，返回成功前核对每条代表的证据。
                final = find_decisions(tx, [r.cache_key for r in representatives])
                for row in representatives:
                    final_saved = final.get(row.cache_key)
                    if final_saved is None:
                        raise InternalError(detail="representative disappeared")
                    final_saved = self._validate_cached(
                        final_saved, by_key[row.cache_key], ctx, records[row.passage_id]
                    )
                    if not self._valid(final_saved, records[row.passage_id]):
                        raise InternalError(detail="representative has no valid evidence")
                cancel.raise_if_cancelled()
        cancel.raise_if_cancelled()
        self._log(ctx, "SUCCEEDED", warning=False)
        return BatchOutcome(
            "succeeded",
            len(inserted_keys),
            len(pairs) - len(inserted_keys),
            scoring_usage.input_tokens + sum(u.input_tokens for u in evidence_usage.values()),
            scoring_usage.estimated_tokens
            + sum(u.estimated_tokens for u in evidence_usage.values()),
            failures,
            truncated,
        )

    @staticmethod
    def _valid(row: DecisionRow, record: PassageRecord) -> bool:
        return valid_evidence(
            row.evidence_kind,
            row.evidence_start,
            row.evidence_end,
            record.text,
            content_status=record.content_status,
        )

    def _evidence(
        self,
        ctx: BatchContext,
        representatives: list[DecisionRow],
        pairs: dict[str, PairInput],
        records: dict[str, PassageRecord],
        inserted_keys: set[str],
        cancel: CancelToken,
    ) -> tuple[list[tuple[DecisionRow, EvidenceResult]], dict[date, _Usage], int]:
        plans = []
        usages: dict[date, _Usage] = {}
        failures = 0
        for row in representatives:
            cancel.raise_if_cancelled()
            rec = records[row.passage_id]
            if self._valid(row, rec):
                continue
            if row.evidence_kind is not None:
                raise InternalError(detail="corrupt cached evidence offsets")
            fallback = fallback_evidence(rec.text, rec.content_status)
            if rec.content_status == "title_only":
                plans.append((row, fallback))
                continue
            if row.cache_key not in inserted_keys:
                self._log(ctx, "CACHED_EVIDENCE_REPAIRED")
                plans.append((row, replace(fallback, warn="CACHED_EVIDENCE_REPAIRED")))
                continue
            sentences = prepare_sentences(rec.text)
            if len(sentences) == MAX_EVIDENCE_SENTENCES and sentences[-1].end < len(
                rec.text.rstrip()
            ):
                self._log(ctx, "SENTENCES_TRUNCATED")
            if not sentences:
                plans.append((row, replace(fallback, warn="NO_SENTENCES")))
                continue
            thesis = pairs[row.cache_key].thesis
            questions = build_evidence_questions(
                row.relation,
                len(sentences),
                has_kill=thesis.kill_condition is not None,
                flavor=_flavor(self.engine.name),
            )
            chars = len(thesis.statement) + len(thesis.kill_condition or "")
            chars += sum(len(s.text) for s in sentences)
            chars += sum(
                len(q.instructions) + len(q.true_text) + len(q.false_text)
                for q in questions.values()
            )
            today = clock.now().date()
            pending = usages.get(today, _Usage()).total
            if not self._budget_allowed(estimate_tokens(chars), today, pending):
                self._log(ctx, "EVIDENCE_BUDGET_EXCEEDED")
                plans.append((row, replace(fallback, warn="EVIDENCE_BUDGET_EXCEEDED")))
                continue
            try:
                cancel.raise_if_cancelled()
                score = self.engine.locate_evidence(
                    thesis, row.relation, [s.text for s in sentences], cancel
                )
                cancel.raise_if_cancelled()
                if not isinstance(score, EvidenceScore):
                    raise EngineError("MODEL_ERROR", detail="INVALID_EVIDENCE_RESPONSE")
                score.__post_init__()
                usages.setdefault(today, _Usage()).add(
                    score.input_tokens, self.engine.name == "jevdb"
                )
                if score.model_id != self.model_id or score.tokens_estimated != (
                    self.engine.name == "jevdb"
                ):
                    raise EngineError("MODEL_ERROR", detail="EVIDENCE_MODEL_MISMATCH")
                evidence = evidence_from_score(rec.text, sentences, score.sentence_probabilities)
            except SentinelError as exc:
                if exc.code not in ("MODEL_ERROR", "TIMEOUT", "RATE_LIMITED"):
                    raise
                cancel.raise_if_cancelled()
                evidence = replace(fallback, warn=exc.code.value)
                failures += 1
            if evidence.warn:
                self._log(ctx, evidence.warn)
            plans.append((row, evidence))
        return plans, usages, failures
