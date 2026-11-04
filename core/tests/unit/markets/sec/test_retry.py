from dataclasses import replace

import pytest

from sentinel.errors import SourceError, UserError
from sentinel.markets.sec import EventFileDraft, FetchedEvent, IndexRow

from .conftest import BASE, NOW, make_ref
from .test_repository import seed_reference, snapshot
from .test_service import scan


def partial(stack, db, *, legacy=False, seq=2):
    client, repo, _ = stack
    main = EventFileDraft(0, "main.htm", "8-K", BASE + "main.htm", "extracted", "Initial", 7)
    failed = EventFileDraft(seq, "ex99.htm", "EX-99.1", BASE + "ex99.htm", "failed", None, None)
    client.rows[0] = replace(client.rows[0], seq=seq)
    repo.upsert(FetchedEvent(make_ref(), [main, failed], "fetch_failed", fetched_at=NOW))
    seed_reference(db)
    if legacy:
        with db.write() as tx:
            tx.execute(
                "UPDATE event_doc SET content_status = ? WHERE event_id = ?",
                ["full_text", make_ref().event_id],
            )
    client.files[BASE + "main.htm"] = AssertionError("referenced main must never be downloaded")
    client.files[BASE + "ex99.htm"] = "<p>Recovered exhibit</p>"
    return main


@pytest.mark.parametrize("legacy", [False, True])
def test_failed_to_recovered_preserves_referenced_main_and_decision(stack, db, legacy):
    main = partial(stack, db, legacy=legacy)
    client, repo, _ = stack
    result = scan(stack)[0]
    assert result.content_status == "full_text" and result.warnings == ()
    assert result.files[0] == main
    assert client.calls == [BASE + "ex99.htm"]
    assert client.index_calls == [make_ref().event_id]
    assert repo.get(make_ref()).files == result.files
    with db.read() as reader:
        reader.execute("SELECT text FROM event_passage")
        assert reader.fetchall() == [("Initial",)]
        reader.execute("SELECT decision_id, passage_id FROM decision")
        assert reader.fetchall() == [("decision", "passage")]
    client.calls.clear()
    client.index_calls.clear()
    assert scan(stack) == [result]
    assert client.calls == client.index_calls == []


@pytest.mark.parametrize("index_error", ["network", "identity"])
def test_index_failure_with_body_remains_failed_then_recovers(stack, index_error):
    client, repo, _ = stack
    client.files[BASE + "main.htm"] = "<p>Initial</p>"
    if index_error == "network":
        client.index_error = SourceError("SOURCE_UNAVAILABLE", reason="SEC_FORBIDDEN")
        warning = "INDEX_FAILED"
    else:
        client.rows.append(replace(client.rows[0], file_name="other.htm", url=BASE + "other.htm"))
        warning = "INDEX_CONFLICT"
    first = scan(stack)[0]
    assert first.content_status == "fetch_failed" and warning in first.warnings
    assert first.files[0].text == "Initial"
    assert repo.get(first.event).content_status == "fetch_failed"
    client.index_error = None
    client.rows = [IndexRow(2, "Press", "ex99.htm", "EX-99.1", BASE + "ex99.htm")]
    client.files[BASE + "ex99.htm"] = "<p>Recovered exhibit</p>"
    client.files[BASE + "main.htm"] = AssertionError("successful main must be reused")
    client.calls.clear()
    result = scan(stack)[0]
    assert result.content_status == "full_text" and result.files[0] == first.files[0]
    assert client.calls == [BASE + "ex99.htm"]


@pytest.mark.parametrize("failure", ["file", "index", "conflict"])
def test_retry_failure_preserves_body_and_keeps_failed_visible(stack, db, failure):
    main = partial(stack, db)
    client, repo, _ = stack
    if failure == "file":
        client.files[BASE + "ex99.htm"] = SourceError("RATE_LIMITED", params={"retryAfterSec": 2})
    elif failure == "index":
        client.index_error = SourceError("SOURCE_UNAVAILABLE", reason="DECODE_FAILED")
    else:
        client.rows.append(client.rows[0])
    result = scan(stack)[0]
    assert result.content_status == "fetch_failed"
    assert result.files[0] == main and result.files[1].text_status == "failed"
    assert "FILE_FAILED" in result.warnings
    assert repo.get(make_ref()).files == result.files
    assert BASE + "main.htm" not in client.calls


