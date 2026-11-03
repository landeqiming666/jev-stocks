import logging
import re
from collections.abc import Sequence
from dataclasses import replace
from pathlib import PurePosixPath

from selectolax.lexbor import LexborHTMLParser

from sentinel.errors import SourceError
from sentinel.logging_setup import get_logger, log_event

from .models import IndexRow
from .urls import directory, document_url, resolve_link, schema_error, validate_archive_url

MAX_EX99 = 3
_EX99_TYPE = re.compile(r"EX-99(?:\.[0-9]+)?")
_LOGGER = get_logger(__name__)


def parse_index(html: str, *, base_url: str) -> list[IndexRow]:
    tree = LexborHTMLParser(html)
    table = None
    for candidate in tree.css("table"):
        headers = [node.text(strip=True) for node in candidate.css("th")]
        if not headers:
            first = candidate.css_first("tr")
            headers = [node.text(strip=True) for node in first.css("td")] if first else []
        if all(name in headers for name in ("Seq", "Description", "Document", "Type")):
            table = candidate
            break
    if table is None:
        log_event(_LOGGER, logging.WARNING, event="sec.index_missing")
        return []
    positions = [headers.index(name) for name in ("Seq", "Description", "Document", "Type")]
    result = []
    for tr in table.css("tr"):
        cells = tr.css("td")
        if len(cells) <= max(positions) or any(cell.attributes.get("colspan") for cell in cells):
            continue
        seq_cell, description_cell, document_cell, type_cell = [cells[pos] for pos in positions]
        raw_seq = seq_cell.text(strip=True)
        link = document_cell.css_first("a")
        if (
            not raw_seq.isascii()
            or not raw_seq.isdigit()
            or not 0 <= int(raw_seq) <= 999
            or not link
        ):
            log_event(_LOGGER, logging.WARNING, event="sec.index_row_invalid")
            continue
        try:
            url = resolve_link(base_url, link.attributes.get("href") or "")
        except (SourceError, ValueError):
            log_event(_LOGGER, logging.WARNING, event="sec.index_link_rejected")
            continue
        result.append(
            IndexRow(
                int(raw_seq),
                description_cell.text(strip=True),
                url.rsplit("/", 1)[1],
                type_cell.text(strip=True),
                url,
            )
        )
    return result


def is_html(file_name: str) -> bool:
    return PurePosixPath(file_name).suffix.lower() in {".htm", ".html", ".xhtml"}


def select_files(
    rows: Sequence[IndexRow],
    *,
    cik: str,
    accession: str,
    primary_document: str,
) -> tuple[list[IndexRow], list[IndexRow]]:
    base = directory(cik, accession)
    primary = IndexRow(0, "", primary_document, "", document_url(cik, accession, primary_document))
    selected: list[IndexRow] = []
    skipped: list[IndexRow] = []
    seen_seq: set[int] = set()
    seen_files: set[str] = set()
    for row in sorted(rows, key=lambda row: row.seq):
        validate_archive_url(row.url, expected_directory=base)
        if (
            type(row.seq) is not int
            or not 0 <= row.seq <= 999
            or row.url.rsplit("/", 1)[1] != row.file_name
            or row.seq in seen_seq
            or row.file_name in seen_files
        ):
            raise schema_error("SEC_INDEX_CONFLICT")
        seen_seq.add(row.seq)
        seen_files.add(row.file_name)
        if row.file_name == primary_document:
            primary = replace(row, seq=0)
        elif row.seq == 0:
            raise schema_error("SEC_INDEX_CONFLICT")
        elif (
            _EX99_TYPE.fullmatch(row.doc_type) is not None
            and is_html(row.file_name)
            and len(selected) < MAX_EX99
        ):
            selected.append(row)
        else:
            skipped.append(row)
    return [primary, *selected], skipped
