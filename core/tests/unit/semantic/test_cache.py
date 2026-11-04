from __future__ import annotations

import hashlib
from dataclasses import astuple, replace
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest

from sentinel.semantic.cache import (
    _row,
    decision_cache_key,
    find_decisions,
    insert_decision,
    norm_text,
    passage_content_hash,
    thesis_content_hash,
)
from sentinel.storage.db import Database
from sentinel.storage.migrations import DEFAULT_MIGRATIONS_DIR, discover_migrations


def key(**changes: object) -> str:
    values: dict[str, Any] = dict(
        engine="jev_direct",
        model_id="jev-1.14.0",
        question_set_version="qs1",
        thesis_hash="a" * 64,
        passage_hash="b" * 64,
        thesis_id="t1",
        thesis_version=1,
        passage_id="p1",
    )
    values.update(changes)
    return decision_cache_key(**values)


def test_decision_cache_key_changes_with_each_component() -> None:
    original = key()
    alternatives = [
        key(**{name: value})
        for name, value in (
            ("engine", "jevdb"),
            ("model_id", "jev-1.13.0"),
            ("question_set_version", "qs2"),
            ("thesis_hash", "c" * 64),
            ("passage_hash", "d" * 64),
            ("thesis_id", "t2"),
            ("thesis_version", 2),
            ("passage_id", "p2"),
        )
    ]
    assert len(set([original, *alternatives])) == 9
    assert all(
        len(k) == 64 and int(k, 16) >= 0 and k == k.lower() for k in [original, *alternatives]
    )
    expected = "|".join(["jev_direct", "jev-1.14.0", "qs1", "a" * 64, "b" * 64, "t1", "1", "p1"])
    assert original == hashlib.sha256(expected.encode()).hexdigest()


def test_norm_text_preserves_internal_whitespace() -> None:
    assert norm_text("  a  b\r\n") == "a  b"
    assert norm_text("e\u0301\r\nz\r x\t\t y") == "é\nz\n x\t\t y"
    assert passage_content_hash(" e\u0301\r\n") == passage_content_hash("é")
    assert thesis_content_hash(" a ", None) == thesis_content_hash("a", "")
    assert thesis_content_hash("a", "b") != thesis_content_hash("a\nb", None)


@pytest.mark.parametrize("text", ["\ud800", "\udfff", "ok\ud800bad"])
def test_invalid_unicode_hash_rejected(text: str) -> None:
    with pytest.raises(ValueError):
        passage_content_hash(text)


@pytest.mark.parametrize(
    "changes",
    [
        {"thesis_id": "a|1"},
        {"passage_id": "p\n"},
        {"thesis_version": True},
        {"thesis_version": 0},
    ],
)
def test_cache_key_rejects_ambiguous_components(changes: dict[str, object]) -> None:
    with pytest.raises(ValueError):
        key(**changes)


def test_migration_matches_authoritative_ddl_and_all_migrations(tmp_path: Path) -> None:
    doc = Path(__file__).parents[4] / "docs" / "04-数据模型.md"
    section = doc.read_text().split("### 3.6 `006_decision.sql`")[1]
    ddl = section.split("```sql\n", 1)[1].split("```", 1)[0]
    migration = DEFAULT_MIGRATIONS_DIR / "006_decision.sql"
    assert migration.read_text() == ddl
    db = Database(tmp_path / "db.duckdb")
    db.open()
    try:
        migrations = discover_migrations(DEFAULT_MIGRATIONS_DIR)
        report = db.migrate()
        assert report.applied == tuple(m.version for m in migrations)
        assert db.migrate().applied == ()
        with db.read() as reader:
            reader.execute("SELECT checksum FROM schema_version WHERE version=6")
            assert reader.fetchone() == (hashlib.sha256(ddl.encode()).hexdigest(),)
            reader.execute("SELECT index_name FROM duckdb_indexes() WHERE table_name='decision'")
            assert {r[0] for r in reader.fetchall()} == {
                "idx_decision_thesis",
                "idx_decision_event",
            }
    finally:
        db.close()


def test_insert_conflict_reads_own_tx_and_preserves_identity(tmp_path: Path) -> None:
    from tests.unit.semantic.test_pipeline import make_row

    db = Database(tmp_path / "db.duckdb")
    db.open()
    db.migrate()
    try:
        row = make_row()
        with db.write() as tx:
            saved, inserted = insert_decision(tx, row)
            assert inserted and saved == row
            collision = replace(row, decision_id="different-id", input_tokens=999)
            saved, inserted = insert_decision(tx, collision)
            assert not inserted and saved == row
            assert find_decisions(tx, [row.cache_key]) == {row.cache_key: row}
        with db.read() as reader:
            assert find_decisions(reader, [row.cache_key]) == {row.cache_key: row}
    finally:
        db.close()


@pytest.mark.parametrize(
    "created_at",
    [datetime(2026, 11, 3, 4), datetime(2026, 11, 3, 12, tzinfo=timezone(timedelta(hours=8)))],
)
def test_decision_row_restores_utc_timestamp(created_at: datetime) -> None:
    from tests.unit.semantic.test_pipeline import make_row

    row = _row(astuple(make_row(created_at=created_at))[:-1])
    assert row.created_at == datetime(2026, 11, 3, 4, tzinfo=UTC)
    assert row.created_at.tzinfo is UTC
