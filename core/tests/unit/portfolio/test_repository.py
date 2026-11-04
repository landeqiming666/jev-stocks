from decimal import Decimal

from sentinel.portfolio import PortfolioService
from sentinel.storage import Database

from .conftest import NOW, add_decision, add_downstream, query


def test_portfolio_unit_fixture_migrates_only_its_owned_prerequisites(db: Database) -> None:
    assert db.schema_version == 3


def test_archive_keeps_versions_and_decisions(service: PortfolioService, db: Database) -> None:
    add_downstream(db)
    first = service.create_thesis("us:ZZAR", "First", None)
    service.update_thesis(first.thesis_id, "Second", None, 1)
    add_decision(db, first.thesis_id, "overturn")
    before = query(db, "SELECT * FROM decision")
    service.archive_thesis(first.thesis_id)
    service.archive_thesis(first.thesis_id)
    assert query(db, "SELECT status, archived_at FROM thesis") == [("archived", NOW)]
    assert len(service.list_versions(first.thesis_id)) == 2
    assert query(db, "SELECT * FROM decision") == before


def test_holding_status_precedence(service: PortfolioService, db: Database) -> None:
    add_downstream(db)
    for symbol in ("ZZAR", "ZZFD", "ZZCL"):
        service.upsert_holding("us:" + symbol, Decimal("1"), None, None)
    attention = service.create_thesis("us:ZZAR", "Pending thesis", None)
    service.create_thesis("us:ZZFD", "Guarded thesis", None)
    add_decision(db, attention.thesis_id, "overturn")
    states = {view.instrument.symbol: view.status for view in service.list_holdings()}
    assert states == {"ZZAR": "attention", "ZZFD": "guarded", "ZZCL": "unguarded"}


def test_holdings_order_puts_positions_before_watchlist(service: PortfolioService) -> None:
    for symbol, quantity in (("ZZFD", "0"), ("ZZCL", "1"), ("ZZAR", "0")):
        service.upsert_holding("us:" + symbol, Decimal(quantity), None, None)
    assert [view.instrument.symbol for view in service.list_holdings()] == ["ZZCL", "ZZAR", "ZZFD"]


def test_003_ddl_is_byte_identical_to_authority() -> None:
    from .conftest import ROOT

    source = (ROOT / "docs" / "04-数据模型.md").read_text()
    ddl = source.split("### 3.3 `", 1)[1].split("```sql\n", 1)[1].split("```", 1)[0]
    actual = (ROOT / "core/sentinel/storage/migrations/003_portfolio.sql").read_bytes()
    assert actual == ddl.encode("utf-8")


def test_missing_downstream_tables_return_null_prices_and_zero_counts(
    service: PortfolioService,
) -> None:
    service.upsert_holding("us:ZZAR", Decimal("5"), None, None)
    service.create_thesis("us:ZZAR", "First", None)
    view = service.list_holdings()[0]
    assert (
        view.last_close is view.last_close_date is view.day_change_pct is view.market_value is None
    )
    assert view.thesis_count == 1 and view.pending_count == view.uncertain_count == 0
    assert view.status == "guarded"
    assert service.list_theses()[0].last_decision is None


def test_price_and_change_use_same_latest_trade_date(
    service: PortfolioService, db: Database
) -> None:
    import pytest

    add_downstream(db, ("3.5",))
    service.upsert_holding("us:ZZAR", Decimal("120"), None, None)
    service.upsert_holding("us:ZZFD", Decimal("0"), None, None)
    with db.write() as tx:
        tx.executemany(
            "INSERT INTO price_daily VALUES (?, ?, NULL, NULL, NULL, ?, ?, 10, 'demo', ?)",
            [
                ["us:ZZAR", "2026-10-28", 10.0, 2.0, NOW],
                ["us:ZZAR", "2026-10-30", 12.0, 9.0, NOW],
                ["us:ZZAR", "2026-10-29", 8.0, 3.0, NOW],
                ["us:ZZFD", "2026-10-29", 5.0, 2.0, NOW],
            ],
        )
    held, watched = service.list_holdings()
    assert held.last_close == 12.0 and held.last_close_date == "2026-10-30"
    assert held.day_change_pct == pytest.approx(0.5)
    assert held.market_value == Decimal("1440.0000")
    assert watched.last_close == 5.0 and watched.day_change_pct is None
    assert watched.market_value == Decimal("0.0000")
    with db.write() as tx:
        tx.execute(
            "INSERT INTO price_daily VALUES ('us:ZZAR', '2026-11-02', "
            "NULL, NULL, NULL, NULL, 11, 1, 'demo', ?)",
            [NOW],
        )
    latest = service.list_holdings()[0]
    assert latest.last_close is latest.market_value is latest.day_change_pct is None
    assert latest.last_close_date == "2026-11-02"


def test_zero_previous_close_yields_null_change(service: PortfolioService, db: Database) -> None:
    add_downstream(db, ("3.5",))
    service.upsert_holding("us:ZZAR", Decimal("1"), None, None)
    with db.write() as tx:
        tx.executemany(
            "INSERT INTO price_daily VALUES ('us:ZZAR', ?, "
            "NULL, NULL, NULL, ?, NULL, 1, 'demo', ?)",
            [["2026-10-29", 0.0, NOW], ["2026-10-30", 12.0, NOW]],
        )
    assert service.list_holdings()[0].day_change_pct is None


