from decimal import Decimal

import pytest

from sentinel import clock, ids
from sentinel.errors import UserError
from sentinel.portfolio import PortfolioService
from sentinel.storage import Database

from .conftest import NOW, query


def test_upsert_reactivates_archived_holding(service: PortfolioService, db: Database) -> None:
    first = service.upsert_holding("us:ZZAR", Decimal("0"), None, None)
    service.archive_holding("us:ZZAR")
    updated = service.upsert_holding("us:ZZAR", Decimal("25"), None, None)
    assert updated.holding_id == first.holding_id and ids.is_ulid(updated.holding_id)
    assert updated.quantity == Decimal("25.0000")
    assert query(db, "SELECT archived_at FROM holding") == [(None,)]


def test_upsert_holding_rolls_back_when_cost_invalid(
    service: PortfolioService, db: Database
) -> None:
    service.upsert_holding("us:ZZAR", Decimal("5"), Decimal("10"), None)
    before = query(db, "SELECT * FROM holding")
    with pytest.raises(UserError) as caught:
        service.upsert_holding("us:ZZAR", Decimal("0"), Decimal("10"), None)
    assert caught.value.field == "avgCost"
    assert query(db, "SELECT * FROM holding") == before


def test_sixth_active_thesis_is_rejected(service: PortfolioService) -> None:
    for number in range(5):
        service.create_thesis("us:ZZAR", f"Thesis {number}", None)
    with pytest.raises(UserError) as caught:
        service.create_thesis("us:ZZAR", "Sixth thesis", None)
    assert caught.value.code == "INVALID_ARGUMENT" and caught.value.params["max"] == 5


def test_update_same_content_does_not_add_version(service: PortfolioService, db: Database) -> None:
    original = service.create_thesis("us:ZZAR", "Margin grows", None)
    same = service.update_thesis(original.thesis_id, "  Margin grows  ", " \n ", 1)
    assert same == original
    assert query(db, "SELECT count(*) FROM thesis_version") == [(1,)]


def test_update_stale_version_returns_conflict(service: PortfolioService) -> None:
    first = service.create_thesis("us:ZZAR", "First", None)
    service.update_thesis(first.thesis_id, "Second", None, 1)
    service.update_thesis(first.thesis_id, "Third", None, 2)
    with pytest.raises(UserError) as caught:
        service.update_thesis(first.thesis_id, "Third", None, 2)
    assert caught.value.code == "CONFLICT" and caught.value.params["currentVersion"] == 3


def test_all_mutations_use_utc_clock(
    service: PortfolioService, db: Database, monkeypatch: pytest.MonkeyPatch
) -> None:
    service.upsert_holding("us:ZZAR", Decimal("1"), None, None)
    thesis = service.create_thesis("us:ZZAR", "First", None)
    assert thesis.created_at == clock.to_iso(NOW)
    assert query(db, "SELECT created_at, updated_at FROM holding") == [(NOW, NOW)]
    assert query(db, "SELECT created_at FROM thesis_version") == [(NOW,)]
    monkeypatch.setenv("SENTINEL_CLOCK", "2026-11-03T08:35:00+08:00")
    changed = clock.now()
    service.update_thesis(thesis.thesis_id, "Second", None, 1)
    service.archive_thesis(thesis.thesis_id)
    service.archive_holding("us:ZZAR")
    assert query(db, "SELECT updated_at, archived_at FROM thesis") == [(changed, changed)]
    assert query(db, "SELECT updated_at, archived_at FROM holding") == [(changed, changed)]


@pytest.mark.parametrize("instrument_id", ["us:ABSENT", "hk:ZZBK", "us:zzar"])
def test_mutations_reject_unknown_or_unsupported_instruments(
    service: PortfolioService, db: Database, instrument_id: str
) -> None:
    with pytest.raises(UserError) as holding:
        service.upsert_holding(instrument_id, Decimal("1"), None, None)
    with pytest.raises(UserError) as thesis:
        service.create_thesis(instrument_id, "First", None)
    assert holding.value.code == thesis.value.code == "NOT_FOUND"
    assert query(db, "SELECT count(*) FROM holding") == [(0,)]
    assert query(db, "SELECT count(*) FROM thesis") == [(0,)]


