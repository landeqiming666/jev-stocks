import json
from datetime import UTC, datetime

import pytest

from sentinel.errors import SourceError
from sentinel.markets.sec.submissions import parse_submissions

from .conftest import CIK, FIXTURES, NOW, SINCE


def payload():
    return json.loads((FIXTURES / "submissions_0001234567.synthetic.json").read_text())


def parse(data, **changes):
    return parse_submissions(
        data,
        **(
            dict(instrument_id="us:ZZAR", cik=CIK, since=SINCE, until=NOW, fetched_at=NOW) | changes
        ),
    )


def test_parse_submissions_filters_forms_and_window():
    result = parse(payload())
    assert len(result) == 6
    assert {ref.form_type for ref in result} == {"8-K", "8-K/A", "6-K"}
    assert all(SINCE < ref.published_at <= NOW for ref in result)
    empty = payload()
    empty["filings"]["recent"] = {key: [] for key in empty["filings"]["recent"]}
    assert parse(empty) == []


def test_parse_submissions_parses_acceptance_utc():
    data = payload()
    data["filings"]["recent"]["acceptanceDateTime"][0] = "2026-07-30T20:30:28.000Z"
    assert parse(data)[-1].published_at == datetime(2026, 7, 30, 20, 30, 28, tzinfo=UTC)


def test_parse_submissions_clamps_and_rejects_schema():
    data = payload()
    data["filings"]["recent"]["acceptanceDateTime"][0] = "2027-01-01T00:00:00Z"
    assert parse(data)[-1].published_at == NOW
    del data["filings"]["recent"]["form"]
    with pytest.raises(SourceError) as caught:
        parse(data)
    assert caught.value.reason == "SEC_SCHEMA"


@pytest.mark.parametrize("field", list(payload()["filings"]["recent"]))
@pytest.mark.parametrize("mutation", ["missing", "short", "not_array"])
def test_all_sixteen_arrays_required_and_aligned(field, mutation):
    data = payload()
    recent = data["filings"]["recent"]
    if mutation == "missing":
        del recent[field]
    elif mutation == "short":
        recent[field].pop()
    else:
        recent[field] = "not an array"
    with pytest.raises(SourceError) as error:
        parse(data)
    assert error.value.code == "SOURCE_UNAVAILABLE" and error.value.reason == "SEC_SCHEMA"


@pytest.mark.parametrize(
    "field,value",
    [
        ("acceptanceDateTime", "2026-07-30"),
        ("acceptanceDateTime", "2026-07-30T20:30:28"),
        ("acceptanceDateTime", "bad"),
        ("acceptanceDateTime", None),
        ("accessionNumber", "../000001"),
        ("accessionNumber", "0001234567-26-000001\n"),
        ("primaryDocument", "../main.htm"),
        ("primaryDocument", "https://evil.example/a.htm"),
        ("primaryDocument", ""),
        ("filingDate", "not a date"),
        ("items", []),
        ("form", None),
    ],
)
def test_bad_supported_row_fails_whole_payload(field, value):
    data = payload()
    data["filings"]["recent"][field][5] = value
    with pytest.raises(SourceError):
        parse(data)


def test_window_excludes_since_includes_until_and_converts_offset():
    data = payload()
    data["filings"]["recent"]["acceptanceDateTime"][5] = "2026-07-20T08:00:00+08:00"
    data["filings"]["recent"]["acceptanceDateTime"][6] = "2026-07-30T23:00:00Z"
    result = parse(data)
    assert all(ref.accession != "0001234567-26-000006" for ref in result)
    assert result[-1].published_at == NOW
    assert result[-1].accession == "0001234567-26-000007"
    assert all(ref.published_at.tzinfo == UTC for ref in result)
    assert parse(data, until=SINCE) == []


def test_duplicate_accession_metadata_conflict():
    data = payload()
    data["filings"]["recent"]["accessionNumber"][6] = data["filings"]["recent"]["accessionNumber"][
        5
    ]
    with pytest.raises(SourceError) as error:
        parse(data)
    assert error.value.reason == "SEC_SCHEMA"
