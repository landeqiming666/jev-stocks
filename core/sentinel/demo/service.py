"""Load and clear the deterministic demo data set inside single transactions."""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Literal, cast

import duckdb
from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel

from sentinel.errors import InternalError, UserError
from sentinel.logging_setup import get_logger, log_event
from sentinel.storage import Database, SqlExecutor

from .loader import (
    EXPECTED_COUNTS,
    delete_registered,
    insert_all,
    read_resources,
    registry_count,
    residual_rows,
    residual_tables,
)

LOGGER = get_logger(__name__)
DEMO_SYMBOLS = ("ZZAR", "ZZFD", "ZZCL", "ZZBK", "ZZEN", "ZZMD")


class DemoCounts(BaseModel):
    model_config = ConfigDict(
        strict=True,
        extra="forbid",
        frozen=True,
        alias_generator=to_camel,
        validate_by_alias=True,
        validate_by_name=True,
        serialize_by_alias=True,
    )

    instruments: int
    holdings: int
    theses: int
    events: int
    decisions: int
    prices: int


class DemoStatus(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)

    loaded: bool
    rows: int


class DemoLoadResult(BaseModel):
    model_config = ConfigDict(
        strict=True,
        extra="forbid",
        frozen=True,
        alias_generator=to_camel,
        validate_by_alias=True,
        validate_by_name=True,
        serialize_by_alias=True,
    )

    loaded: Literal[True] = True
    counts: DemoCounts


def _loaded(tx: SqlExecutor) -> bool:
    tx.execute("SELECT value_json FROM setting WHERE key='demoDataLoaded'")
    row = tx.fetchone()
    if row is not None:
        try:
            if json.loads(cast(str, row[0])) is True:
                return True
        except (TypeError, ValueError) as exc:
            raise InternalError(detail="demo: invalid loaded flag") from exc
    return registry_count(tx) > 0


def _refuse_real_data(tx: SqlExecutor) -> None:
    tx.execute(
        "SELECT (SELECT count(*) FROM holding), (SELECT count(*) FROM thesis), "
        "(SELECT count(*) FROM paper_account)"
    )
    row = tx.fetchone()
    if row is None:
        raise InternalError(detail="demo: conflict query")
    if any(cast(int, value) for value in row):
        raise UserError("CONFLICT", reason="REAL_DATA_PRESENT")
    placeholders = ",".join("?" for _ in DEMO_SYMBOLS)
    tx.execute(
        f"SELECT count(*) FROM instrument "
        f"WHERE symbol IN ({placeholders}) OR instrument_id LIKE 'us:ZZ%'",
        list(DEMO_SYMBOLS),
    )
    conflict = tx.fetchone()
    if conflict is None or cast(int, conflict[0]):
        raise UserError("CONFLICT", reason="REAL_DATA_PRESENT")


def _counts(tx: SqlExecutor) -> DemoCounts:
    tx.execute(
        "SELECT (SELECT count(*) FROM instrument WHERE source='demo'), "
        "(SELECT count(*) FROM holding), "
        "(SELECT count(*) FROM thesis), "
        "(SELECT count(*) FROM event_doc WHERE source='demo'), "
        "(SELECT count(*) FROM decision), "
        "(SELECT count(*) FROM price_daily WHERE source='demo')"
    )
    row = tx.fetchone()
    if row is None:
        raise InternalError(detail="demo: count query")
    values = [cast(int, value) for value in row]
    names = ("instruments", "holdings", "theses", "events", "decisions", "prices")
    return DemoCounts(**dict(zip(names, values, strict=True)))


def _verify(counts: DemoCounts) -> None:
    actual = counts.model_dump()
    if actual != EXPECTED_COUNTS:
        raise InternalError(detail=f"demo: counts {actual} != {EXPECTED_COUNTS}")


class DemoService:
    def __init__(self, db: Database, resources: Path, clock: Callable[[], datetime]) -> None:
        self._db = db
        self._clock = clock
        self._data = read_resources(resources)

    def load(self) -> DemoCounts:
        try:
            with self._db.write() as tx:
                if _loaded(tx):
                    raise UserError("CONFLICT", reason="ALREADY_LOADED")
                _refuse_real_data(tx)
                insert_all(tx, self._data, self._clock())
                counts = _counts(tx)
                _verify(counts)
                return counts
        except duckdb.Error as exc:
            log_event(
                LOGGER,
                logging.ERROR,
                event="demo.load.failed",
                error_code="INTERNAL",
                detail=type(exc).__name__,
            )
            raise InternalError(detail="demo: load failed") from exc

    def clear(self) -> None:
        try:
            with self._db.write() as tx:
                removed = delete_registered(tx, self._clock())
                residual = residual_rows(tx)
                if residual:
                    names = residual_tables(tx)
                    log_event(
                        LOGGER,
                        logging.ERROR,
                        event="demo.clear.residual",
                        error_code="INTERNAL",
                        detail=",".join(names),
                    )
                    raise InternalError(detail=f"demo: residual rows {residual}")
                log_event(
                    LOGGER,
                    logging.INFO,
                    event="demo.clear.done",
                    detail=str(removed),
                )
        except duckdb.Error as exc:
            raise InternalError(detail="demo: clear failed") from exc

    def status(self) -> DemoStatus:
        try:
            with self._db.read() as tx:
                return DemoStatus(loaded=_loaded(tx), rows=registry_count(tx))
        except duckdb.Error as exc:
            raise InternalError(detail="demo: status failed") from exc


def load_demo(db: Database, resources: Path, clock: Callable[[], datetime]) -> DemoCounts:
    return DemoService(db, resources, clock).load()


def clear_demo(db: Database, clock: Callable[[], datetime]) -> None:
    try:
        with db.write() as tx:
            removed = delete_registered(tx, clock())
            residual = residual_rows(tx)
            if residual:
                names = residual_tables(tx)
                log_event(
                    LOGGER,
                    logging.ERROR,
                    event="demo.clear.residual",
                    error_code="INTERNAL",
                    detail=",".join(names),
                )
                raise InternalError(detail=f"demo: residual rows {residual}")
            log_event(
                LOGGER,
                logging.INFO,
                event="demo.clear.done",
                detail=str(removed),
            )
    except duckdb.Error as exc:
        raise InternalError(detail="demo: clear failed") from exc
