from dataclasses import replace

import pytest

from sentinel.errors import SourceError
from sentinel.markets.sec import IndexRow
from sentinel.markets.sec.index import parse_index, select_files

from .conftest import ACCESSION, BASE, CIK, FIXTURES


def test_parse_index_and_cap_ex99():
    rows = parse_index(
        (FIXTURES / "filing_index_8k_ex99.synthetic.html").read_text(),
        base_url=BASE + ACCESSION + "-index.htm",
    )
    assert any(row.doc_type == "EX-99.1" for row in rows)
    selected, skipped = select_files(
        rows, cik=CIK, accession=ACCESSION, primary_document="main.htm"
    )
    assert selected[0].seq == 0
    assert sum(row.doc_type.startswith("EX-99") for row in selected) == 3
    assert len([row for row in skipped if row.file_name.endswith(".htm")]) == 2


def test_select_files_skips_and_empty_index():
    assert parse_index("<p>No index</p>", base_url=BASE) == []
    rows = parse_index(
        (FIXTURES / "filing_index_8k_ex99.synthetic.html").read_text(), base_url=BASE
    )
    selected, skipped = select_files(
        rows[-2:], cik=CIK, accession=ACCESSION, primary_document="main.htm"
    )
    assert len(selected) == 1
    assert {row.file_name for row in skipped} == {"data.xml", "release.pdf"}


def table(href, seq="2"):
    return (
        "<table><tr><th>Seq</th><th>Description</th><th>Document</th><th>Type</th></tr>"
        f'<tr><td>{seq}</td><td>Release</td><td><a href="{href}">release.htm</a></td>'
        "<td>EX-99.1</td></tr></table>"
    )


@pytest.mark.parametrize(
    "href",
    [
        "https://evil.example/release.htm",
        "//evil.example/a.htm",
        "javascript:alert(1)",
        "../release.htm",
        "%2e%2e/release.htm",
        "%252e%252e/a.htm",
        "/Archives/edgar/data/9/000000000926000001/release.htm",
        "release.htm?key=private",
        "release.htm#private",
        "release.htm\n",
        "\\evil.example\\a.htm",
        "/ix?doc=https%3A%2F%2Fevil.example%2Fa.htm",
        "/ix?doc=%2FArchives%2Fedgar%2Fdata%2F9%2Fa.htm",
        "/ix?doc=main.htm",
        "/ix?doc=%2FArchives%2Fedgar%2Fdata%2F1234567%2F..%2Fmain.htm",
        "/ix?doc=/Archives/edgar/data/1234567/a&doc=/private",
        "/ix?doc=/private&secret=private",
        "/ixviewer/doc/action?doc=//evil.example/a.htm",
    ],
)
def test_malicious_links_never_selected_and_do_not_log_payload(href, caplog):
    assert parse_index(table(href), base_url=BASE + ACCESSION + "-index.htm") == []
    assert "sec.index_link_rejected" in caplog.text
    assert "evil.example" not in caplog.text and "private" not in caplog.text


@pytest.mark.parametrize("viewer", ["/ix", "/ixviewer/ix.html", "/ixviewer/doc/action"])
def test_safe_ixviewer_unwraps_only_same_archive(viewer):
    path = BASE.split("https://www.sec.gov")[1] + "release.htm"
    rows = parse_index(table(viewer + "?doc=" + path), base_url=BASE)
    assert rows[0].url == BASE + "release.htm"


@pytest.mark.parametrize("seq", ["bad", "-1", "1000", "٢", ""])
def test_bad_sequence_logs_without_losing_other_rows(seq, caplog):
    assert parse_index(table("release.htm", seq), base_url=BASE) == []
    assert "sec.index_row_invalid" in caplog.text


def test_duplicate_sequence_or_filename_is_explicit_conflict():
    row = IndexRow(2, "Press", "release.htm", "EX-99.1", BASE + "release.htm")
    for other in (
        row,
        replace(row, file_name="other.htm", url=BASE + "other.htm"),
        replace(row, seq=3),
        replace(row, seq=0),
    ):
        with pytest.raises(SourceError) as error:
            select_files([row, other], cik=CIK, accession=ACCESSION, primary_document="main.htm")
        assert error.value.reason == "SEC_INDEX_CONFLICT"


def test_empty_link_is_rejected_without_downloading_index_as_document():
    assert parse_index(table(""), base_url=BASE + ACCESSION + "-index.htm") == []


def test_order_main_at_zero_and_nonhtml_exhibits_do_not_consume_cap():
    rows = [
        IndexRow(9, "Cover", "main.htm", "8-K", BASE + "main.htm"),
        IndexRow(1, "PDF", "press.pdf", "EX-99.1", BASE + "press.pdf"),
    ]
    rows += [
        IndexRow(i + 2, "Press", f"press{i}.htm", f"EX-99.{i + 2}", BASE + f"press{i}.htm")
        for i in range(4)
    ]
    selected, skipped = select_files(
        list(reversed(rows)), cik=CIK, accession=ACCESSION, primary_document="main.htm"
    )
    assert [row.seq for row in selected] == [0, 2, 3, 4]
    assert {row.seq for row in skipped} == {1, 5}
