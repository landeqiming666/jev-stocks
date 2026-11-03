from __future__ import annotations

import base64
import hashlib
import json
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path

import duckdb
import pytest
from jsonschema import Draft202012Validator, FormatChecker
from pydantic import ValidationError
from referencing import Registry, Resource
from referencing.jsonschema import DRAFT202012

from sentinel import clock, messages
from sentinel.errors import InternalError, UserError
from sentinel.ids import new_id
from sentinel.messages import inbox as inbox_messages
from sentinel.rpc import CancelToken, Dispatcher
from sentinel.rpc.dispatcher import RequestContext
from sentinel.scan.pending import (
    InboxService,
    StatusSnapshot,
    register_handlers,
)
from sentinel.storage import Database, SqlExecutor
from sentinel.storage.migrations import DEFAULT_MIGRATIONS_DIR, discover_migrations

ROOT = Path(__file__).resolve().parents[4]
NOW = datetime(2026, 11, 2, 0, 35, tzinfo=UTC)
TEXT = "Zenith Arc Robotics: 雪😀。 Sales slowed."
METHODS = ("inbox.list", "decision.get", "decision.act", "decision.reopen")
TYPES = json.loads((ROOT / "contracts/types.schema.json").read_text())
REGISTRY = Registry().with_resource(
    "types.schema.json", Resource.from_contents(TYPES, default_specification=DRAFT202012)
)


def uid(index: int) -> str:
    return new_id(timestamp_ms=1, entropy=index.to_bytes(10, "big"))


def ddl(section: str) -> bytes:
    document = (ROOT / "docs/04-数据模型.md").read_bytes()
    return (
        document.split(f"### {section} `".encode(), 1)[1]
        .split(b"```sql\n", 1)[1]
        .split(b"```", 1)[0]
    )


def query(db: Database, sql: str, params: list | None = None) -> list[tuple]:
    with db.read() as reader:
        reader.execute(sql, params)
        return reader.fetchall()


SECTION_MIGRATIONS = (
    ("3.6", "decision", 6, "decision"),
    ("3.8", "scan_run", 8, "scan"),
    ("3.10", "paper_account", 10, "paper"),
)


def complete_fixture_sections(database: Database, migrations_dir: Path | None = None) -> None:
    delivered = {
        migration.version
        for migration in discover_migrations(migrations_dir or DEFAULT_MIGRATIONS_DIR)
    }
    with database.write() as tx:
        tx.execute(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema=current_schema() AND table_type='BASE TABLE'"
        )
        tables = {row[0] for row in tx.fetchall()}
        for section, table, version, name in SECTION_MIGRATIONS:
            tx.execute("SELECT name, checksum FROM schema_version WHERE version=?", [version])
            recorded = tx.fetchone()
            authoritative = ddl(section)
            if version in delivered:
                assert table in tables, f"{table}: applied migration is missing its table"
                assert recorded == (name, hashlib.sha256(authoritative).hexdigest()), (
                    f"{table}: existing section must have its authoritative migration checksum"
                )
            else:
                assert recorded is None and table not in tables, (
                    f"{table}: existing section must have its authoritative migration checksum"
                )
                # 仅尚未交付的 section 在临时数据库显式补造；不伪造迁移记录。
                tx.execute(authoritative.decode())


