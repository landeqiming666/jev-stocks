from collections.abc import Callable, Mapping
from datetime import datetime

from sentinel import __version__
from sentinel.domain.contact import is_valid_sec_email
from sentinel.errors import UserError
from sentinel.http import HttpClient
from sentinel.markets.instruments.models import Instrument

from .index import parse_index
from .models import FilingRef, IndexRow
from .submissions import parse_submissions
from .urls import ARCHIVE_BASE, canonical_cik, document_url, schema_error, validate_archive_url

__all__ = ["ARCHIVE_BASE", "SecFilingsClient"]


class SecFilingsClient:
    def __init__(
        self,
        http: HttpClient,
        *,
        email_provider: Callable[[], str | None] | None = None,
    ) -> None:
        self._http = http
        self._email_provider = email_provider

    def _headers(self) -> dict[str, str]:
        email = self._email_provider() if self._email_provider is not None else None
        if not is_valid_sec_email(email):
            raise UserError("CONFIG_REQUIRED", params={"missing": ["secEmail"]})
        return {"User-Agent": f"Sentinel/{__version__} {email}"}

    def list_filings(
        self,
        instrument: Instrument,
        since: datetime,
        until: datetime,
        fetched_at: datetime,
    ) -> list[FilingRef]:
        headers = self._headers()
        cik = canonical_cik(instrument.cik)
        if instrument.market != "us":
            raise schema_error()
        payload = self._http.get_json(
            f"https://data.sec.gov/submissions/CIK{cik}.json", source="sec", headers=headers
        )
        if not isinstance(payload, Mapping):
            raise schema_error()
        return parse_submissions(
            payload,
            instrument_id=instrument.instrument_id,
            cik=cik,
            since=since,
            until=until,
            fetched_at=fetched_at,
        )

    def fetch_file(self, url: str) -> str:
        headers = self._headers()
        validate_archive_url(url)
        return self._http.get_text(url, source="sec", headers=headers)

    def fetch_index(self, ref: FilingRef) -> list[IndexRow]:
        url = document_url(ref.cik, ref.accession, ref.accession + "-index.htm")
        return parse_index(self.fetch_file(url), base_url=url)
