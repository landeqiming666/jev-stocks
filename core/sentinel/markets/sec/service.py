import logging
from collections.abc import Callable
from dataclasses import replace
from datetime import datetime

from sentinel.errors import SourceError
from sentinel.logging_setup import get_logger, log_event
from sentinel.markets.instruments.models import Instrument

from .client import SecFilingsClient
from .extract import html_to_text
from .index import is_html, select_files
from .models import (
    ContentStatus,
    EventFileDraft,
    FetchedEvent,
    FilingRef,
    IndexRow,
    TextStatus,
    file_warnings,
)
from .repository import SecFilingsRepository, ensure_file_identity, event_title
from .submissions import as_utc

_LOGGER = get_logger(__name__)


class SecFilingsService:
    def __init__(
        self,
        client: SecFilingsClient,
        repo: SecFilingsRepository,
        clock: Callable[[], datetime],
    ) -> None:
        self._client = client
        self._repo = repo
        self._clock = clock

    def _file(self, row: IndexRow, *, skipped: bool = False) -> EventFileDraft:
        status: TextStatus = "skipped"
        text = None
        count = None
        if not skipped and is_html(row.file_name):
            try:
                text = html_to_text(self._client.fetch_file(row.url))
            except SourceError as error:
                status = "failed"
                log_event(
                    _LOGGER,
                    logging.WARNING,
                    event="sec.file_failed",
                    error_code=error.code.value,
                    reason=error.reason,
                )
            else:
                status = "extracted" if text else "empty"
                count = len(text)
        return EventFileDraft(row.seq, row.file_name, row.doc_type, row.url, status, text, count)

    def _fetch(
        self,
        ref: FilingRef,
        fetched_at: datetime,
        stored: FetchedEvent | None,
    ) -> FetchedEvent:
        warnings: tuple[str, ...] = ()
        try:
            rows = self._client.fetch_index(ref)
        except SourceError as error:
            rows = []
            warnings = ("INDEX_FAILED",)
            log_event(
                _LOGGER,
                logging.WARNING,
                event="sec.index_failed",
                error_code=error.code.value,
                reason=error.reason,
            )
        if not rows and not warnings:
            warnings = ("PRIMARY_ONLY",)
        try:
            selected, skipped = select_files(
                rows, cik=ref.cik, accession=ref.accession, primary_document=ref.primary_document
            )
        except SourceError:
            log_event(_LOGGER, logging.WARNING, event="sec.index_conflict")
            selected, skipped = select_files(
                [], cik=ref.cik, accession=ref.accession, primary_document=ref.primary_document
            )
            warnings = (*warnings, "INDEX_CONFLICT")
        selected[0] = replace(selected[0], doc_type=ref.form_type)
        previous = stored.files if stored is not None else []
        ensure_file_identity(previous, [*selected, *skipped])
        # 索引消失或附件超出本轮上限不能抹掉旧 failed，成功正文与引用也必须保留。
        merged = {file.seq: file for file in previous}
        for row in selected:
            existing = merged.get(row.seq)
            if existing is None or existing.text_status not in {"extracted", "empty"}:
                merged[row.seq] = self._file(row)
        for row in skipped:
            if row.seq not in merged:
                merged[row.seq] = self._file(row, skipped=True)
        files = sorted(merged.values(), key=lambda file: file.seq)
        status: ContentStatus = "title_only"
        if any(file.text_status == "failed" for file in files) or any(
            warning in {"INDEX_FAILED", "INDEX_CONFLICT"} for warning in warnings
        ):
            status = "fetch_failed"
        elif any(file.text for file in files):
            status = "full_text"
        event = FetchedEvent(
            ref, files, status, fetched_at=fetched_at, warnings=(*warnings, *file_warnings(files))
        )
        return replace(event, title=event_title(event))

    def fetch_for_instrument(
        self,
        instrument: Instrument,
        *,
        since: datetime,
        until: datetime,
    ) -> list[FetchedEvent]:
        fetched_at = as_utc(self._clock())
        refs = self._client.list_filings(instrument, since, until, fetched_at)
        result = []
        for ref in sorted(refs, key=lambda ref: (ref.published_at, ref.event_id)):
            stored = self._repo.get(ref)
            if (
                stored is not None
                and stored.content_status in {"full_text", "title_only"}
                and not any(file.text_status == "failed" for file in stored.files)
            ):
                result.append(stored)
                continue
            event = self._fetch(ref, fetched_at, stored)
            self._repo.upsert(event)
            saved = self._repo.get(ref)
            assert saved is not None
            result.append(
                replace(saved, warnings=tuple(dict.fromkeys((*event.warnings, *saved.warnings))))
            )
        return result