@pytest.fixture(autouse=True)
def isolated(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("SENTINEL_CLOCK", clock.to_iso(NOW))
    monkeypatch.setenv("SENTINEL_OFFLINE", "1")
    monkeypatch.setenv("SENTINEL_DATA_DIR", str(tmp_path))
    # 公共 messages 注册属于主 agent；此处明确装配本包的真实模板。
    monkeypatch.setattr(messages, "MESSAGES", messages.MESSAGES | inbox_messages.MESSAGES)


@pytest.fixture
def db(tmp_path: Path, request: pytest.FixtureRequest) -> Iterator[Database]:
    database = Database(tmp_path / "pending.duckdb")
    database.open()
    try:
        migrations_dir = None
        if hasattr(request, "param"):
            migrations_dir = tmp_path / "pending-migrations"
            migrations_dir.mkdir()
            for migration in discover_migrations(DEFAULT_MIGRATIONS_DIR):
                (migrations_dir / migration.sql_path.name).write_bytes(
                    migration.sql_path.read_bytes()
                )
            for section, _, version, name in SECTION_MIGRATIONS:
                if section in request.param:
                    # 未来 008/010 在此只作为权威字节迁移 fixture，走真实执行器。
                    target = migrations_dir / f"{version:03}_{name}.sql"
                    if not target.exists():
                        target.write_bytes(ddl(section))
                    else:
                        assert target.read_bytes() == ddl(section)
        database.migrate(migrations_dir)
        complete_fixture_sections(database, migrations_dir)
        with database.write() as tx:
            tx.execute(
                "INSERT INTO instrument VALUES ('us:ZZAR', 'us', 'ZZAR', 'NASDAQ', "
                "'Zenith Arc Robotics Inc.', NULL, 'USD', NULL, TRUE, 'demo', ?)",
                [NOW],
            )
            tx.execute(
                "INSERT INTO holding VALUES (?, 'us:ZZAR', 0, NULL, NULL, ?, ?, NULL)",
                [uid(1), NOW, NOW],
            )
            tx.execute(
                "INSERT INTO thesis VALUES (?, 'us:ZZAR', 'active', 1, ?, ?, NULL)",
                [uid(2), NOW, NOW],
            )
            tx.execute(
                "INSERT INTO thesis_version VALUES (?, 1, 'Sales will grow', NULL, 'v1', ?)",
                [uid(2), NOW],
            )
        yield database
    finally:
        database.close()


def status(reader: SqlExecutor, as_of: datetime) -> StatusSnapshot:
    assert as_of == clock.now()
    reader.execute("SELECT COUNT(*) FROM holding")
    return StatusSnapshot.model_validate(
        {
            "source": {
                "name": "SEC EDGAR",
                "state": "degraded",
                "lastSuccessAt": None,
                "message": "Synthetic source state",
            },
            "engine": {"active": None, "modelId": "jev-1.14.0", "state": "unconfigured"},
            "offline": True,
        }
    )


@pytest.fixture
def service(db: Database) -> InboxService:
    return InboxService(db, status_provider=status)


def seed(
    db: Database,
    index: int = 10,
    *,
    event: int = 1,
    seq: int = 0,
    relation: str = "weaken",
    headline: float = 0.74,
    kind: str | None = "sentence",
    start: int | None = 0,
    end: int | None = 20,
    text: str = TEXT,
    file_seq: int = 0,
    thesis: str | None = None,
    published: datetime = NOW,
) -> str:
    decision_id, event_id = uid(index), f"us:0009990001-26-{event:06d}"
    passage_id = hashlib.sha256(f"{event_id}|{file_seq}|{seq}".encode()).hexdigest()[:32]
    with db.write() as tx:
        tx.execute(
            "INSERT INTO event_doc VALUES (?, 'us:ZZAR', 'us', '8-K', 'Synthetic disclosure', "
            "?, ?, 'https://example.com/filing', NULL, ?, ?, 'demo') ON CONFLICT DO NOTHING",
            [
                event_id,
                published,
                published.date(),
                "title_only" if file_seq == -1 else "full_text",
                NOW,
            ],
        )
        if file_seq >= 0:
            tx.execute(
                "INSERT INTO event_file VALUES (?, ?, 'synthetic.htm', 'EX-99.1', "
                "'https://example.com/file', 'extracted', ?, ?) ON CONFLICT DO NOTHING",
                [event_id, file_seq, text, len(text)],
            )
        tx.execute(
            "INSERT INTO event_passage VALUES (?, ?, ?, ?, ?, 0, ?, ?) ON CONFLICT DO NOTHING",
            [passage_id, event_id, file_seq, seq, text, len(text), passage_id],
        )
        tx.execute(
            "INSERT INTO decision VALUES (?, ?, 1, ?, ?, 'us:ZZAR', ?, .95, ?, .41, "
            "NULL, .06, ?, ?, ?, ?, 'jev_direct', 'jev-1.14.0', 'qs-test', ?, 10, FALSE, "
            "1, ?, ?)",
            [
                decision_id,
                thesis or uid(2),
                passage_id,
                event_id,
                relation,
                headline,
                headline,
                kind,
                start,
                end,
                decision_id,
                "title_only" if file_seq == -1 else "full_text",
                NOW,
            ],
        )
    return decision_id


def action(db: Database, decision_id: str, index: int, at: datetime, value: str = "ignore") -> None:
    with db.write() as tx:
        tx.execute(
            "INSERT INTO thesis_action VALUES (?, ?, ?, NULL, ?)",
            [uid(index), decision_id, value, at],
        )


def wire(value) -> dict:
    return value.model_dump(mode="json", by_alias=True)


def validate_type(name: str, result: dict) -> None:
    Draft202012Validator(
        {"$ref": "types.schema.json#/$defs/" + name},
        registry=REGISTRY,
        format_checker=FormatChecker(),
    ).validate(result)


def test_action_ddl_is_authoritative_and_migration_is_idempotent(db: Database) -> None:
    source = ROOT / "core/sentinel/storage/migrations/007_action.sql"
    assert source.read_bytes() == ddl("3.7")
    assert db.migrate().applied == ()
    assert query(db, "SELECT checksum FROM schema_version WHERE version=7") == [
        (hashlib.sha256(source.read_bytes()).hexdigest(),)
    ]


def test_representative_prefers_overturn_over_weaken(db: Database, service: InboxService) -> None:
    seed(db, relation="weaken", headline=0.99)
    selected = seed(db, 11, seq=1, relation="overturn", headline=0.8)
    assert [item.decision_id for item in service.list_inbox().items] == [selected]


def test_representative_uses_headline_then_passage_seq(db: Database, service: InboxService) -> None:
    seed(db, headline=0.8)
    selected = seed(db, 11, seq=1, headline=0.9)
    seed(db, 12, seq=2, headline=0.9)
    assert service.list_inbox().items[0].decision_id == selected


def test_tie_uses_smallest_decision_id(db: Database, service: InboxService) -> None:
    seed(db, 12)
    selected = seed(db, 11)
    assert service.list_inbox().items[0].decision_id == selected


def test_uncertain_is_separate_from_items(db: Database, service: InboxService) -> None:
    seed(db)
    seed(db, 11, event=2, relation="uncertain", headline=0.55)
    page = service.list_inbox()
    assert len(page.items) == len(page.uncertain) == 1
    assert wire(page)["summary"] == {
        "pendingCount": 2,
        "overturnCount": 0,
        "weakenCount": 1,
        "uncertainCount": 1,
        "processedCount": 0,
    }
    validate_type("Inbox", wire(page))


@pytest.mark.parametrize(
    "damage", [None, "missing_evidence", "offset", "file", "version", "holding", "thesis"]
)
@pytest.mark.parametrize("response", [None, "ignore", "reopen"])
def test_portfolio_counts_match_inbox_after_actions_and_incomplete_evidence(
    db: Database, service: InboxService, damage: str | None, response: str | None
) -> None:
    from sentinel.portfolio import PortfolioService

    selected = seed(db, relation="overturn")
    seed(db, 11, seq=1, relation="weaken")
    seed(db, 12, event=2, relation="uncertain", headline=0.55)
    if response is not None:
        service.act(selected, "ignore", None)
        if response == "reopen":
            service.reopen(selected)
    if damage is not None:
        changes = {
            "missing_evidence": "UPDATE decision SET evidence_kind=NULL WHERE decision_id=?",
            "offset": "UPDATE decision SET evidence_end=999 WHERE decision_id=?",
            "file": "UPDATE event_file SET text_status='failed', text=NULL",
            "version": "DELETE FROM thesis_version",
            "holding": "UPDATE holding SET archived_at=TIMESTAMP '2026-11-02'",
            "thesis": "UPDATE thesis SET archived_at=TIMESTAMP '2026-11-02'",
        }
        with db.write() as tx:
            tx.execute(
                changes[damage], [selected] if damage in ("missing_evidence", "offset") else []
            )
    inbox = service.list_inbox()
    holdings = PortfolioService(db).list_holdings()
    assert sum(item.pending_count for item in holdings) == len(inbox.items)
    assert sum(item.uncertain_count for item in holdings) == len(inbox.uncertain)
    assert (
        sum(item.pending_count + item.uncertain_count for item in holdings)
        == inbox.summary.pending_count
    )


@pytest.mark.parametrize("relation", ["none", "support"])
def test_non_alert_relations_never_enter_any_group(
    db: Database, service: InboxService, relation: str
) -> None:
    selected = seed(db, relation=relation)
    action(db, selected, 100, NOW)
    page = service.list_inbox()
    assert page.items == page.uncertain == page.processed == []


def test_sort_severity_headline_published_then_id(db: Database, service: InboxService) -> None:
    a = seed(db, 10, event=1, headline=0.9)
    b = seed(db, 11, event=2, relation="overturn", headline=0.7)
    c = seed(db, 12, event=3, headline=0.95)
    d = seed(db, 13, event=4, headline=0.9, published=NOW + timedelta(seconds=1))
    e = seed(db, 14, event=5, headline=0.9)
    assert [item.decision_id for item in service.list_inbox().items] == [b, c, d, a, e]


def test_uncertain_sort_headline_published_then_id(db: Database, service: InboxService) -> None:
    a = seed(db, event=1, relation="uncertain", headline=0.55)
    b = seed(db, 11, event=2, relation="uncertain", headline=0.6)
    c = seed(
        db, 12, event=3, relation="uncertain", headline=0.55, published=NOW + timedelta(seconds=1)
    )
    assert [item.decision_id for item in service.list_inbox().uncertain] == [b, c, a]


@pytest.mark.parametrize("change", ["thesis", "holding", "status"])
def test_archived_entities_hide_lists_but_preserve_details(
    db: Database, service: InboxService, change: str
) -> None:
    selected = seed(db)
    service.act(selected, "ignore", None)
    with db.write() as tx:
        if change == "thesis":
            tx.execute("UPDATE thesis SET archived_at=?, status='archived'", [NOW])
        elif change == "holding":
            tx.execute("UPDATE holding SET archived_at=?", [NOW])
        else:
            tx.execute("UPDATE thesis SET status='archived'")
    page = service.list_inbox()
    assert page.items == page.uncertain == page.processed == []
    detail = service.get_decision(selected)
    assert detail.decision_id == selected and len(detail.actions) == 1
    validate_type("DecisionDetail", wire(detail))


def test_old_version_stays_pending_with_snapshot_text_and_kill_condition(
    db: Database,
    service: InboxService,
) -> None:
    selected = seed(db)
    with db.write() as tx:
        tx.execute("UPDATE thesis_version SET kill_condition='Sales decline' WHERE version=1")
        tx.execute(
            "INSERT INTO thesis_version VALUES (?, 2, 'Updated logic', NULL, 'v2', ?)",
            [uid(2), NOW],
        )
        tx.execute("UPDATE thesis SET current_version=2")
    summary = service.list_inbox().items[0]
    assert summary.decision_id == selected
    assert summary.thesis_version == 1 and summary.thesis_current_version == 2
    assert summary.thesis_statement == "Sales will grow"
    assert summary.kill_condition == "Sales decline"
    assert service.get_decision(selected).thesis_is_latest is False


@pytest.mark.parametrize(
    "kind,start,end,text",
    [
        (None, None, None, TEXT),
        ("unknown", None, None, TEXT),
        ("sentence", -1, 3, TEXT),
        ("sentence", 0, 1000, TEXT),
        ("sentence", 3, 3, TEXT),
        ("sentence", 4, 2, TEXT),
        ("sentence", None, 3, TEXT),
        ("sentence", 0, None, TEXT),
        ("passage", None, None, ""),
        ("passage", None, None, " \u3000 "),
        ("passage", 0, 1, TEXT),
        ("sentence", 0, 1, "   "),
        ("title", None, None, TEXT),
    ],
)
def test_invalid_evidence_excluded_without_fill_and_detail_internal(
    db: Database,
    service: InboxService,
    caplog: pytest.LogCaptureFixture,
    kind: str | None,
    start: int | None,
    end: int | None,
    text: str,
) -> None:
    selected = seed(db, kind=kind, start=start, end=end, text=text)
    before = query(db, "SELECT * FROM decision")
    assert service.list_inbox().items == []
    assert "INTERNAL" in str([record.__dict__ for record in caplog.records])
    with pytest.raises(InternalError):
        service.get_decision(selected)
    with pytest.raises(InternalError):
        service.act(selected, "ignore", None)
    assert query(db, "SELECT * FROM decision") == before
    assert query(db, "SELECT * FROM thesis_action") == []


def test_missing_top_evidence_does_not_select_weaker_fallback(
    db: Database, service: InboxService
) -> None:
    seed(db, relation="overturn", kind=None)
    seed(db, 11, seq=1, relation="weaken", kind="passage", start=None, end=None)
    assert service.list_inbox().items == []


@pytest.mark.parametrize(
    "file_seq,kind,part",
    [(0, "sentence", "主文档"), (1, "passage", "EX-99.1"), (-1, "title", "标题")],
)
def test_evidence_kinds_and_unicode_offsets(
    db: Database, service: InboxService, file_seq: int, kind: str, part: str
) -> None:
    selected = seed(
        db,
        kind=kind,
        file_seq=file_seq,
        start=21 if kind == "sentence" else None,
        end=23 if kind == "sentence" else None,
        text="Synthetic disclosure" if file_seq == -1 else TEXT,
    )
    evidence = service.get_decision(selected).evidence
    assert evidence.file_part == part
    if kind == "sentence":
        assert evidence.text == TEXT[21:23] == "雪😀"
        assert evidence.sentence_start == 21 and evidence.sentence_end == 23
    elif kind == "passage":
        assert evidence.text == TEXT
        assert evidence.sentence_start is evidence.sentence_end is None
    else:
        assert evidence.text == "Synthetic disclosure"
        assert evidence.sentence_start is evidence.sentence_end is None


@pytest.mark.parametrize(
    "damage",
    [
        "passage",
        "event",
        "version",
        "instrument",
        "file",
        "event_link",
        "instrument_link",
        "file_text",
    ],
)
def test_orphans_and_mismatches_are_internal_not_not_found(
    db: Database, service: InboxService, damage: str
) -> None:
    selected = seed(db)
    with db.write() as tx:
        statements = {
            "passage": "DELETE FROM event_passage",
            "event": "DELETE FROM event_doc",
            "version": "DELETE FROM thesis_version",
            "instrument": "DELETE FROM instrument",
            "file": "DELETE FROM event_file",
            "event_link": "UPDATE decision SET event_id='us:missing'",
            "instrument_link": "UPDATE decision SET instrument_id='us:ZZFD'",
            "file_text": "UPDATE event_file SET text=NULL, text_status='failed'",
        }
        tx.execute(statements[damage])
    assert service.list_inbox().items == []
    with pytest.raises(InternalError):
        service.get_decision(selected)


def test_last_action_reopen_returns_item_to_pending(db: Database, service: InboxService) -> None:
    selected = seed(db)
    service.act(selected, "still_valid", None)
    result = service.reopen(selected)
    assert result.action.action == "reopen"
    page = service.list_inbox()
    assert len(page.items) == 1 and page.processed == []
    assert [a.action for a in service.get_decision(selected).actions] == ["reopen", "still_valid"]
    count = query(db, "SELECT COUNT(*) FROM thesis_action")
    assert wire(service.reopen(selected)) == wire(result)
    assert query(db, "SELECT COUNT(*) FROM thesis_action") == count


def test_only_latest_action_controls_state(db: Database, service: InboxService) -> None:
    selected = seed(db)
    action(db, selected, 100, NOW, "ignore")
    action(db, selected, 101, NOW, "still_valid")
    item = service.list_inbox().processed[0]
    assert item.action.action == "still_valid"
    assert [a.action for a in service.get_decision(selected).actions] == ["still_valid", "ignore"]


def test_processed_window_excludes_31_days_old_and_includes_boundary(
    db: Database, service: InboxService
) -> None:
    old = seed(db)
    boundary = seed(db, 11, event=2)
    recent = seed(db, 12, event=3)
    action(db, old, 100, NOW - timedelta(days=31))
    action(db, boundary, 101, NOW - timedelta(days=30))
    action(db, recent, 102, NOW)
    assert [item.decision_id for item in service.list_inbox().processed] == [recent, boundary]
    assert len(service.get_decision(old).actions) == 1


@pytest.mark.parametrize("value", ["still_valid", "revise", "exit_intent", "ignore"])
def test_act_does_not_modify_thesis_or_order_tables(
    db: Database, service: InboxService, value: str
) -> None:
    selected = seed(db)
    tables = ("thesis", "thesis_version", "holding", "decision", "paper_order", "cash_ledger")
    before = {table: query(db, "SELECT * FROM " + table) for table in tables}
    result = service.act(selected, value, None)
    assert result.action.action == value
    assert {table: query(db, "SELECT * FROM " + table) for table in tables} == before
    validate_type("DecisionSummary", wire(result))


def test_act_appends_multiple_records_and_same_timestamp_latest(
    db: Database, service: InboxService
) -> None:
    selected = seed(db)
    for index in range(20):
        result = service.act(selected, "ignore", str(index))
        assert result.action.note == str(index)
    assert query(db, "SELECT COUNT(*) FROM thesis_action") == [(20,)]
    assert [a.note for a in service.get_decision(selected).actions] == [
        str(index) for index in reversed(range(20))
    ]


def test_reopen_on_pending_is_noop(db: Database, service: InboxService) -> None:
    selected = seed(db)
    assert service.reopen(selected).action is None
    assert query(db, "SELECT * FROM thesis_action") == []


@pytest.mark.parametrize(
    "note,expected",
    [
        (None, None),
        (" \u3000\t", None),
        ("\u3000雪😀\t", "雪😀"),
        ("😀" * 200, "😀" * 200),
        (" " + "😀" * 200 + " ", "😀" * 200),
    ],
)
def test_note_is_trimmed_and_blank_becomes_null(
    db: Database, service: InboxService, note: str | None, expected: str | None
) -> None:
    selected = seed(db)
    assert service.act(selected, "ignore", note).action.note == expected
    assert query(db, "SELECT note FROM thesis_action") == [(expected,)]


@pytest.mark.parametrize("method", ["get_decision", "act", "reopen"])
def test_missing_decision_raises_not_found(
    db: Database, service: InboxService, method: str
) -> None:
    with pytest.raises(UserError) as error:
        getattr(service, method)(uid(999), *(["ignore", None] if method == "act" else []))
    assert error.value.code == "NOT_FOUND"
    assert error.value.to_wire()["message"] == "没有找到这条判定"
    assert query(db, "SELECT * FROM thesis_action") == []


def test_protected_write_reads_own_action_without_new_read(
    db: Database, service: InboxService, monkeypatch: pytest.MonkeyPatch
) -> None:
    selected = seed(db)
    original_read = db.read

    def forbidden_read():
        raise AssertionError("write result must use the original protected tx")

    monkeypatch.setattr(db, "read", forbidden_read)
    assert service.act(selected, "ignore", "own write").action.note == "own write"
    assert service.reopen(selected).action.action == "reopen"
    monkeypatch.setattr(db, "read", original_read)
    assert query(db, "SELECT COUNT(*) FROM thesis_action") == [(2,)]


def test_response_failure_rolls_back_append(
    db: Database, service: InboxService, monkeypatch: pytest.MonkeyPatch
) -> None:
    selected = seed(db)
    original = service._get_summary
    calls = 0

    def fail_after_insert(reader, decision_id):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise InternalError(detail="synthetic response failure")
        return original(reader, decision_id)

    monkeypatch.setattr(service, "_get_summary", fail_after_insert)
    with pytest.raises(InternalError):
        service.act(selected, "ignore", None)
    assert query(db, "SELECT * FROM thesis_action") == []


def test_processed_pagination_keeps_pending_complete_and_same_time_cursor(
    db: Database,
    service: InboxService,
) -> None:
    pending = seed(db)
    uncertain = seed(db, 11, event=2, relation="uncertain", headline=0.55)
    processed = [seed(db, 12 + i, event=3 + i) for i in range(5)]
    for index, selected in enumerate(processed):
        action(db, selected, 100 + index, NOW)
    found, cursor = [], None
    while True:
        page = service.list_inbox(limit=2, cursor=cursor)
        assert [item.decision_id for item in page.items] == [pending]
        assert [item.decision_id for item in page.uncertain] == [uncertain]
        assert page.summary.processed_count == len(page.processed)
        validate_type("Inbox", wire(page))
        assert "nextCursor" not in wire(page)
        found.extend(item.decision_id for item in page.processed)
        cursor = page.next_cursor
        if cursor is None:
            break
        decoded = base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4)).decode()
        assert decoded.startswith(clock.to_iso(NOW) + "|")
    assert found == list(reversed(processed)) and len(found) == len(set(found))


