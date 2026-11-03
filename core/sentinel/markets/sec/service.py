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
from .repository import SecFilingsRepository, event_title
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

    def _fetch(self, ref: FilingRef, fetched_at: datetime) -> FetchedEvent:
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
        files = [self._file(row) for row in selected]
        files.extend(self._file(row, skipped=True) for row in skipped)
        files.sort(key=lambda file: file.seq)
        status: ContentStatus = "title_only"
        if any(file.text for file in files):
            status = "full_text"
        elif any(file.text_status == "failed" for file in files) or "INDEX_FAILED" in warnings:
            status = "fetch_failed"
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
            if stored is not None and stored.content_status in {"full_text", "title_only"}:
                if stored.warnings:
                    log_event(_LOGGER, logging.WARNING, event="sec.cached_file_failed")
                result.append(stored)
                continue
            event = self._fetch(ref, fetched_at)
            self._repo.upsert(event)
            result.append(event)
        return result
