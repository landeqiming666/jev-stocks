from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date

from sentinel.errors import ErrorCode, SentinelError, UserError
from sentinel.messages import INTERNAL_FALLBACK, render


def known_retry_after(value: object) -> int | float | None:
    if type(value) is int and value >= 0:
        return value
    if type(value) is float and math.isfinite(value) and value >= 0:
        return value
    return None


@dataclass(frozen=True)
class Bar:
    trade_date: date
    open: float | None
    high: float | None
    low: float | None
    close: float | None
    adj_close: float | None
    volume: int | None


@dataclass(frozen=True)
class RefreshFailure:
    instrument_id: str
    code: str
    reason: str
    retry_after_sec: int | float | None = None

    def to_wire(self) -> dict[str, object]:
        code = ErrorCode(self.code)
        if code == ErrorCode.INTERNAL:
            message = INTERNAL_FALLBACK
        elif code == ErrorCode.RATE_LIMITED:
            wait = known_retry_after(self.retry_after_sec)
            message = (
                render("error.RATE_LIMITED", {"retryAfterSec": wait})
                if wait is not None
                else render("prices.rate_limited")
            )
        else:
            message = render(f"error.{code}")
        return {
            "instrumentId": self.instrument_id,
            "error": {"code": code.value, "message": message},
        }

    @classmethod
    def from_error(cls, instrument_id: str, error: SentinelError) -> RefreshFailure:
        return cls(
            instrument_id,
            error.code.value,
            error.reason or error.code.value,
            known_retry_after(error.params.get("retryAfterSec")),
        )


@dataclass(frozen=True)
class RefreshResult:
    updated: int
    failed: list[RefreshFailure]
    as_of: date

    def to_wire(self) -> dict[str, object]:
        return {
            "updated": self.updated,
            "failed": [failure.to_wire() for failure in self.failed],
            "asOf": self.as_of.isoformat(),
        }


@dataclass(frozen=True)
class RefreshParams:
    instrument_ids: Sequence[str] | None = None

    def __post_init__(self) -> None:
        ids = self.instrument_ids
        if ids is not None:
            if (
                isinstance(ids, (str, bytes))
                or not isinstance(ids, Sequence)
                or any(not isinstance(item, str) or not item for item in ids)
            ):
                raise UserError("INVALID_ARGUMENT", field="instrumentIds")
            object.__setattr__(self, "instrument_ids", tuple(ids))

    @classmethod
    def from_wire(cls, params: Mapping[str, object]) -> RefreshParams:
        if set(params) - {"instrumentIds"}:
            raise UserError("INVALID_ARGUMENT", field="instrumentIds")
        if "instrumentIds" not in params:
            return cls()
        ids = params["instrumentIds"]
        if not isinstance(ids, list) or any(not isinstance(item, str) or not item for item in ids):
            raise UserError("INVALID_ARGUMENT", field="instrumentIds")
        return cls(ids)

    def to_wire(self) -> dict[str, object]:
        return {} if self.instrument_ids is None else {"instrumentIds": list(self.instrument_ids)}
