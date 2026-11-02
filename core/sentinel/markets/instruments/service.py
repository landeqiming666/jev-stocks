"""Refresh policy and search service; JSON-RPC wiring is owned by C-07."""

import logging
from collections.abc import Callable
from datetime import datetime, timedelta

from sentinel.errors import SourceError, UserError
from sentinel.logging_setup import get_logger, log_event

from .models import ImportStats, SearchHit
from .normalize import DEFAULT_LIMIT, MAX_LIMIT
from .repository import InstrumentRepository, _utc
from .source import SecTickerSource

MAX_AGE_DAYS = 7


class InstrumentService:
    def __init__(
        self,
        repo: InstrumentRepository,
        source: SecTickerSource,
        clock: Callable[[], datetime],
    ) -> None:
        self._repo = repo
        self._source = source
        self._clock = clock
        self._logger = get_logger(__name__)

    def search(self, query: str, limit: int = DEFAULT_LIMIT) -> list[SearchHit]:
        return self._repo.search(query, limit=limit)

    def ensure_fresh(self, *, offline: bool, has_sec_email: bool) -> ImportStats | None:
        if offline or not has_sec_email:
            return None
        now = _utc(self._clock())
        last = self._repo.last_refresh_at()
        if (
            not self._repo.is_empty()
            and last is not None
            and now - last <= timedelta(days=MAX_AGE_DAYS)
        ):
            return None
        try:
            rows = self._source.fetch()
        except (SourceError, UserError) as exc:
            if isinstance(exc, UserError) and exc.code != "CONFIG_REQUIRED":
                raise
            log_event(
                self._logger,
                logging.WARNING,
                event="instruments.refresh_failed",
                error_code=exc.code.value,
                reason=exc.reason,
            )
            return None
        if not rows:
            log_event(
                self._logger,
                logging.WARNING,
                event="instruments.refresh_empty",
                error_code="SOURCE_UNAVAILABLE",
                reason="TICKER_EMPTY",
            )
            return None
        return self._repo.replace_from_sec(rows, fetched_at=now)


__all__ = ["DEFAULT_LIMIT", "MAX_LIMIT", "MAX_AGE_DAYS", "InstrumentService"]