@pytest.mark.parametrize("limit", [0, 201, -1, True, "2", None])
def test_invalid_internal_page_limit(service: InboxService, limit: object) -> None:
    with pytest.raises(UserError) as error:
        service.list_inbox(limit=limit)
    assert error.value.code == "INVALID_ARGUMENT" and error.value.field == "limit"


@pytest.mark.parametrize(
    "cursor",
    [
        "",
        "SQL' OR 1=1--",
        "eA",
        "😀",
        "=" * 4,
        base64.urlsafe_b64encode(b"2026-11-02|bad").decode(),
    ],
)
def test_invalid_cursor_rejected(service: InboxService, cursor: str) -> None:
    with pytest.raises(UserError) as error:
        service.list_inbox(cursor=cursor)
    assert error.value.field == "cursor"


def test_real_setup_usage_limit_reset_lastscan_and_dynamic_status(db: Database) -> None:
    snapshots = [status(NoneReader(), NOW), status(NoneReader(), NOW)]
    snapshots[1] = snapshots[1].model_copy(update={"offline": False})

    def provider(reader, as_of):
        return snapshots.pop(0)

    service = InboxService(db, status_provider=provider)
    with db.write() as tx:
        tx.execute(
            "INSERT INTO usage_daily VALUES (?, 'jev_direct', 'jev-1.14.0', 31, 0, 1)", [NOW.date()]
        )
        tx.execute(
            "INSERT INTO usage_daily VALUES (?, 'jevdb', 'jev-1.14.0', 0, 11, 1)", [NOW.date()]
        )
        tx.execute(
            "INSERT INTO usage_daily VALUES (?, 'jevdb', 'old-model', 0, 99, 1)",
            [NOW.date() - timedelta(days=1)],
        )
        tx.execute("INSERT INTO setting VALUES ('dailyTokenBudget', '10000', ?)", [NOW])
        tx.execute(
            "INSERT INTO scan_run (run_id, trigger, market, status, window_start, window_end, "
            "engine, model_id, question_set_version, instruments, skipped_no_thesis, filings, "
            "passages, decisions, error_code, error_message, finished_at, created_at) "
            "VALUES (?, 'manual', 'us', 'partial', ?, ?, 'jev_direct', 'jev-1.14.0', 'qs-test', "
            "3, 2, 5, 7, 11, 'SOURCE_UNAVAILABLE', 'Synthetic source failure', ?, ?)",
            [uid(500), NOW, NOW, NOW, NOW],
        )
    first = wire(service.list_inbox())
    assert first["setup"] == {"holdings": 1, "activeTheses": 1, "scannableInstruments": 1}
    assert first["dataStatus"]["budget"] == {
        "usedTokens": 42,
        "limitTokens": 10000,
        "resetAt": "2026-11-03T00:00:00Z",
    }
    assert first["lastScan"]["stats"] == {
        "instruments": 3,
        "skippedNoThesis": 2,
        "filings": 5,
        "passages": 7,
        "decisions": 11,
    }
    assert first["lastScan"]["error"]["message"] == "Synthetic source failure"
    assert first["dataStatus"]["engine"]["state"] == "unconfigured"
    assert first["dataStatus"]["marketState"] == "holiday"
    assert first["dataStatus"]["nextOpenAt"] == "2026-11-02T14:30:00Z"
    validate_type("Inbox", first)
    with db.write() as tx:
        tx.execute("UPDATE setting SET value_json='20000' WHERE key='dailyTokenBudget'")
    second = wire(service.list_inbox())
    assert second["dataStatus"]["offline"] is False
    assert second["dataStatus"]["budget"]["limitTokens"] == 20000


