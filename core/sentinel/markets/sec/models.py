from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Literal

TextStatus = Literal["extracted", "empty", "failed", "skipped"]
ContentStatus = Literal["full_text", "title_only", "fetch_failed"]


@dataclass(frozen=True)
class FilingRef:
    event_id: str
    instrument_id: str
    cik: str
    accession: str
    form_type: str
    published_at: datetime
    filing_date: date
    items: str | None
    primary_document: str
    primary_doc_description: str | None


@dataclass(frozen=True)
class IndexRow:
    seq: int
    description: str
    file_name: str
    doc_type: str
    url: str


@dataclass(frozen=True)
class EventFileDraft:
    seq: int
    file_name: str
    doc_type: str
    url: str
    text_status: TextStatus
    text: str | None
    char_count: int | None


@dataclass(frozen=True)
class FetchedEvent:
    event: FilingRef
    files: list[EventFileDraft]
    content_status: ContentStatus
    title: str | None = None
    fetched_at: datetime | None = None
    warnings: tuple[str, ...] = field(default_factory=tuple)


def file_warnings(files: list[EventFileDraft]) -> tuple[str, ...]:
    return ("FILE_FAILED",) if any(file.text_status == "failed" for file in files) else ()
