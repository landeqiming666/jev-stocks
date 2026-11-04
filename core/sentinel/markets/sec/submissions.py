from collections.abc import Mapping
from datetime import UTC, date, datetime

from .models import FilingRef
from .urls import canonical_cik, document_url, schema_error

FORMS = {"8-K", "8-K/A", "6-K"}
RECENT_FIELDS = (
    "accessionNumber",
    "filingDate",
    "reportDate",
    "acceptanceDateTime",
    "act",
    "form",
    "fileNumber",
    "filmNumber",
    "items",
    "core_type",
    "size",
    "isXBRL",
    "isInlineXBRL",
    "isXBRLNumeric",
    "primaryDocument",
    "primaryDocDescription",
)


def as_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise schema_error()
    return value.astimezone(UTC)


def parse_submissions(
    payload: Mapping[str, object],
    *,
    instrument_id: str,
    cik: str,
    since: datetime,
    until: datetime,
    fetched_at: datetime,
) -> list[FilingRef]:
    cik = canonical_cik(cik)
    since, until, fetched_at = (as_utc(value) for value in (since, until, fetched_at))
    filings = payload.get("filings") if isinstance(payload, Mapping) else None
    recent = filings.get("recent") if isinstance(filings, Mapping) else None
    if not isinstance(recent, Mapping):
        raise schema_error()
    columns: dict[str, list[object]] = {}
    for name in RECENT_FIELDS:
        column = recent.get(name)
        if not isinstance(column, list):
            raise schema_error()
        columns[name] = column
    if len({len(column) for column in columns.values()}) != 1:
        raise schema_error()
    result: dict[str, FilingRef] = {}
    for index, form in enumerate(columns["form"]):
        if not isinstance(form, str):
            raise schema_error()
        if form not in FORMS:
            continue
        values = {
            name: columns[name][index]
            for name in (
                "accessionNumber",
                "filingDate",
                "acceptanceDateTime",
                "items",
                "primaryDocument",
                "primaryDocDescription",
            )
        }
        if not all(isinstance(value, str) for value in values.values()):
            raise schema_error()
        strings = {name: str(value) for name, value in values.items()}
        try:
            published = min(
                as_utc(datetime.fromisoformat(strings["acceptanceDateTime"])), fetched_at
            )
            filing_date = date.fromisoformat(strings["filingDate"])
            document_url(cik, strings["accessionNumber"], strings["primaryDocument"])
        except (ValueError, TypeError):
            raise schema_error() from None
        if not since < published <= until:
            continue
        accession = strings["accessionNumber"]
        ref = FilingRef(
            "us:" + accession,
            instrument_id,
            cik,
            accession,
            form,
            published,
            filing_date,
            strings["items"] or None,
            strings["primaryDocument"],
            strings["primaryDocDescription"] or None,
        )
        if ref.event_id in result and result[ref.event_id] != ref:
            raise schema_error()
        result[ref.event_id] = ref
    return sorted(result.values(), key=lambda ref: (ref.published_at, ref.event_id))