class NoneReader:
    def execute(self, sql):
        return None


def test_list_uses_one_snapshot_including_provider_and_usage(
    db: Database, monkeypatch: pytest.MonkeyPatch
) -> None:
    selected = seed(db)
    reads = 0
    original = db.read

    @contextmanager
    def counted():
        nonlocal reads
        reads += 1
        with original() as reader:
            yield reader

    monkeypatch.setattr(db, "read", counted)
    with duckdb.connect(str(db.path)) as outside:

        def provider(reader, as_of):
            outside.execute("UPDATE holding SET archived_at=?", [NOW])
            outside.execute(
                "INSERT INTO usage_daily VALUES (?, 'jevdb', 'jev-1.14.0', 0, 99, 1)", [NOW.date()]
            )
            return status(reader, as_of)

        page = InboxService(db, status_provider=provider).list_inbox()
    assert reads == 1
    assert page.items[0].decision_id == selected
    assert page.setup.holdings == 1
    assert page.data_status.budget.used_tokens == 0


@pytest.fixture
def dispatcher(service: InboxService) -> Dispatcher:
    result = Dispatcher()
    register_handlers(result, service)
    return result


def call(dispatcher: Dispatcher, method: str, params: dict) -> dict:
    return dispatcher.dispatch(
        dispatcher.lookup(method), params, RequestContext("r-p03", method, CancelToken(), NOW)
    )


