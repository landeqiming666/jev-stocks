from __future__ import annotations

import json
from typing import cast

from sentinel.demo import DemoService
from sentinel.demo.loader import SCHEMA, pk_json
from sentinel.storage import Database


def query(db: Database, sql: str, params: list[object] | None = None) -> list[tuple[object, ...]]:
    with db.read() as reader:
        reader.execute(sql, params)
        return reader.fetchall()


def test_demo_rows_cover_every_inserted_table(service: DemoService, db: Database) -> None:
    service.load()
    registered = {
        cast(str, row[0]): cast(int, row[1])
        for row in query(db, "SELECT table_name, count(*) FROM demo_row GROUP BY table_name")
    }
    expected = {
        table: cast(int, query(db, f"SELECT count(*) FROM {table}")[0][0]) for table, *_ in SCHEMA
    }
    assert registered | {"setting": 1} == expected | {"setting": 1}
    assert registered["setting"] == 1
    assert {table: count for table, count in registered.items() if table != "setting"} == expected
    assert sum(registered.values()) == 1651


def test_registered_keys_match_declared_primary_keys(service: DemoService, db: Database) -> None:
    service.load()
    for table, _columns, keys, _json_keys in SCHEMA:
        rows = query(db, "SELECT pk_json FROM demo_row WHERE table_name=?", [table])
        assert len(rows) == cast(int, query(db, f"SELECT count(*) FROM {table}")[0][0])
        for (raw,) in rows:
            values = json.loads(cast(str, raw))
            assert set(values) == set(keys)
            assert pk_json(values) == raw
            clauses = " AND ".join(f"{key}=?" for key in keys)
            assert query(
                db,
                f"SELECT count(*) FROM {table} WHERE {clauses}",
                [values[key] for key in keys],
            ) == [(1,)]
