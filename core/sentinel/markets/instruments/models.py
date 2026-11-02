"""Snake-case domain models with explicit contract serialization for C-07."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from .normalize import DEFAULT_LIMIT, validate_search


@dataclass(frozen=True)
class TickerRow:
    cik: str
    name: str
    ticker: str
    exchange: str


@dataclass(frozen=True)
class Instrument:
    instrument_id: str
    market: str
    symbol: str
    exchange: str
    name: str
    name_zh: str | None
    currency: str
    cik: str | None
    is_active: bool

    def to_wire(self) -> dict[str, object]:
        return {
            "instrumentId": self.instrument_id,
            "market": self.market,
            "symbol": self.symbol,
            "name": self.name,
            "nameZh": self.name_zh,
            "exchange": self.exchange,
            "currency": self.currency,
            "isActive": self.is_active,
        }


@dataclass(frozen=True)
class SearchHit:
    instrument: Instrument
    score: int


@dataclass(frozen=True)
class ImportStats:
    total: int
    kept: int
    skipped_exchange: int
    skipped_symbol: int
    duplicates: int
    deactivated: int


@dataclass(frozen=True)
class SearchParams:
    query: str
    limit: int = DEFAULT_LIMIT

    def __post_init__(self) -> None:
        validate_search(self.query, self.limit)


@dataclass(frozen=True)
class SearchResult:
    items: list[Instrument]

    @classmethod
    def from_hits(cls, hits: Sequence[SearchHit]) -> SearchResult:
        return cls([hit.instrument for hit in hits])

    def to_wire(self) -> dict[str, object]:
        return {"items": [instrument.to_wire() for instrument in self.items]}
