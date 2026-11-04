from __future__ import annotations

import logging
from collections.abc import Iterator
from contextlib import contextmanager
from decimal import Decimal
from typing import cast

import duckdb
from pydantic import ValidationError

from sentinel import clock, ids
from sentinel.errors import InternalError, UserError
from sentinel.logging_setup import get_logger, log_event
from sentinel.storage import Database

from .models import HoldingView, ThesisStatus, ThesisVersionView, ThesisView
from .repository import PortfolioRepository
from .validation import (
    content_hash,
    validate_id,
    validate_quantity,
    validate_text,
    validate_version,
)

MAX_ACTIVE_THESES = 5


@contextmanager
def _database_errors() -> Iterator[None]:
    try:
        yield
    except (duckdb.Error, ValidationError) as exc:
        log_event(
            get_logger(__name__),
            logging.ERROR,
            event="portfolio.database.failed",
            error_code="INTERNAL",
            detail=type(exc).__name__,
        )
        raise InternalError(detail="portfolio database operation failed") from exc


class PortfolioService:
    def __init__(self, db: Database) -> None:
        self._db = db
        self._repo = PortfolioRepository()

    def list_holdings(self) -> list[HoldingView]:
        with _database_errors(), self._db.read() as tx:
            return self._repo.list_holdings(tx)

    def count_holdings(self) -> int:
        with _database_errors(), self._db.read() as tx:
            tx.execute("SELECT count(*) FROM holding WHERE archived_at IS NULL")
            row = tx.fetchone()
            assert row is not None
            return cast(int, row[0])

    def list_scannable_instruments(self) -> list[str]:
        with _database_errors(), self._db.read() as tx:
            tx.execute(
                "SELECT DISTINCT h.instrument_id FROM holding h JOIN thesis t "
                "ON t.instrument_id = h.instrument_id AND t.status = 'active' "
                "WHERE h.archived_at IS NULL ORDER BY h.instrument_id"
            )
            return [cast(str, row[0]) for row in tx.fetchall()]

    def list_active_theses(self, instrument_id: str) -> list[ThesisView]:
        return self.list_theses(instrument_id, "active")

    def upsert_holding(
        self, instrument_id: str, quantity: Decimal, avg_cost: Decimal | None, note: str | None
    ) -> HoldingView:
        instrument_id = validate_id(instrument_id, "instrumentId")
        quantity = validate_quantity(quantity)
        avg_cost = None if avg_cost is None else validate_quantity(avg_cost, "avgCost")
        if quantity == 0 and avg_cost is not None:
            raise UserError("INVALID_ARGUMENT", field="avgCost")
        note = validate_text(note, "note", 200)
        with _database_errors(), self._db.write() as tx:
            instrument = self._repo.get_instrument(tx, instrument_id)
            if instrument is None or not instrument.is_active or instrument.market != "us":
                raise UserError("NOT_FOUND", field="instrumentId")
            holding = self._repo.get_holding(tx, instrument_id)
            moment = clock.now()
            if holding is None:
                tx.execute(
                    "INSERT INTO holding VALUES (?, ?, ?, ?, ?, ?, ?, NULL)",
                    [ids.new_id(), instrument_id, quantity, avg_cost, note, moment, moment],
                )
            else:
                tx.execute(
                    "UPDATE holding SET quantity = ?, avg_cost = ?, note = ?, updated_at = ?, "
                    "archived_at = NULL WHERE instrument_id = ?",
                    [quantity, avg_cost, note, moment, instrument_id],
                )
            return self._repo.list_holdings(tx, instrument_id)[0]

    def archive_holding(self, instrument_id: str) -> None:
        instrument_id = validate_id(instrument_id, "instrumentId")
        with _database_errors(), self._db.write() as tx:
            row = self._repo.get_holding(tx, instrument_id)
            if row is None:
                raise UserError("NOT_FOUND", field="instrumentId")
            if row.archived_at is None:
                moment = clock.now()
                tx.execute(
                    "UPDATE holding SET archived_at = ?, updated_at = ? WHERE instrument_id = ?",
                    [moment, moment, instrument_id],
                )

    def list_theses(
        self, instrument_id: str | None = None, status: ThesisStatus | None = None
    ) -> list[ThesisView]:
        if instrument_id is not None:
            instrument_id = validate_id(instrument_id, "instrumentId")
        if status is not None and status not in ("active", "archived"):
            raise UserError("INVALID_ARGUMENT", field="status")
        with _database_errors(), self._db.read() as tx:
            return self._repo.list_theses(tx, instrument_id, status)

    def create_thesis(
        self, instrument_id: str, statement: str, kill_condition: str | None
    ) -> ThesisView:
        instrument_id = validate_id(instrument_id, "instrumentId")
        statement = cast(str, validate_text(statement, "statement", 500, required=True))
        kill_condition = validate_text(kill_condition, "killCondition", 300)
        with _database_errors(), self._db.write() as tx:
            instrument = self._repo.get_instrument(tx, instrument_id)
            if instrument is None or not instrument.is_active or instrument.market != "us":
                raise UserError("NOT_FOUND", field="instrumentId")
            if self._repo.count_active(tx, instrument_id) >= MAX_ACTIVE_THESES:
                raise UserError(
                    "INVALID_ARGUMENT", field="instrumentId", params={"max": MAX_ACTIVE_THESES}
                )
            thesis_id, moment = ids.new_id(), clock.now()
            tx.execute(
                "INSERT INTO thesis VALUES (?, ?, 'active', 1, ?, ?, NULL)",
                [thesis_id, instrument_id, moment, moment],
            )
            self._repo.insert_version(
                tx,
                thesis_id,
                1,
                statement,
                kill_condition,
                content_hash(statement, kill_condition),
                moment,
            )
            return self._repo.thesis_view(tx, thesis_id)

    def update_thesis(
        self, thesis_id: str, statement: str, kill_condition: str | None, expected_version: int
    ) -> ThesisView:
        thesis_id = validate_id(thesis_id, "thesisId")
        statement = cast(str, validate_text(statement, "statement", 500, required=True))
        kill_condition = validate_text(kill_condition, "killCondition", 300)
        expected_version = validate_version(expected_version)
        digest = content_hash(statement, kill_condition)
        with _database_errors(), self._db.write() as tx:
            thesis = self._repo.get_thesis(tx, thesis_id)
            if thesis is None or thesis.status != "active":
                raise UserError("NOT_FOUND", field="thesisId")
            if thesis.current_version != expected_version:
                raise UserError("CONFLICT", params={"currentVersion": thesis.current_version})
            if self._repo.current_hash(tx, thesis) == digest:
                return self._repo.thesis_view(tx, thesis_id)
            next_version, moment = expected_version + 1, clock.now()
            self._repo.insert_version(
                tx, thesis_id, next_version, statement, kill_condition, digest, moment
            )
            tx.execute(
                "UPDATE thesis SET current_version = ?, updated_at = ? "
                "WHERE thesis_id = ? AND current_version = ? RETURNING current_version",
                [next_version, moment, thesis_id, expected_version],
            )
            if tx.fetchone() is None:
                current = self._repo.get_thesis(tx, thesis_id)
                raise UserError(
                    "CONFLICT",
                    params={
                        "currentVersion": current.current_version if current else expected_version
                    },
                )
            return self._repo.thesis_view(tx, thesis_id)

    def archive_thesis(self, thesis_id: str) -> None:
        thesis_id = validate_id(thesis_id, "thesisId")
        with _database_errors(), self._db.write() as tx:
            thesis = self._repo.get_thesis(tx, thesis_id)
            if thesis is None:
                raise UserError("NOT_FOUND", field="thesisId")
            if thesis.status != "archived":
                moment = clock.now()
                tx.execute(
                    "UPDATE thesis SET status = 'archived', archived_at = ?, updated_at = ? "
                    "WHERE thesis_id = ?",
                    [moment, moment, thesis_id],
                )

    def list_versions(self, thesis_id: str) -> list[ThesisVersionView]:
        thesis_id = validate_id(thesis_id, "thesisId")
        with _database_errors(), self._db.read() as tx:
            thesis = self._repo.get_thesis(tx, thesis_id)
            if thesis is None:
                raise UserError("NOT_FOUND", field="thesisId")
            versions = self._repo.list_versions(tx, thesis_id)
            if len(versions) != thesis.current_version or any(
                item.version != len(versions) - index for index, item in enumerate(versions)
            ):
                raise InternalError(detail="thesis version history is incomplete")
            return versions