@pytest.mark.parametrize("disposition", ["missing", "skipped"])
def test_old_failed_exhibit_cannot_be_hidden_by_new_index(stack, db, disposition):
    partial(stack, db, seq=8 if disposition == "skipped" else 2)
    client, repo, _ = stack
    if disposition == "missing":
        client.rows = []
    else:
        client.rows = [
            IndexRow(seq, "Press", f"new{seq}.htm", f"EX-99.{seq}", BASE + f"new{seq}.htm")
            for seq in (1, 3, 4)
        ] + client.rows
        for seq in (1, 3, 4):
            client.files[BASE + f"new{seq}.htm"] = "<p>Additional exhibit</p>"
    result = scan(stack)[0]
    assert result.content_status == "fetch_failed" and "FILE_FAILED" in result.warnings
    retained = next(file for file in result.files if file.file_name == "ex99.htm")
    assert retained.text_status == "failed"
    assert repo.get(make_ref()).files == result.files
    assert client.calls == (
        [] if disposition == "missing" else [BASE + f"new{seq}.htm" for seq in (1, 3, 4)]
    )


@pytest.mark.parametrize("identity_change", ["name", "sequence", "type", "primary"])
def test_identity_change_rolls_back_whole_event(stack, db, identity_change):
    partial(stack, db)
    client, _, _ = stack
    before = snapshot(db)
    if identity_change == "name":
        client.rows[0] = replace(client.rows[0], file_name="other.htm", url=BASE + "other.htm")
        client.files[BASE + "other.htm"] = "<p>Other</p>"
    elif identity_change == "sequence":
        client.rows[0] = replace(client.rows[0], seq=3)
    elif identity_change == "type":
        client.rows[0] = replace(client.rows[0], doc_type="EX-99.2")
    else:
        client.refs[0] = make_ref(primary_document="other.htm")
        client.files[BASE + "other.htm"] = "<p>Other</p>"
    with pytest.raises(UserError) as error:
        scan(stack)
    assert error.value.code == "CONFLICT"
    assert client.calls == []
    assert snapshot(db) == before


def test_repository_cannot_mark_complete_while_retaining_omitted_failed_file(stack, db):
    main = partial(stack, db)
    _, repo, _ = stack
    repo.upsert(FetchedEvent(make_ref(), [main], "full_text", fetched_at=NOW))
    result = repo.get(make_ref())
    assert result.content_status == "fetch_failed"
    assert result.files[1].text_status == "failed"


def test_empty_file_is_reused_while_failed_main_recovers(stack):
    client, _, _ = stack
    client.files[BASE + "main.htm"] = SourceError("SOURCE_UNAVAILABLE", reason="DECODE_FAILED")
    first = scan(stack)[0]
    assert first.files[1].text_status == "empty"
    client.calls.clear()
    client.files[BASE + "main.htm"] = ""
    client.files[BASE + "ex99.htm"] = AssertionError("empty is already successfully extracted")
    result = scan(stack)[0]
    assert result.content_status == "title_only"
    assert client.calls == [BASE + "main.htm"]


@pytest.mark.parametrize("winner_text", ["First recovered body", ""])
def test_late_retry_cannot_overwrite_concurrently_recovered_success(
    stack, db, monkeypatch, winner_text
):
    main = partial(stack, db)
    client, repo, _ = stack
    winner = EventFileDraft(
        2,
        "ex99.htm",
        "EX-99.1",
        BASE + "ex99.htm",
        "extracted" if winner_text else "empty",
        winner_text,
        len(winner_text),
    )

    def another_recovery(url):
        assert url == BASE + "ex99.htm"
        repo.upsert(FetchedEvent(make_ref(), [main, winner], "full_text", fetched_at=NOW))
        return "<p>Later conflicting body</p>"

    monkeypatch.setattr(client, "fetch_file", another_recovery)
    with pytest.raises(UserError) as error:
        scan(stack)
    assert error.value.reason == "SEC_FILE_CONTENT"
    assert repo.get(make_ref()).files == [main, winner]
    with db.read() as reader:
        reader.execute("SELECT decision_id, passage_id FROM decision")
        assert reader.fetchall() == [("decision", "passage")]
