from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path

import duckdb
import pytest

from sentinel.errors import UserError
from sentinel.markets.sec import EventFileDraft, FetchedEvent, SecFilingsRepository

from .conftest import BASE, NOW, make_ref


def draft(text="Initial", seq=0, name="main.htm"):
    return EventFileDraft(
        seq, name, "8-K" if seq == 0 else "EX-99.1", BASE + name, "extracted", text, len(text)
    )


def event(*files, **changes):
    return FetchedEvent(
        make_ref(), list(files) or [draft()], "full_text", fetched_at=NOW, **changes
    )


def snapshot(db):
    with db.read() as reader:
        reader.execute("SELECT * FROM event_doc ORDER BY event_id")
        docs = reader.fetchall()
        reader.execute("SELECT * FROM event_file ORDER BY event_id, seq")
        return docs, reader.fetchall()


def test_migration_matches_authoritative_bytes_and_is_idempotent(db):
    root = Path(__file__).resolve().parents[5]
    text = (root / "docs/04-数据模型.md").read_text()
    section = text.split("### 3.4 ", 1)[1].split("### 3.5 ", 1)[0]
    expected = section.split("```sql\n", 1)[1].split("```", 1)[0].encode()
    assert (root / "core/sentinel/storage/migrations/004_filings.sql").read_bytes() == expected
    assert db.schema_version == 4
    db.migrate()
    assert db.schema_version == 4


@pytest.mark.parametrize("has_existing", [False, True])
@pytest.mark.parametrize("failure_kind", ["io", "sql"])
def test_event_and_all_files_rollback_after_second_file_write(
    db, monkeypatch, has_existing, failure_kind
):
    repo = SecFilingsRepository(db)
    if has_existing:
        repo.upsert(event(draft(), draft("Press", 2, "ex99.htm")))
    before = snapshot(db)
    original = db.write

    class FailingExecutor:
        def __init__(self, tx):
            self.tx = tx
            self.files = 0

        def execute(self, sql, params=None):
            result = self.tx.execute(sql, params)
            if "INSERT INTO event_file" in sql:
                self.files += 1
                if self.files == 2:
                    if failure_kind == "sql":
                        self.tx.execute(
                            "INSERT INTO event_file VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                            [
                                make_ref().event_id,
                                999,
                                "bad.htm",
                                None,
                                BASE + "bad.htm",
                                "failed",
                                None,
                                None,
                            ],
                        )
                    raise OSError("synthetic write failure")
            return result

        def fetchone(self):
            return self.tx.fetchone()

    @contextmanager
    def fail_write():
        with original() as tx:
            yield FailingExecutor(tx)

    monkeypatch.setattr(db, "write", fail_write)
    with pytest.raises(OSError if failure_kind == "io" else duckdb.ConstraintException):
        repo.upsert(event(draft("Replacement"), draft("Replacement press", 2, "ex99.htm")))
    assert snapshot(db) == before


def seed_reference(db):
    with db.write() as tx:
        tx.execute(
            "INSERT INTO event_passage VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            ["passage", make_ref().event_id, 0, 0, "Initial", 0, 7, "hash"],
        )
        tx.execute("CREATE TABLE decision (decision_id VARCHAR PRIMARY KEY, passage_id VARCHAR)")
        tx.execute("INSERT INTO decision VALUES (?, ?)", ["decision", "passage"])


def test_existing_passages_decisions_survive_retry_and_rejection(db):
    repo = SecFilingsRepository(db)
    repo.upsert(event())
    seed_reference(db)
    repo.upsert(event())
    before = snapshot(db)
    with pytest.raises(UserError) as error:
        repo.upsert(event(draft("Changed body")))
    assert error.value.code == "CONFLICT" and error.value.reason == "SEC_PASSAGE_REFERENCE"
    assert snapshot(db) == before
    with db.read() as reader:
        reader.execute("SELECT text FROM event_passage")
        assert reader.fetchall() == [("Initial",)]
        reader.execute("SELECT * FROM decision")
        assert reader.fetchall() == [("decision", "passage")]


def test_file_identity_conflict_rolls_back_doc_and_other_files(db):
    repo = SecFilingsRepository(db)
    repo.upsert(event(draft(), draft("Exhibit", 2, "ex99.htm")))
    before = snapshot(db)
    with pytest.raises(UserError) as error:
        repo.upsert(event(draft("Changed main"), draft("Other", 2, "other.htm")))
    assert error.value.reason == "SEC_FILE_IDENTITY"
    assert snapshot(db) == before


def test_omitted_files_are_retained_without_physical_delete(db):
    repo = SecFilingsRepository(db)
    repo.upsert(event(draft(), draft("Exhibit", 2, "ex99.htm")))
    repo.upsert(event())
    stored = repo.get(make_ref())
    assert [file.seq for file in stored.files] == [0, 2]


def test_sql_bindings_and_codepoint_count_with_hostile_text(db, caplog):
    repo = SecFilingsRepository(db)
    text = "'; DROP TABLE event_doc; -- 😀机密\n"
    ref = make_ref(items=None, primary_doc_description=text)
    repo.upsert(FetchedEvent(ref, [draft(text)], "full_text", fetched_at=NOW))
    stored = repo.get(ref)
    assert stored.files[0].text == text and stored.files[0].char_count == len(text)
    assert "机密" not in caplog.text and "DROP TABLE" not in caplog.text
    assert db.schema_version == 4


def test_cached_ref_uses_saved_primary_url_not_new_metadata(db):
    repo = SecFilingsRepository(db)
    repo.upsert(event())
    result = repo.get(make_ref(primary_document="new.htm", cik="0007654321"))
    assert result.event.primary_document == "main.htm"
    assert result.event.cik == "0001234567"
    with pytest.raises(UserError) as error:
        repo.get(make_ref(instrument_id="us:ZZFD"))
    assert error.value.reason == "SEC_EVENT_IDENTITY"


def test_title_passage_cannot_be_silently_changed(db):
    repo = SecFilingsRepository(db)
    first = replace(event(), files=[], content_status="title_only")
    repo.upsert(first)
    with db.write() as tx:
        tx.execute(
            "INSERT INTO event_passage VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            ["title", first.event.event_id, -1, 0, "Title", 0, 5, "hash"],
        )
    before = snapshot(db)
    with pytest.raises(UserError) as error:
        repo.upsert(replace(first, event=make_ref(items="8.01")))
    assert error.value.reason == "SEC_PASSAGE_REFERENCE"
    assert snapshot(db) == before
