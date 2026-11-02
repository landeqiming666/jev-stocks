import duckdb
import pytest

from sentinel.storage import Database, check_integrity

VIOLATIONS = {
    "orphan_thesis_version": (
        "INSERT INTO thesis_version VALUES ('missing', 1, 'Synthetic', NULL, 'hash', '2026-11-02')"
    ),
    "thesis_version_gap": "UPDATE thesis SET current_version=2",
    "orphan_decision_thesis": "UPDATE decision SET thesis_version=2",
    "orphan_decision_passage": "UPDATE decision SET passage_id='missing'",
    "orphan_passage": "UPDATE event_passage SET event_id='missing'",
    "evidence_out_of_range": "UPDATE decision SET evidence_start=-1",
    "orphan_action": "UPDATE thesis_action SET decision_id='missing'",
    "batch_run_missing": "UPDATE scan_batch SET run_id='missing'",
    "order_account_missing": "UPDATE paper_order SET account_id='missing' WHERE order_id='o'",
    "fill_without_order": "UPDATE fill SET order_id='missing'",
    "filled_order_without_fill": "DELETE FROM fill",
    "position_mismatch": "UPDATE position SET quantity=3",
    "negative_position": "UPDATE position SET quantity=-1",
    "negative_cash": "UPDATE cash_ledger SET amount=-1 WHERE entry_type='deposit'",
    "reserved_mismatch": "UPDATE cash_ledger SET amount=-6 WHERE entry_type='reserve'",
    "equity_mismatch": "UPDATE equity_snapshot SET equity=121",
}


@pytest.mark.parametrize("rule,sql", VIOLATIONS.items())
def test_each_integrity_rule_has_a_violation_case(
    business_db: Database, rule: str, sql: str
) -> None:
    assert check_integrity(business_db) == []
    with business_db.write() as tx:
        tx.execute(sql)
    errors = check_integrity(business_db)
    assert len([error for error in errors if error.startswith(rule + ":")]) == 1
    assert errors == sorted(errors)
    assert any(any("\u4e00" <= character <= "\u9fff" for character in error) for error in errors)


def test_orphan_thesis_version_is_reported(business_db: Database) -> None:
    with business_db.write() as tx:
        tx.execute(VIOLATIONS["orphan_thesis_version"])
    assert any(error.startswith("orphan_thesis_version:") for error in check_integrity(business_db))


def test_clean_database_has_no_integrity_errors(business_db: Database) -> None:
    assert check_integrity(business_db) == []


def test_core_only_database_skips_uncreated_business_tables(db: Database) -> None:
    assert check_integrity(db) == []
    db.migrate()
    assert check_integrity(db) == []


def test_partial_table_sets_run_only_applicable_rules(db: Database) -> None:
    with db.write() as tx:
        tx.execute(
            "CREATE TABLE position (account_id VARCHAR, instrument_id VARCHAR, quantity INTEGER)"
        )
        tx.execute("INSERT INTO position VALUES ('acct', 'us:ZZAA', -1)")
    assert len(check_integrity(db)) == 1
    assert check_integrity(db)[0].startswith("negative_position:")


def test_partial_schema_does_not_swallow_sql_errors(db: Database) -> None:
    with db.write() as tx:
        tx.execute("CREATE TABLE position (account_id VARCHAR, instrument_id VARCHAR)")
    with pytest.raises(duckdb.Error):
        check_integrity(db)


@pytest.mark.parametrize(
    "update",
    [
        "evidence_start=NULL",
        "evidence_end=NULL",
        "evidence_start=3, evidence_end=3",
        "evidence_end=8",
        "evidence_start=-1",
    ],
)
def test_evidence_unicode_codepoint_bounds(business_db: Database, update: str) -> None:
    with business_db.write() as tx:
        tx.execute("UPDATE decision SET " + update)
    assert any(error.startswith("evidence_out_of_range:") for error in check_integrity(business_db))


@pytest.mark.parametrize(
    "sql",
    [
        "DELETE FROM position",
        "UPDATE paper_order SET side='sell' WHERE order_id='o'",
        "UPDATE fill SET quantity=1",
    ],
)
def test_position_reconciles_missing_rows_and_sells(business_db: Database, sql: str) -> None:
    with business_db.write() as tx:
        tx.execute(sql)
    assert any(error.startswith("position_mismatch:") for error in check_integrity(business_db))


@pytest.mark.parametrize(
    "sql",
    [
        "DELETE FROM thesis_version",
        "UPDATE thesis_version SET version=2; UPDATE thesis SET current_version=2",
        "INSERT INTO thesis_version SELECT thesis_id, 3, statement, kill_condition, "
        "content_hash, created_at FROM thesis_version; UPDATE thesis SET current_version=3",
    ],
)
def test_thesis_versions_start_at_one_and_are_contiguous(business_db: Database, sql: str) -> None:
    with business_db.write() as tx:
        tx.execute(sql)
    assert any(error.startswith("thesis_version_gap:") for error in check_integrity(business_db))


def test_reserved_sql_matches_authoritative_balance_query(business_db: Database) -> None:
    with business_db.read() as reader:
        assert reader.execute(
            """
            SELECT COALESCE(SUM(CASE WHEN entry_type IN ('deposit','buy','sell','fee')
                       THEN amount END), 0),
                   COALESCE(-SUM(CASE WHEN entry_type IN ('reserve','release') THEN amount END), 0)
            FROM cash_ledger WHERE account_id = ?
        """,
            ["acct"],
        ).fetchone() == (100, 5)
    with business_db.write() as tx:
        tx.execute(
            "INSERT INTO cash_ledger VALUES "
            "('release', 'acct', '2026-11-02', 'release', 5, 'pending', '2026-11-02')"
        )
        tx.execute(
            "UPDATE paper_order SET status='cancelled', reserved_cash=NULL WHERE order_id='pending'"
        )
    assert check_integrity(business_db) == []


def test_duckdb_indexed_update_and_delete_reinsert_limits() -> None:
    with duckdb.connect() as raw:
        raw.execute(
            "CREATE TABLE parent(id INTEGER PRIMARY KEY, code VARCHAR UNIQUE); "
            "INSERT INTO parent VALUES (1,'a'),(2,'b')"
        )
        raw.execute(
            "BEGIN; DELETE FROM parent WHERE id=1; INSERT INTO parent VALUES(1,'a'); COMMIT"
        )
        assert raw.execute("SELECT * FROM parent ORDER BY id").fetchall() == [(1, "a"), (2, "b")]
        raw.execute("CREATE TABLE large (id INTEGER PRIMARY KEY)")
        raw.execute("INSERT INTO large SELECT range FROM range(2049)")
        with pytest.raises(duckdb.ConstraintException, match="2048"):
            raw.execute("UPDATE large SET id=id+1")
        raw.execute(
            "CREATE TABLE child(id INTEGER REFERENCES parent(id)); INSERT INTO child VALUES(1)"
        )
        with pytest.raises(duckdb.ConstraintException):
            raw.execute("UPDATE parent SET id=3 WHERE id=1")
        raw.execute("BEGIN")
        with pytest.raises(duckdb.ConstraintException):
            raw.execute("DELETE FROM parent WHERE id=1")
        raw.execute("ROLLBACK")