@pytest.mark.parametrize("method", METHODS)
def test_contract_examples_and_actual_registered_handlers(
    db: Database, dispatcher: Dispatcher, method: str
) -> None:
    document = json.loads((ROOT / f"contracts/methods/{method}.json").read_text())
    spec = dispatcher.lookup(method)
    assert spec is not None and spec.result_model is not None
    assert set(dispatcher.methods()) == set(METHODS)
    for example in document["examples"]:
        if "result" in example:
            parsed = spec.result_model.model_validate(example["result"], strict=True)
            assert wire(parsed) == example["result"]
            spec.params_model.model_validate(example["params"], by_alias=True, by_name=False)
    selected = seed(db)
    params = {} if method == "inbox.list" else {"decisionId": selected}
    if method == "decision.act":
        params.update(action="revise", note=" \u3000雪😀 ")
    response = call(dispatcher, method, params)
    assert "result" in response
    Draft202012Validator(document["result"], registry=REGISTRY).validate(response["result"])
    if method == "decision.act":
        assert response["result"]["action"]["note"] == "雪😀"
    assert call(dispatcher, method, params | {"unknown": 1})["error"]["code"] == "INVALID_ARGUMENT"


@pytest.mark.parametrize("method", METHODS)
def test_rpc_params_are_closed_and_reject_snake_names(dispatcher: Dispatcher, method: str) -> None:
    if method == "inbox.list":
        params = {"limit": 1}
    else:
        params = {"decision_id": uid(10)}
        if method == "decision.act":
            params["action"] = "ignore"
    assert call(dispatcher, method, params)["error"]["code"] == "INVALID_ARGUMENT"


