from contextlib import contextmanager
from dataclasses import replace

import pytest

from sentinel.errors import SourceError, UserError
from sentinel.markets.sec import IndexRow

from .conftest import ACCESSION, BASE, INSTRUMENT, NOW, SINCE, make_ref


def scan(stack):
    return stack[2].fetch_for_instrument(INSTRUMENT, since=SINCE, until=NOW)


def test_service_writes_title_only_when_all_empty(stack, db):
    result = scan(stack)
    assert result[0].content_status == "title_only"
    with db.read() as reader:
        reader.execute("SELECT text_status FROM event_file ORDER BY seq")
        assert reader.fetchall() == [("empty",), ("empty",)]


def test_service_skips_existing_full_text(stack):
    client, repo, _ = stack
    client.files[BASE + "main.htm"] = "<p>Saved text</p>"
    first = scan(stack)
    client.calls.clear()
    assert scan(stack) == first
    assert client.calls == []


def test_service_maps_rate_limit_and_decode(stack):
    client, _, _ = stack
    client.list_error = SourceError("RATE_LIMITED", params={"retryAfterSec": 2})
    with pytest.raises(SourceError) as caught:
        scan(stack)
    assert caught.value is client.list_error
    client.list_error = SourceError("SOURCE_UNAVAILABLE", reason="DECODE_FAILED")
    with pytest.raises(SourceError) as caught:
        scan(stack)
    assert caught.value.reason == "DECODE_FAILED"


def test_title_only_reused_without_requests(stack):
    client, _, _ = stack
    first = scan(stack)
    client.calls.clear()
    assert scan(stack) == first
    assert client.calls == []


def test_partial_download_failure_keeps_text_and_visible_failed_file_cr(stack, caplog):
    client, repo, _ = stack
    client.files[BASE + "main.htm"] = "<p>Saved cover</p>"
    client.files[BASE + "ex99.htm"] = SourceError("SOURCE_UNAVAILABLE", reason="SEC_FORBIDDEN")
    first = scan(stack)[0]
    assert first.content_status == "full_text"
    assert [(file.text_status, file.text) for file in first.files] == [
        ("extracted", "Saved cover"),
        ("failed", None),
    ]
    assert first.warnings == ("FILE_FAILED",)
    assert repo.get(first.event).files[1].text_status == "failed"
    client.files[BASE + "ex99.htm"] = "<p>Would recover with a future approved retry</p>"
    client.calls.clear()
    second = scan(stack)[0]
    assert second == first and client.calls == []
    assert "sec.cached_file_failed" in caplog.text


def test_fetch_failed_retries_and_then_reuses_full_text(stack):
    client, repo, _ = stack
    client.files[BASE + "main.htm"] = SourceError("SOURCE_UNAVAILABLE", reason="DECODE_FAILED")
    first = scan(stack)[0]
    assert first.content_status == "fetch_failed"
    assert first.files[0].text is None and first.files[0].char_count is None
    client.files[BASE + "main.htm"] = "<p>Recovered 😀</p>"
    client.calls.clear()
    second = scan(stack)[0]
    assert second.content_status == "full_text" and len(client.calls) == 2
    assert repo.get(first.event).files[0].text == "Recovered 😀"
    client.calls.clear()
    assert scan(stack) == [second] and client.calls == []


def test_index_network_failure_with_empty_primary_is_not_success(stack):
    client, _, _ = stack
    client.index_error = SourceError("SOURCE_UNAVAILABLE", reason="SEC_FORBIDDEN")
    first = scan(stack)[0]
    assert first.content_status == "fetch_failed" and first.warnings == ("INDEX_FAILED",)
    client.index_error = None
    client.files[BASE + "ex99.htm"] = "<p>Recovered exhibit</p>"
    assert scan(stack)[0].content_status == "full_text"


def test_index_structure_fallback_and_skipped_pdf(stack):
    client, _, _ = stack
    client.rows = []
    first = scan(stack)[0]
    assert first.content_status == "title_only" and first.warnings == ("PRIMARY_ONLY",)
    assert client.calls == [BASE + "main.htm"]


def test_six_k_title_prefers_ex991_then_main(stack):
    client, _, _ = stack
    client.refs = [make_ref(form_type="6-K", items=None)]
    client.files[BASE + "main.htm"] = "<p>Cover</p>"
    client.files[BASE + "ex99.htm"] = "<h1>Press heading</h1><p>Body</p>"
    assert scan(stack)[0].title == "6-K: Press heading"


def test_skipped_files_persist_without_http(stack, db):
    client, _, _ = stack
    client.rows.append(IndexRow(3, "PDF", "press.pdf", "EX-99.2", BASE + "press.pdf"))
    client.rows.append(IndexRow(4, "Data", "data.xml", "EX-101.INS", BASE + "data.xml"))
    files = scan(stack)[0].files
    assert [file.text_status for file in files] == ["empty", "empty", "skipped", "skipped"]
    assert len(client.calls) == 2
    with db.read() as reader:
        reader.execute("SELECT count(*) FROM event_file")
        assert reader.fetchone() == (4,)


def test_configuration_clear_mid_download_propagates_without_empty_event(stack, db, monkeypatch):
    client, _, _ = stack
    monkeypatch.setattr(
        client,
        "fetch_file",
        lambda url: (_ for _ in ()).throw(
            UserError("CONFIG_REQUIRED", params={"missing": ["secEmail"]})
        ),
    )
    with pytest.raises(UserError):
        scan(stack)
    with db.read() as reader:
        reader.execute("SELECT count(*) FROM event_doc")
        assert reader.fetchone() == (0,)


def test_network_never_inside_transaction_events_commit_independently(stack, db, monkeypatch):
    client, repo, _ = stack
    second_accession = "0001234567-26-000002"
    second_base = BASE.replace(ACCESSION.replace("-", ""), second_accession.replace("-", ""))
    second_ref = make_ref(
        event_id="us:" + second_accession,
        accession=second_accession,
        published_at=NOW.replace(hour=22),
    )
    client.refs = [make_ref(), second_ref]
    client.rows = []
    client.files[second_base + "main.htm"] = "<p>Earlier event</p>"
    active = [False]
    transactions = []
    original_write = db.write
    original_fetch = client.fetch_file

    @contextmanager
    def tracked_write():
        assert not active[0]
        active[0] = True
        try:
            with original_write() as tx:
                yield tx
            transactions.append("commit")
        finally:
            active[0] = False

    def checked_fetch(url):
        assert not active[0]
        return original_fetch(url)

    monkeypatch.setattr(db, "write", tracked_write)
    monkeypatch.setattr(client, "fetch_file", checked_fetch)
    events = scan(stack)
    assert [item.event.accession for item in events] == [second_accession, ACCESSION]
    assert transactions == ["commit", "commit"]
    assert all(repo.get(item.event) is not None for item in events)


def test_later_event_persistence_failure_does_not_rollback_earlier(stack, monkeypatch):
    client, repo, _ = stack
    second_ref = replace(
        make_ref(), event_id="us:0001234567-26-000002", accession="0001234567-26-000002"
    )
    client.refs = [make_ref(), second_ref]
    client.rows = []
    second_base = BASE.replace(ACCESSION.replace("-", ""), second_ref.accession.replace("-", ""))
    client.files[second_base + "main.htm"] = ""
    original = repo.upsert

    def failing(event):
        if event.event == second_ref:
            raise OSError("synthetic save failure")
        original(event)

    monkeypatch.setattr(repo, "upsert", failing)
    with pytest.raises(OSError):
        scan(stack)
    assert repo.get(make_ref()) is not None and repo.get(second_ref) is None