def test_instrument_validation_uses_write_transaction_snapshot(
    service: PortfolioService, db: Database, monkeypatch: pytest.MonkeyPatch
) -> None:
    from sentinel.portfolio.repository import PortfolioRepository

    get = PortfolioRepository.get_instrument

    def deactivate(repo, tx, instrument_id):
        tx.execute(
            "UPDATE instrument SET is_active = FALSE WHERE instrument_id = ?", [instrument_id]
        )
        return get(repo, tx, instrument_id)

    monkeypatch.setattr(PortfolioRepository, "get_instrument", deactivate)
    for mutation in (
        lambda: service.upsert_holding("us:ZZAR", Decimal("1"), None, None),
        lambda: service.create_thesis("us:ZZAR", "First", None),
    ):
        with pytest.raises(UserError) as caught:
            mutation()
        assert caught.value.code == "NOT_FOUND"
    assert query(db, "SELECT is_active FROM instrument WHERE instrument_id = 'us:ZZAR'") == [
        (True,)
    ]
    assert query(db, "SELECT count(*) FROM holding") == [(0,)]
    assert query(db, "SELECT count(*) FROM thesis") == [(0,)]


def test_write_views_read_own_inserts_and_updates(
    service: PortfolioService, db: Database, monkeypatch: pytest.MonkeyPatch
) -> None:
    def forbidden_read(*args, **kwargs):
        raise AssertionError("independent read inside a write transaction")

    with monkeypatch.context() as patch:
        patch.setattr(db, "read", forbidden_read)
        holding = service.upsert_holding(" us:ZZAR ", Decimal("2"), None, " first ")
        changed = service.upsert_holding("us:ZZAR", Decimal("3"), Decimal("12"), "second")
        assert changed.holding_id == holding.holding_id and changed.quantity == Decimal("3.0000")
        first = service.create_thesis(" us:ZZAR ", " First ", None)
        second = service.update_thesis(" " + first.thesis_id + " ", "Second", " Floor ", 1)
        assert second.version == second.version_count == 2
        assert second.statement == "Second" and second.kill_condition == "Floor"
    assert query(db, "SELECT current_version FROM thesis") == [(2,)]


@pytest.mark.parametrize("operation", ["create", "update"])
def test_second_write_failure_rolls_back_entire_thesis_transaction(
    service: PortfolioService,
    db: Database,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    operation: str,
) -> None:
    from sentinel.errors import InternalError
    from sentinel.storage import WriteTx

    first = service.create_thesis("us:ZZAR", "First", None)
    before = query(db, "SELECT * FROM thesis"), query(db, "SELECT * FROM thesis_version")
    execute = WriteTx.execute

    def fail_second(tx, sql, params=None):
        if operation == "create" and sql.startswith("INSERT INTO thesis_version"):
            return execute(
                tx,
                "INSERT INTO thesis_version VALUES (?, 0, NULL, NULL, 'bad', ?)",
                [first.thesis_id, NOW],
            )
        if operation == "update" and sql.startswith("UPDATE thesis SET current_version"):
            return execute(
                tx, "UPDATE thesis SET status = NULL WHERE thesis_id = ?", [first.thesis_id]
            )
        return execute(tx, sql, params)

    with monkeypatch.context() as patch:
        patch.setattr(WriteTx, "execute", fail_second)
        with pytest.raises(InternalError):
            if operation == "create":
                service.create_thesis("us:ZZAR", "Second thesis", None)
            else:
                service.update_thesis(first.thesis_id, "Changed", None, 1)
    assert (query(db, "SELECT * FROM thesis"), query(db, "SELECT * FROM thesis_version")) == before
    assert any(
        getattr(record, "sentinel", {}).get("event") == "portfolio.database.failed"
        for record in caplog.records
    )