@pytest.mark.parametrize("action_value", ["reopen", "buy", "", 1, None, True])
def test_invalid_action_no_writes(
    db: Database, dispatcher: Dispatcher, service: InboxService, action_value: object
) -> None:
    selected = seed(db)
    response = call(dispatcher, "decision.act", {"decisionId": selected, "action": action_value})
    assert response["error"]["code"] == "INVALID_ARGUMENT"
    assert response["error"]["data"]["field"] == "action"
    with pytest.raises(UserError):
        service.act(selected, action_value, None)
    assert query(db, "SELECT * FROM thesis_action") == []


@pytest.mark.parametrize("note", ["😀" * 201, 1, True, [], {}])
def test_invalid_note_no_write_and_max_metadata(
    db: Database, dispatcher: Dispatcher, note: object
) -> None:
    selected = seed(db)
    response = call(
        dispatcher, "decision.act", {"decisionId": selected, "action": "ignore", "note": note}
    )
    assert response["error"]["code"] == "INVALID_ARGUMENT"
    assert response["error"]["data"]["field"] == "note"
    if isinstance(note, str):
        assert response["error"]["data"]["max"] == 200
    assert query(db, "SELECT * FROM thesis_action") == []


def test_parameterized_ids_and_notes_do_not_execute_sql(
    db: Database, dispatcher: Dispatcher, service: InboxService
) -> None:
    selected = seed(db)
    malicious = "'; DROP TABLE decision; --"
    result = service.act(selected, "ignore", malicious)
    assert result.action.note == malicious
    response = call(dispatcher, "decision.get", {"decisionId": malicious})
    assert response["error"]["code"] == "NOT_FOUND"
    assert query(db, "SELECT COUNT(*) FROM decision") == [(1,)]


