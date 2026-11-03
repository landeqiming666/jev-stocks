from dataclasses import replace
from datetime import date, datetime
from typing import cast

from sentinel import clock
from sentinel.errors import UserError
from sentinel.storage import Database

from .models import (
    ContentStatus,
    EventFileDraft,
    FetchedEvent,
    FilingRef,
    TextStatus,
    file_warnings,
)
from .submissions import FORMS, as_utc
from .title import build_title
from .urls import document_url, schema_error


def event_title(event: FetchedEvent) -> str:
    files = sorted(event.files, key=lambda file: (file.doc_type != "EX-99.1", file.seq))
    first = next(
        (
            file.text
            for file in files
            if file.text and (file.doc_type == "EX-99.1" or file.seq == 0)
        ),
        None,
    )
    return build_title(
        form_type=event.event.form_type,
        items=event.event.items,
        primary_doc_description=event.event.primary_doc_description,
        first_line=first,
    )


class SecFilingsRepository:
    def __init__(self, db: Database) -> None:
        self._db = db

    def get(self, ref: FilingRef) -> FetchedEvent | None:
        with self._db.read() as reader:
            reader.execute(
                """SELECT instrument_id, form_type, published_at, filing_date,
                items, content_status, title, fetched_at, url FROM event_doc WHERE event_id = ?""",
                [ref.event_id],
            )
            row = reader.fetchone()
            if row is None:
                return None
            if row[0] != ref.instrument_id:
                raise UserError("CONFLICT", reason="SEC_EVENT_IDENTITY")
            reader.execute(
                """SELECT seq, file_name, doc_type, url, text_status, text, char_count
                FROM event_file WHERE event_id = ? ORDER BY seq""",
                [ref.event_id],
            )
            files = [
                EventFileDraft(
                    cast(int, item[0]),
                    cast(str, item[1]),
                    cast(str, item[2]),
                    cast(str, item[3]),
                    cast(TextStatus, item[4]),
                    cast(str | None, item[5]),
                    cast(int | None, item[6]),
                )
                for item in reader.fetchall()
            ]
        stored_ref = replace(
            ref,
            cik=cast(str, row[8]).split("/")[-3].zfill(10),
            instrument_id=row[0],
            form_type=cast(str, row[1]),
            published_at=cast(datetime, row[2]),
            filing_date=cast(date, row[3]),
            items=cast(str | None, row[4]),
            primary_document=cast(str, row[8]).rsplit("/", 1)[1],
        )
        return FetchedEvent(
            stored_ref,
            files,
            cast(ContentStatus, row[5]),
            cast(str, row[6]),
            cast(datetime, row[7]),
            file_warnings(files),
        )

    def upsert(self, event: FetchedEvent) -> None:
        ref = event.event
        fetched_at = as_utc(event.fetched_at or clock.now())
        published_at = as_utc(ref.published_at)
        url = document_url(ref.cik, ref.accession, ref.primary_document)
        if (
            ref.event_id != "us:" + ref.accession
            or ref.form_type not in FORMS
            or published_at > fetched_at
            or event.content_status not in {"full_text", "title_only", "fetch_failed"}
        ):
            raise schema_error()
        seen: set[int] = set()
        for file in event.files:
            if (
                type(file.seq) is not int
                or not 0 <= file.seq <= 999
                or file.seq in seen
                or file.text_status not in {"extracted", "empty", "failed", "skipped"}
                or file.url != document_url(ref.cik, ref.accession, file.file_name)
                or (file.seq == 0 and file.file_name != ref.primary_document)
                or (file.text is not None and file.char_count != len(file.text))
                or (file.text is None and file.char_count is not None)
            ):
                raise schema_error()
            seen.add(file.seq)
        title = event.title if event.title is not None else event_title(event)
        with self._db.write() as tx:
            tx.execute(
                "SELECT instrument_id, url, title FROM event_doc WHERE event_id = ?", [ref.event_id]
            )
            existing = tx.fetchone()
            if existing is not None:
                if existing[:2] != (ref.instrument_id, url):
                    raise UserError("CONFLICT", reason="SEC_EVENT_IDENTITY")
                if existing[2] != title:
                    tx.execute(
                        """SELECT 1 FROM event_passage
                        WHERE event_id = ? AND file_seq = -1 LIMIT 1""",
                        [ref.event_id],
                    )
                    if tx.fetchone() is not None:
                        raise UserError("CONFLICT", reason="SEC_PASSAGE_REFERENCE")
            tx.execute(
                """INSERT INTO event_doc VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT (event_id) DO UPDATE SET
                instrument_id = excluded.instrument_id, market = excluded.market,
                form_type = excluded.form_type, title = excluded.title,
                published_at = excluded.published_at, filing_date = excluded.filing_date,
                url = excluded.url, items = excluded.items,
                content_status = excluded.content_status,
                fetched_at = excluded.fetched_at, source = excluded.source""",
                [
                    ref.event_id,
                    ref.instrument_id,
                    "us",
                    ref.form_type,
                    title,
                    published_at,
                    ref.filing_date,
                    url,
                    ref.items,
                    event.content_status,
                    fetched_at,
                    "sec_edgar",
                ],
            )
            for file in event.files:
                tx.execute(
                    """SELECT file_name, doc_type, url, text FROM event_file
                    WHERE event_id = ? AND seq = ?""",
                    [ref.event_id, file.seq],
                )
                previous = tx.fetchone()
                if previous is not None:
                    if previous[:3] != (file.file_name, file.doc_type, file.url):
                        raise UserError("CONFLICT", reason="SEC_FILE_IDENTITY")
                    if previous[3] != file.text:
                        tx.execute(
                            """SELECT 1 FROM event_passage
                            WHERE event_id = ? AND file_seq = ? LIMIT 1""",
                            [ref.event_id, file.seq],
                        )
                        if tx.fetchone() is not None:
                            raise UserError("CONFLICT", reason="SEC_PASSAGE_REFERENCE")
                # 04 的永久引用要求保留既有行；仅覆盖同键的非键列。
                tx.execute(
                    """INSERT INTO event_file VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT (event_id, seq) DO UPDATE SET
                    file_name = excluded.file_name, doc_type = excluded.doc_type,
                    url = excluded.url,
                    text_status = excluded.text_status, text = excluded.text,
                    char_count = excluded.char_count""",
                    [
                        ref.event_id,
                        file.seq,
                        file.file_name,
                        file.doc_type,
                        file.url,
                        file.text_status,
                        file.text,
                        file.char_count,
                    ],
                )
