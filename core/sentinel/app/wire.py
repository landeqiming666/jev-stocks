"""组合根自有 RPC 线上模型：只覆盖 C-07 负责注册的 markets 两个方法。"""

from __future__ import annotations

from datetime import date

from pydantic import Field

from sentinel.markets.instruments.normalize import DEFAULT_LIMIT, MAX_LIMIT
from sentinel.settings.models import WireModel


class SearchParamsWire(WireModel):
    query: str = Field(min_length=1, max_length=120)
    limit: int = Field(default=DEFAULT_LIMIT, ge=1, le=MAX_LIMIT)


class InstrumentWire(WireModel):
    instrument_id: str
    market: str
    symbol: str
    name: str
    name_zh: str | None
    exchange: str
    currency: str
    is_active: bool


class SearchResultWire(WireModel):
    items: list[InstrumentWire]


class RefreshParamsWire(WireModel):
    instrument_ids: list[str] | None = None


class ErrorWire(WireModel):
    code: str
    message: str


class RefreshFailureWire(WireModel):
    instrument_id: str
    error: ErrorWire


class RefreshResultWire(WireModel):
    updated: int = Field(ge=0)
    failed: list[RefreshFailureWire]
    as_of: date


__all__ = [
    "ErrorWire",
    "InstrumentWire",
    "RefreshFailureWire",
    "RefreshParamsWire",
    "RefreshResultWire",
    "SearchParamsWire",
    "SearchResultWire",
]