@pytest.mark.parametrize("budget", ["null", "true", "0", "50000001", "1.0", '"10000"', "bad"])
def test_corrupt_budget_is_internal_not_defaulted(
    db: Database, service: InboxService, budget: str
) -> None:
    with db.write() as tx:
        tx.execute("INSERT INTO setting VALUES ('dailyTokenBudget', ?, ?)", [budget, NOW])
    with pytest.raises(InternalError):
        service.list_inbox()


def test_missing_scan_table_is_not_silently_ignored(db: Database, service: InboxService) -> None:
    with db.write() as tx:
        tx.execute("DROP TABLE scan_run")
    with pytest.raises(duckdb.CatalogException):
        service.list_inbox()


def test_status_provider_is_required_and_invalid_state_rejected(db: Database) -> None:
    with pytest.raises(TypeError):
        InboxService(db)
    with pytest.raises(ValidationError):
        StatusSnapshot.model_validate({"source": {}, "engine": {}, "offline": False})


def test_same_timestamp_actions_across_handles_return_each_own_write(db: Database) -> None:
    selected = seed(db)
    other = Database(db.path)
    other.open()
    try:
        services = [InboxService(database, status_provider=status) for database in (db, other)]

        def respond(index):
            return services[index % 2].act(selected, "ignore", str(index)).action.note

        with ThreadPoolExecutor(max_workers=4) as pool:
            assert list(pool.map(respond, range(16))) == [str(i) for i in range(16)]
        history = services[0].get_decision(selected).actions
        assert len(history) == 16
        assert set(record.note for record in history) == {str(i) for i in range(16)}
    finally:
        other.close()


def test_processed_subsecond_cursor_and_newer_timestamp_win(
    db: Database, service: InboxService
) -> None:
    old = seed(db)
    recent = seed(db, 11, event=2)
    same = seed(db, 12, event=3)
    action(db, old, 500, NOW - timedelta(microseconds=1))
    action(db, recent, 100, NOW)
    action(db, same, 101, NOW)
    first = service.list_inbox(limit=1)
    second = service.list_inbox(limit=1, cursor=first.next_cursor)
    third = service.list_inbox(limit=1, cursor=second.next_cursor)
    assert [page.processed[0].decision_id for page in (first, second, third)] == [same, recent, old]
    assert third.next_cursor is None


def test_default_processed_limit_does_not_limit_unresolved_groups(
    db: Database, service: InboxService
) -> None:
    for index in range(51):
        selected = seed(db, 10 + index, event=1 + index)
        action(db, selected, 100 + index, NOW)
    pending = seed(db, 200, event=200)
    page = service.list_inbox()
    assert len(page.processed) == page.summary.processed_count == 50
    assert page.next_cursor is not None
    assert [item.decision_id for item in page.items] == [pending]
    assert len(service.list_inbox(limit=200).processed) == 51


def test_representative_is_chosen_across_thesis_versions(
    db: Database, service: InboxService
) -> None:
    selected = seed(db, relation="overturn", headline=0.8)
    second = seed(db, 11, seq=1, relation="weaken", headline=0.99)
    with db.write() as tx:
        tx.execute(
            "INSERT INTO thesis_version VALUES (?, 2, 'Second version', NULL, 'v2', ?)",
            [uid(2), NOW],
        )
        tx.execute("UPDATE thesis SET current_version=2")
        tx.execute("UPDATE decision SET thesis_version=2 WHERE decision_id=?", [second])
    assert [item.decision_id for item in service.list_inbox().items] == [selected]
    assert service.get_decision(second).decision_id == second
    assert service.get_decision(second).thesis_statement == "Second version"


@pytest.mark.parametrize(
    "field,value",
    [
        ("p_against", float("nan")),
        ("p_contradicts", float("inf")),
        ("p_relevant", -1.0),
        ("headline", 1.1),
    ],
)
def test_invalid_probabilities_are_not_fabricated(
    db: Database, service: InboxService, field: str, value: float
) -> None:
    selected = seed(db)
    with db.write() as tx:
        tx.execute("UPDATE decision SET " + field + "=?", [value])
    assert service.list_inbox().items == []
    with pytest.raises(InternalError):
        service.get_decision(selected)


@pytest.mark.parametrize(
    "at,expected",
    [
        ("2026-11-02T14:00:00Z", "pre"),
        ("2026-11-02T15:00:00Z", "open"),
        ("2026-11-02T22:00:00Z", "after"),
        ("2026-11-03T02:00:00Z", "closed"),
        ("2026-11-26T15:00:00Z", "holiday"),
    ],
)
def test_data_status_market_uses_real_calendar_and_clock(
    db: Database, monkeypatch: pytest.MonkeyPatch, at: str, expected: str
) -> None:
    monkeypatch.setenv("SENTINEL_CLOCK", at)
    snapshot = status(NoneReader(), clock.now())
    result = InboxService(db, status_provider=lambda reader, as_of: snapshot).list_inbox()
    assert result.as_of == at
    assert result.data_status.market_state == expected
    validate_type("DataStatus", wire(result.data_status))