def test_computed_market_value_can_exceed_quantity_decimal_bound(
    service: PortfolioService, db: Database
) -> None:
    from decimal import Inexact, Rounded, localcontext

    add_downstream(db, ("3.5",))
    with db.write() as tx:
        tx.execute(
            "INSERT INTO price_daily VALUES ('us:ZZAR', '2026-10-30', "
            "NULL, NULL, NULL, 1000, NULL, 1, 'demo', ?)",
            [NOW],
        )
    with localcontext() as ctx:
        ctx.prec = 2
        ctx.traps[Inexact] = True
        ctx.traps[Rounded] = True
        holding = service.upsert_holding("us:ZZAR", Decimal("99999999999999.9999"), None, None)
        assert holding.market_value == Decimal("99999999999999999.9000")
        assert (
            holding.model_dump(mode="json", by_alias=True)["marketValue"]
            == "99999999999999999.9000"
        )


def test_pending_representative_counts_actions_and_archived_theses(
    service: PortfolioService, db: Database
) -> None:
    add_downstream(db)
    service.upsert_holding("us:ZZAR", Decimal("1"), None, None)
    thesis = service.create_thesis("us:ZZAR", "First", None)
    other = service.create_thesis("us:ZZAR", "Other", None)
    add_decision(db, thesis.thesis_id, "weaken", "weaken", seq=1)
    add_decision(db, thesis.thesis_id, "overturn", "overturn", seq=2)
    add_decision(db, thesis.thesis_id, "overturn", "overturn-first", seq=0)
    add_decision(db, thesis.thesis_id, "uncertain", "uncertain", event_id="us:0009990001-26-000002")
    add_decision(db, thesis.thesis_id, "support", "support", event_id="us:0009990001-26-000003")
    add_decision(db, other.thesis_id, "overturn", "other", event_id="us:0009990001-26-000004")
    service.archive_thesis(other.thesis_id)
    held = service.list_holdings()[0]
    assert held.thesis_count == 1 and held.pending_count == 1 and held.uncertain_count == 1
    with db.write() as tx:
        tx.execute(
            "INSERT INTO thesis_action VALUES ('action-a', 'overturn-first', 'ignore', NULL, ?)",
            [NOW],
        )
    held = service.list_holdings()[0]
    assert held.pending_count == 0 and held.uncertain_count == 1 and held.status == "guarded"
    with db.write() as tx:
        tx.execute(
            "INSERT INTO thesis_action VALUES ('action-z', 'overturn-first', 'reopen', NULL, ?)",
            [NOW],
        )
    assert service.list_holdings()[0].pending_count == 1
    service.archive_thesis(thesis.thesis_id)
    held = service.list_holdings()[0]
    assert held.thesis_count == held.pending_count == held.uncertain_count == 0
    assert held.status == "unguarded"
    assert len(query(db, "SELECT * FROM decision")) == 6
    assert len(query(db, "SELECT * FROM thesis_action")) == 2


def test_decision_without_action_view_counts_zero_and_exposes_last_decision(
    service: PortfolioService, db: Database
) -> None:
    add_downstream(db, ("3.4", "3.6"))
    service.upsert_holding("us:ZZAR", Decimal("1"), None, None)
    first = service.create_thesis("us:ZZAR", "First", None)
    add_decision(db, first.thesis_id, "overturn")
    assert service.list_holdings()[0].pending_count == 0
    assert service.list_theses()[0].last_decision.decision_id == "d1"


def test_latest_decision_survives_edit_and_uses_timestamp_then_id(
    service: PortfolioService, db: Database
) -> None:
    add_downstream(db)
    first = service.create_thesis("us:ZZAR", "First", None)
    add_decision(db, first.thesis_id, "overturn", "d1")
    add_decision(db, first.thesis_id, "support", "d2", event_id="us:0009990001-26-000002")
    changed = service.update_thesis(first.thesis_id, "Second", None, 1)
    assert changed.last_decision.decision_id == "d2"
    with db.write() as tx:
        tx.execute(
            "UPDATE decision SET created_at = ? WHERE decision_id = 'd1'", [NOW.replace(day=3)]
        )
    latest = service.list_theses()[0]
    assert latest.last_decision.decision_id == "d1"
    assert latest.last_decision.event_title == "Synthetic event us:0009990001-26-000001"


def test_sql_errors_are_not_hidden_as_missing_tables(
    service: PortfolioService, db: Database
) -> None:
    import pytest

    from sentinel.errors import InternalError

    service.upsert_holding("us:ZZAR", Decimal("1"), None, None)
    with db.write() as tx:
        tx.execute("CREATE TABLE price_daily (instrument_id VARCHAR, trade_date DATE)")
    with pytest.raises(InternalError):
        service.list_holdings()


def test_archived_holding_preserves_all_theses_versions_decisions_and_actions(
    service: PortfolioService, db: Database
) -> None:
    add_downstream(db)
    service.upsert_holding("us:ZZAR", Decimal("1"), None, None)
    first = service.create_thesis("us:ZZAR", "First", None)
    service.update_thesis(first.thesis_id, "Second", None, 1)
    add_decision(db, first.thesis_id, "overturn")
    with db.write() as tx:
        tx.execute("INSERT INTO thesis_action VALUES ('a1', 'd1', 'ignore', NULL, ?)", [NOW])
    tables = ("thesis", "thesis_version", "decision", "thesis_action")
    before = {table: query(db, f"SELECT * FROM {table}") for table in tables}
    service.archive_holding("us:ZZAR")
    assert service.list_holdings() == [] and service.list_scannable_instruments() == []
    assert {table: query(db, f"SELECT * FROM {table}") for table in tables} == before