def test_lost_update_returning_rolls_back_inserted_version(
    service: PortfolioService, db: Database, monkeypatch: pytest.MonkeyPatch
) -> None:
    from sentinel.storage import WriteTx

    first = service.create_thesis("us:ZZAR", "First", None)
    execute = WriteTx.execute

    def lose_update(tx, sql, params=None):
        if sql.startswith("UPDATE thesis SET current_version"):
            return execute(tx, sql.replace(" RETURNING", " AND FALSE RETURNING"), params)
        return execute(tx, sql, params)

    with monkeypatch.context() as patch:
        patch.setattr(WriteTx, "execute", lose_update)
        with pytest.raises(UserError) as caught:
            service.update_thesis(first.thesis_id, "Second", None, 1)
        assert caught.value.code == "CONFLICT"
    assert query(db, "SELECT current_version FROM thesis") == [(1,)]
    assert len(service.list_versions(first.thesis_id)) == 1


def test_two_concurrent_editors_only_one_wins(service: PortfolioService, db: Database) -> None:
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier

    first = service.create_thesis("us:ZZAR", "First", None)
    other_db = Database(db.path)
    other_db.open()
    other = PortfolioService(other_db)
    barrier = Barrier(2)

    def edit(pair):
        editor, statement = pair
        barrier.wait(timeout=5)
        try:
            return editor.update_thesis(first.thesis_id, statement, None, 1).version
        except UserError as exc:
            assert exc.params["currentVersion"] == 2
            return exc.code

    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(edit, [(service, "One"), (other, "Two")]))
        assert sorted(map(str, results)) == ["2", "CONFLICT"]
        assert len(service.list_versions(first.thesis_id)) == 2
    finally:
        other_db.close()


def test_concurrent_create_respects_five_active_limit(
    service: PortfolioService, db: Database
) -> None:
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier

    for i in range(4):
        service.create_thesis("us:ZZAR", str(i), None)
    barrier = Barrier(4)

    def create(i):
        barrier.wait(timeout=5)
        try:
            service.create_thesis("us:ZZAR", f"Concurrent {i}", None)
            return "ok"
        except UserError as exc:
            assert exc.params["max"] == 5
            return exc.code

    with ThreadPoolExecutor(max_workers=4) as pool:
        outcomes = list(pool.map(create, range(4)))
    assert outcomes.count("ok") == 1 and outcomes.count("INVALID_ARGUMENT") == 3
    assert len(service.list_active_theses("us:ZZAR")) == 5
    assert query(db, "SELECT count(*) FROM thesis_version") == [(5,)]


def test_archives_are_idempotent_and_release_active_limit(
    service: PortfolioService, db: Database, monkeypatch: pytest.MonkeyPatch
) -> None:
    service.upsert_holding("us:ZZAR", Decimal("0"), None, None)
    theses = [service.create_thesis("us:ZZAR", str(i), None) for i in range(5)]
    service.archive_holding("us:ZZAR")
    service.archive_thesis(theses[0].thesis_id)
    before = query(db, "SELECT * FROM holding"), query(db, "SELECT * FROM thesis")
    monkeypatch.setenv("SENTINEL_CLOCK", "2026-11-03T00:35:00Z")
    service.archive_holding("us:ZZAR")
    service.archive_thesis(theses[0].thesis_id)
    assert (query(db, "SELECT * FROM holding"), query(db, "SELECT * FROM thesis")) == before
    assert service.count_holdings() == 0 and service.list_scannable_instruments() == []
    assert len(service.list_theses(None, "archived")) == 1
    assert len(service.list_theses(None, "active")) == 4
    with pytest.raises(UserError) as caught:
        service.update_thesis(theses[0].thesis_id, "Changed", None, 1)
    assert caught.value.code == "NOT_FOUND"
    service.create_thesis("us:ZZAR", "Replacement", None)
    service.upsert_holding("us:ZZAR", Decimal("0"), None, None)
    assert service.list_scannable_instruments() == ["us:ZZAR"]
    assert len(service.list_versions(theses[0].thesis_id)) == 1


