from datetime import UTC, datetime
from pathlib import Path

import pytest

from sentinel.markets.instruments.models import Instrument
from sentinel.markets.sec import FilingRef, IndexRow, SecFilingsRepository, SecFilingsService
from sentinel.storage import Database

FIXTURES = Path(__file__).resolve().parents[3] / "fixtures" / "sec"
NOW = datetime(2026, 7, 30, 23, tzinfo=UTC)
SINCE = datetime(2026, 7, 20, tzinfo=UTC)
CIK = "0001234567"
ACCESSION = "0001234567-26-000001"
BASE = f"https://www.sec.gov/Archives/edgar/data/1234567/{ACCESSION.replace('-', '')}/"
INSTRUMENT = Instrument(
    "us:ZZAR", "us", "ZZAR", "NASDAQ", "Zenith Arc Robotics Inc.", None, "USD", CIK, True
)


def make_ref(**changes):
    values = dict(
        event_id=f"us:{ACCESSION}",
        instrument_id="us:ZZAR",
        cik=CIK,
        accession=ACCESSION,
        form_type="8-K",
        published_at=NOW,
        filing_date=NOW.date(),
        items="2.02,9.01",
        primary_document="main.htm",
        primary_doc_description="Synthetic disclosure",
    )
    return FilingRef(**(values | changes))


class FakeClient:
    def __init__(self):
        self.refs = [make_ref()]
        self.rows = [IndexRow(2, "Press", "ex99.htm", "EX-99.1", BASE + "ex99.htm")]
        self.files = {BASE + "main.htm": "", BASE + "ex99.htm": ""}
        self.calls = []
        self.index_calls = []
        self.list_error = None
        self.index_error = None

    def list_filings(self, instrument, since, until, fetched_at):
        if self.list_error:
            raise self.list_error
        return self.refs

    def fetch_index(self, ref):
        self.index_calls.append(ref.event_id)
        if self.index_error:
            raise self.index_error
        return self.rows

    def fetch_file(self, url):
        self.calls.append(url)
        result = self.files[url]
        if isinstance(result, Exception):
            raise result
        return result


@pytest.fixture
def db(tmp_path):
    database = Database(tmp_path / "test.duckdb")
    database.open()
    database.migrate()
    yield database
    database.close()


@pytest.fixture
def stack(db):
    client = FakeClient()
    repo = SecFilingsRepository(db)
    return client, repo, SecFilingsService(client, repo, lambda: NOW)
