from __future__ import annotations

import hashlib
import logging
from typing import cast

import duckdb

from sentinel.errors import InternalError, SourceError, UserError
from sentinel.ids import passage_id
from sentinel.markets.sec.models import FetchedEvent
from sentinel.semantic.cache import passage_content_hash
from sentinel.semantic.pipeline import PassageRecord
from sentinel.semantic.segment import MAX_PASSAGES_PER_DOCUMENT, TextSpan, split_passages
from sentinel.storage.db import Database, SqlExecutor

_LOG = logging.getLogger(__name__)


def read_passages(reader: SqlExecutor, event_id: str, instrument_id: str) -> list[PassageRecord]:
    reader.execute(
        "SELECT p.passage_id, p.text, p.content_hash, p.file_seq FROM "
        "event_passage p "
        "JOIN event_doc e ON e.event_id=p.event_id "
        "WHERE p.event_id=? AND e.instrument_id=? ORDER BY p.file_seq, p.seq,"
        " p.passage_id",
        [event_id, instrument_id],
    )
    return [
        PassageRecord(
            cast(str, row[0]),
            event_id,
            instrument_id,
            seq,
            cast(str, row[1]),
            cast(str, row[2]),
            "title_only" if row[3] == -1 else "full_text",
        )
        for seq, row in enumerate(reader.fetchall())
    ]


def persist_passages(db: Database, event: FetchedEvent) -> list[PassageRecord]:
    ref = event.event
    if event.content_status == "fetch_failed" or any(
        f.text_status == "failed" for f in event.files
    ):
        raise SourceError("SOURCE_UNAVAILABLE", reason="SEC_FETCH_FAILED")
    drafts: list[tuple[object, ...]] = []
    if event.content_status == "title_only":
        text = event.title or ""
        if text.strip():
            text.encode("utf-8")
            if len(text) > 1200:
                raise InternalError(detail="scan title exceeds passage limit")
            # C-00 helper 拒绝 -1；标题仍按 04 的同一永久 ID 公式计算。
            identity = hashlib.sha256(f"{ref.event_id}|-1|0|{len(text)}".encode()).hexdigest()[:32]
            drafts.append(
                (identity, ref.event_id, -1, 0, text, 0, len(text), passage_content_hash(text))
            )
    elif event.content_status == "full_text":
        seen: set[int] = set()
        for file in sorted(event.files, key=lambda f: f.seq):
            if file.seq in seen:
                raise InternalError(detail="duplicate filing file sequence")
            seen.add(file.seq)
            if file.text_status != "extracted" or not file.text:
                continue
            file.text.encode("utf-8")
            result = split_passages(file.text, max_chars=1200)
            if result.truncated:
                _LOG.warning("event_id=%s reason=FILE_PASSAGES_TRUNCATED", ref.event_id)
            for seq, span in enumerate(result.passages):
                drafts.append(_draft(ref.event_id, file.seq, seq, span))
    else:
        raise InternalError(detail="invalid scan content status")
    try:
        with db.write() as tx:
            tx.execute("SELECT instrument_id FROM event_doc WHERE event_id=?", [ref.event_id])
            if tx.fetchone() != (ref.instrument_id,):
                raise InternalError(detail="scan event identity missing")
            for draft in drafts:
                tx.execute(
                    "INSERT INTO event_passage VALUES (?, ?, ?, ?, ?, ?, ?, ?) "
                    "ON CONFLICT(passage_id) DO NOTHING",
                    list(draft),
                )
                tx.execute("SELECT * FROM event_passage WHERE passage_id=?", [draft[0]])
                if tx.fetchone() != draft:
                    raise UserError("CONFLICT", reason="SCAN_PASSAGE_IDENTITY")
            saved = read_passages(tx, ref.event_id, ref.instrument_id)
    except duckdb.Error:
        raise InternalError(detail="scan passage write failed") from None
    if len(saved) > MAX_PASSAGES_PER_DOCUMENT:
        _LOG.warning("event_id=%s reason=EVENT_PASSAGES_TRUNCATED", ref.event_id)
    if not saved:
        _LOG.warning("event_id=%s reason=NO_SCORABLE_TEXT", ref.event_id)
    return saved


def _draft(event_id: str, file_seq: int, seq: int, span: TextSpan) -> tuple[object, ...]:
    return (
        passage_id(event_id, file_seq, span.start, span.end),
        event_id,
        file_seq,
        seq,
        span.text,
        span.start,
        span.end,
        passage_content_hash(span.text),
    )