def test_nfc_equivalent_update_is_noop_but_stale_version_conflicts(
    service: PortfolioService, db: Database
) -> None:
    first = service.create_thesis("us:ZZAR", "é\nMargin", "Floor")
    same = service.update_thesis(first.thesis_id, " e\u0301\r\nMargin ", " Floor ", 1)
    assert same == first
    service.update_thesis(first.thesis_id, "Second", None, 1)
    with pytest.raises(UserError) as caught:
        service.update_thesis(first.thesis_id, "Second", None, 1)
    assert caught.value.code == "CONFLICT"
    assert query(db, "SELECT count(*) FROM thesis_version") == [(2,)]


@pytest.mark.parametrize("operation", ["list", "update", "versions"])
def test_missing_current_version_surfaces_internal_error(
    service: PortfolioService, db: Database, operation: str
) -> None:
    from sentinel.errors import InternalError

    first = service.create_thesis("us:ZZAR", "First", None)
    with db.write() as tx:
        tx.execute("UPDATE thesis SET current_version = 2 WHERE thesis_id = ?", [first.thesis_id])
    with pytest.raises(InternalError):
        if operation == "update":
            service.update_thesis(first.thesis_id, "Second", None, 2)
        elif operation == "versions":
            service.list_versions(first.thesis_id)
        else:
            service.list_theses()
    assert query(db, "SELECT count(*) FROM thesis_version") == [(1,)]


def test_version_snapshots_never_change_across_edits_and_archive(
    service: PortfolioService, db: Database
) -> None:
    first = service.create_thesis("us:ZZAR", " First ", " Floor ")
    original = query(db, "SELECT * FROM thesis_version")
    service.update_thesis(first.thesis_id, "Second", None, 1)
    service.update_thesis(first.thesis_id, "Third", "New floor", 2)
    service.archive_thesis(first.thesis_id)
    assert query(db, "SELECT * FROM thesis_version WHERE version = 1") == original
    versions = service.list_versions(first.thesis_id)
    assert [item.version for item in versions] == [3, 2, 1]
    assert versions[-1].statement == "First" and versions[-1].kill_condition == "Floor"


def test_two_concurrent_upserts_share_one_holding_identity(
    service: PortfolioService, db: Database
) -> None:
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier

    barrier = Barrier(2)

    def upsert(quantity):
        barrier.wait(timeout=5)
        return service.upsert_holding("us:ZZAR", Decimal(quantity), None, None).holding_id

    with ThreadPoolExecutor(max_workers=2) as pool:
        identities = list(pool.map(upsert, ("1", "2")))
    assert identities[0] == identities[1]
    assert query(db, "SELECT count(*) FROM holding") == [(1,)]


@pytest.mark.parametrize("mutation", ["holding", "thesis"])
def test_inactive_instruments_are_rejected(
    service: PortfolioService, db: Database, mutation: str
) -> None:
    with db.write() as tx:
        tx.execute("UPDATE instrument SET is_active = FALSE WHERE instrument_id = 'us:ZZAR'")
    with pytest.raises(UserError) as caught:
        if mutation == "holding":
            service.upsert_holding("us:ZZAR", Decimal("1"), None, None)
        else:
            service.create_thesis("us:ZZAR", "First", None)
    assert caught.value.code == "NOT_FOUND"
    assert query(db, "SELECT count(*) FROM holding") == [(0,)]
    assert query(db, "SELECT count(*) FROM thesis") == [(0,)]