def test_title_offsets_and_empty_title_are_not_repaired(
    db: Database, service: InboxService
) -> None:
    selected = seed(db, kind="title", file_seq=-1, text="Synthetic disclosure", start=0, end=3)
    assert service.list_inbox().items == []
    with pytest.raises(InternalError):
        service.get_decision(selected)
    with db.write() as tx:
        tx.execute("UPDATE decision SET evidence_start=NULL, evidence_end=NULL")
        tx.execute("UPDATE event_passage SET text=' '")
        tx.execute("UPDATE event_doc SET title=' '")
    assert service.list_inbox().items == []
    with pytest.raises(InternalError):
        service.get_decision(selected)


@pytest.mark.parametrize(
    "scan_status",
    ["queued", "running", "succeeded", "partial", "failed", "cancelled", "interrupted"],
)
def test_latest_scan_uses_created_time_then_ulid_and_preserves_null_finish(
    db: Database,
    service: InboxService,
    scan_status: str,
) -> None:
    with db.write() as tx:
        tx.executemany(
            "INSERT INTO scan_run (run_id, trigger, market, status, window_start, window_end, "
            "engine, model_id, question_set_version, created_at) "
            "VALUES (?, 'manual', 'us', ?, ?, ?, 'jev_direct', 'jev-1.14.0', 'qs-test', ?)",
            [[uid(500), "succeeded", NOW, NOW, NOW], [uid(501), scan_status, NOW, NOW, NOW]],
        )
    last_scan = service.list_inbox().last_scan
    assert last_scan.run_id == uid(501) and last_scan.status == scan_status
    assert last_scan.finished_at is None and last_scan.error is None
    assert wire(last_scan)["stats"] == {
        "instruments": 0,
        "skippedNoThesis": 0,
        "filings": 0,
        "passages": 0,
        "decisions": 0,
    }


def test_rpc_not_found_uses_own_local_message_and_internal_has_request_id(
    db: Database,
    dispatcher: Dispatcher,
) -> None:
    response = call(dispatcher, "decision.get", {"decisionId": uid(1000)})
    assert response["error"] == {
        "code": "NOT_FOUND",
        "message": "没有找到这条判定",
        "data": {"retryable": False},
    }
    selected = seed(db, kind=None)
    response = call(dispatcher, "decision.get", {"decisionId": selected})
    assert response["error"]["code"] == "INTERNAL"
    assert response["error"]["data"]["requestId"] == "r-p03"


@pytest.mark.parametrize("db", [(), ("3.8",), ("3.10",), ("3.8", "3.10")], indirect=True)
def test_fixture_coexists_with_all_discovered_migrations(
    db: Database,
    service: InboxService,
    tmp_path: Path,
) -> None:
    migrations_dir = tmp_path / "pending-migrations"
    discovered = discover_migrations(migrations_dir)
    actual_migrations = discover_migrations(DEFAULT_MIGRATIONS_DIR)
    for migration in actual_migrations:
        assert (
            migrations_dir / migration.sql_path.name
        ).read_bytes() == migration.sql_path.read_bytes()
    actual = {migration.version for migration in actual_migrations}
    recorded = {row[0] for row in query(db, "SELECT version FROM schema_version")}
    assert recorded == {migration.version for migration in discovered}
    assert actual <= recorded
    for section, table, version, name in SECTION_MIGRATIONS:
        assert query(
            db, "SELECT COUNT(*) FROM information_schema.tables WHERE table_name=?", [table]
        ) == [(1,)]
        if version in recorded:
            assert query(
                db, "SELECT name, checksum FROM schema_version WHERE version=?", [version]
            ) == [(name, hashlib.sha256(ddl(section)).hexdigest())]
    assert db.migrate(migrations_dir).applied == ()
    selected = seed(db)
    assert service.list_inbox().items[0].decision_id == selected
    assert service.act(selected, "ignore", "migrations coexist").action.note == "migrations coexist"
    assert service.get_decision(selected).actions[0].action == "ignore"


@pytest.mark.parametrize("damage", ["checksum", "unrecorded", "missing_table"])
def test_fixture_does_not_hide_existing_section_damage(db: Database, damage: str) -> None:
    version = query(db, "SELECT name, checksum FROM schema_version WHERE version=6")
    assert version == [("decision", hashlib.sha256(ddl("3.6")).hexdigest())]
    with db.write() as tx:
        if damage == "checksum":
            tx.execute("UPDATE schema_version SET checksum='corrupt' WHERE version=6")
        elif damage == "unrecorded":
            tx.execute("DELETE FROM schema_version WHERE version=6")
        else:
            tx.execute("DROP TABLE decision")
    with pytest.raises(AssertionError, match="authoritative migration checksum|missing its table"):
        complete_fixture_sections(db)
    assert query(db, "SELECT COUNT(*) FROM schema_version WHERE version=6") == [
        (0 if damage == "unrecorded" else 1,)
    ]
    assert query(
        db, "SELECT COUNT(*) FROM information_schema.tables WHERE table_name='decision'"
    ) == [(0 if damage == "missing_table" else 1,)]


def test_fixture_does_not_recreate_delivered_section_after_table_and_record_loss(
    tmp_path: Path,
) -> None:
    database = Database(tmp_path / "missing-delivered.duckdb")
    database.open()
    try:
        database.migrate()
        with database.write() as tx:
            tx.execute("DROP TABLE decision")
            tx.execute("DELETE FROM schema_version WHERE version=6")
        with pytest.raises(AssertionError, match="missing its table"):
            complete_fixture_sections(database)
        assert query(
            database, "SELECT COUNT(*) FROM information_schema.tables WHERE table_name='decision'"
        ) == [(0,)]
    finally:
        database.close()
