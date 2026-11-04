from __future__ import annotations

import shutil
from datetime import datetime
from pathlib import Path
from typing import cast

import pytest

from sentinel.demo import DemoService, clear_demo, load_demo
from sentinel.demo.loader import SCHEMA
from sentinel.errors import InternalError, UserError
from sentinel.scan.pending import InboxService, StatusSnapshot
from sentinel.storage import Database, SqlExecutor

from .conftest import NOW, RESOURCES

EXPECTED = {
    "instruments": 6,
    "holdings": 5,
    "theses": 6,
    "events": 6,
    "decisions": 12,
    "prices": 1560,
}


def query(db: Database, sql: str, params: list[object] | None = None) -> list[tuple[object, ...]]:
    with db.read() as reader:
        reader.execute(sql, params)
        return reader.fetchall()


def table_counts(db: Database) -> dict[str, int]:
    return {
        entry[0]: cast(int, query(db, f"SELECT count(*) FROM {entry[0]}")[0][0]) for entry in SCHEMA
    }


def status_provider(reader: SqlExecutor, as_of: datetime) -> StatusSnapshot:
    return StatusSnapshot.model_validate(
        {
            "source": {
                "name": "SEC EDGAR",
                "state": "ok",
                "lastSuccessAt": None,
                "message": None,
            },
            "engine": {"active": None, "modelId": "jev-1.14.0", "state": "unconfigured"},
            "offline": True,
        }
    )


def test_load_returns_exact_manifest_counts(service: DemoService) -> None:
    counts = service.load()
    assert counts.model_dump() == EXPECTED
    status = service.status()
    assert status.loaded is True and status.rows > 0


def test_load_is_atomic_on_bad_price_row(db: Database, tmp_path: Path) -> None:
    resources = tmp_path / "bad-price"
    shutil.copytree(RESOURCES, resources)
    prices = resources / "prices.csv"
    lines = prices.read_text(encoding="utf-8").splitlines()
    prices.write_text("\n".join(lines[:-1]) + "\n", encoding="utf-8")
    with pytest.raises(InternalError):
        load_demo(db, resources, lambda: NOW)
    assert all(count == 0 for count in table_counts(db).values())
    assert query(db, "SELECT count(*) FROM demo_row") == [(0,)]
    assert query(db, "SELECT count(*) FROM setting WHERE key='demoDataLoaded'") == [(0,)]


def test_load_is_atomic_on_bad_manifest_count(db: Database, tmp_path: Path) -> None:
    resources = tmp_path / "bad-count"
    shutil.copytree(RESOURCES, resources)
    shutil.copyfile(Path(__file__).with_name("bad_counts.json"), resources / "manifest.json")
    with pytest.raises(InternalError):
        load_demo(db, resources, lambda: NOW)
    assert all(count == 0 for count in table_counts(db).values())
    assert query(db, "SELECT count(*) FROM demo_row") == [(0,)]


def test_load_twice_returns_conflict(service: DemoService) -> None:
    service.load()
    with pytest.raises(UserError) as caught:
        service.load()
    assert caught.value.code.value == "CONFLICT"
    assert caught.value.reason == "ALREADY_LOADED"


def test_load_refuses_real_holding(db: Database) -> None:
    with db.write() as tx:
        tx.execute(
            "INSERT INTO instrument VALUES ('us:REAL', 'us', 'REAL', 'NYSE', 'Real Co', "
            "NULL, 'USD', NULL, TRUE, 'sec_company_tickers', ?)",
            [NOW],
        )
        tx.execute(
            "INSERT INTO holding VALUES ('01K00000000000000000099999', 'us:REAL', 1, 10, "
            "NULL, ?, ?, NULL)",
            [NOW, NOW],
        )
    with pytest.raises(UserError) as caught:
        DemoService(db, RESOURCES, lambda: NOW).load()
    assert caught.value.reason == "REAL_DATA_PRESENT"
    assert query(db, "SELECT count(*) FROM holding") == [(1,)]
    assert query(db, "SELECT count(*) FROM demo_row") == [(0,)]


def test_clear_removes_only_demo_rows(service: DemoService, db: Database) -> None:
    with db.write() as tx:
        tx.execute("INSERT INTO setting VALUES ('language', '\"zh-CN\"', ?)", [NOW])
    service.load()
    service.clear()
    assert all(count == 0 for count in table_counts(db).values())
    assert query(db, "SELECT count(*) FROM demo_row") == [(0,)]
    assert query(db, "SELECT value_json FROM setting WHERE key='language'") == [('"zh-CN"',)]
    assert query(db, "SELECT value_json FROM setting WHERE key='demoDataLoaded'") == [("false",)]
    assert service.status().loaded is False


def test_clear_is_idempotent(db: Database) -> None:
    service = DemoService(db, RESOURCES, lambda: NOW)
    service.load()
    service.clear()
    clear_demo(db, lambda: NOW)
    assert query(db, "SELECT count(*) FROM demo_row") == [(0,)]
    assert query(db, "SELECT value_json FROM setting WHERE key='demoDataLoaded'") == [("false",)]


def test_pending_inbox_has_three_and_one_uncertain(service: DemoService, db: Database) -> None:
    service.load()
    page = InboxService(db, status_provider=status_provider).list_inbox()
    assert page.summary.pending_count == 3
    assert page.summary.overturn_count == 1
    assert page.summary.weaken_count == 1
    assert page.summary.uncertain_count == 1
    assert [(item.instrument.symbol, item.relation, item.headline) for item in page.items] == [
        ("ZZAR", "overturn", 0.93),
        ("ZZCL", "weaken", 0.78),
    ]
    assert [(item.instrument.symbol, item.relation, item.headline) for item in page.uncertain] == [
        ("ZZEN", "uncertain", 0.71),
    ]
    assert page.setup.holdings == 5
    assert page.setup.active_theses == 6
    assert page.last_scan is not None
    assert page.last_scan.run_id == "01K00000000000000000000001"


def test_clear_rolls_back_when_demo_row_reappears(service: DemoService, db: Database) -> None:
    service.load()
    with db.write() as tx:
        tx.execute("DELETE FROM demo_row WHERE table_name='instrument' AND pk_json LIKE '%ZZMD%'")
    with pytest.raises(InternalError):
        service.clear()
    assert query(db, "SELECT count(*) FROM instrument WHERE source='demo'") == [(6,)]
    assert query(db, "SELECT count(*) FROM demo_row") == [(1650,)]


def test_clear_after_manual_delete_skips_missing_rows(service: DemoService, db: Database) -> None:
    service.load()
    with db.write() as tx:
        tx.execute("DELETE FROM price_daily WHERE instrument_id='us:ZZMD'")
    service.clear()
    assert query(db, "SELECT count(*) FROM instrument WHERE source='demo'") == [(0,)]
    assert query(db, "SELECT count(*) FROM demo_row") == [(0,)]
