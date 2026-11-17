from __future__ import annotations

import re
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from pydantic.alias_generators import to_camel

from sentinel.clock import parse_iso
from sentinel.domain.contact import is_valid_sec_email
from sentinel.errors import ErrorCode

Count = Annotated[int, Field(ge=0)]
Identifier = Annotated[str, Field(min_length=1)]
IsoTime = Annotated[
    str,
    Field(
        pattern=r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(?:\.[0-9]+)?Z(?![\s\S])"
    ),
]
ScanStatus = Literal[
    "queued", "running", "succeeded", "partial", "failed", "cancelled", "interrupted"
]
BatchStatus = Literal["pending", "succeeded", "failed", "cancelled"]
MODEL_ID: Literal["jev-1.14.0"] = "jev-1.14.0"


class WireModel(BaseModel):
    model_config = ConfigDict(
        strict=True,
        regex_engine="python-re",
        extra="forbid",
        frozen=True,
        revalidate_instances="always",
        alias_generator=to_camel,
        validate_by_alias=True,
        validate_by_name=True,
    )

    @field_validator(
        "window_start",
        "window_end",
        "started_at",
        "finished_at",
        "reset_at",
        "from_",
        check_fields=False,
    )
    @classmethod
    def timestamp(cls, value: str | None) -> str | None:
        if value is not None:
            parse_iso(value)
        return value


class ScanError(WireModel):
    code: str
    message: str

    @field_validator("code")
    @classmethod
    def known_code(cls, value: str) -> str:
        ErrorCode(value)
        return value


class ScanConfiguration(WireModel):
    engine: Literal["auto", "jevdb", "jev_direct"]
    model_id: Literal["jev-1.14.0"]
    sec_contact_email: Annotated[str, Field(max_length=120)] | None
    daily_token_budget: Annotated[int, Field(ge=10_000, le=50_000_000)]
    first_scan_lookback_days: Annotated[int, Field(ge=1, le=30)]

    @field_validator("sec_contact_email")
    @classmethod
    def valid_email(cls, value: str | None) -> str | None:
        if value is not None and not is_valid_sec_email(value):
            raise ValueError("invalid SEC contact email")
        return value


class RunCounters(WireModel):
    instruments: Count
    skipped_no_thesis: Count
    filings: Count
    passages: Count
    decisions: Count
    cached_decisions: Count
    requests: Count
    input_tokens: Count
    est_cost_usd: str
    duration_ms: Count

    @field_validator("est_cost_usd")
    @classmethod
    def amount(cls, value: str) -> str:
        if re.fullmatch(r"[0-9]+\.[0-9]{6}", value) is None:
            raise ValueError("six decimal cost required")
        return value


class BatchSummary(WireModel):
    total: Count
    succeeded: Count
    failed: Count
    pending: Count


class ScanRunView(WireModel):
    run_id: Identifier
    trigger: Literal["manual", "schedule"]
    market: Literal["us", "cn", "hk"]
    status: ScanStatus
    window_start: IsoTime
    window_end: IsoTime
    stats: RunCounters
    engine: Literal["jev_direct", "jevdb"]
    model_id: str
    started_at: IsoTime | None
    finished_at: IsoTime | None
    error: ScanError | None
    batch_summary: BatchSummary


class ScanBatchView(WireModel):
    batch_id: Identifier
    run_id: Identifier
    instrument_id: Identifier
    event_id: Identifier
    event_title: str
    status: BatchStatus
    attempts: Count
    error: ScanError | None
    passages: Count
    decisions: Count
    input_tokens: Count


class ScanBudget(WireModel):
    used_tokens: Count
    limit_tokens: Annotated[int, Field(ge=10_000, le=50_000_000)]
    reset_at: IsoTime


class ScanHistoryPage(WireModel):
    items: list[ScanRunView]
    next_cursor: str | None
    budget: ScanBudget


class ScanDetailView(WireModel):
    run: ScanRunView
    batches: list[ScanBatchView]


class StartParams(WireModel):
    market: Literal["us"]
    from_: IsoTime | None = Field(default=None, alias="from")

    @model_validator(mode="before")
    @classmethod
    def no_null(cls, value: object) -> object:
        if isinstance(value, dict) and "from" in value and value["from"] is None:
            raise ValueError("from cannot be null")
        return value


class RunParams(WireModel):
    run_id: Identifier


class BatchParams(WireModel):
    batch_id: Identifier


class HistoryParams(WireModel):
    limit: Annotated[int, Field(ge=1, le=200)] = 50
    cursor: Identifier | None = None

    @model_validator(mode="before")
    @classmethod
    def no_null(cls, value: object) -> object:
        if isinstance(value, dict) and any(item is None for item in value.values()):
            raise ValueError("history parameters cannot be null")
        return value


class StartResult(WireModel):
    run_id: Identifier


class OkResult(WireModel):
    ok: Literal[True]

    @field_validator("ok", mode="before")
    @classmethod
    def true_bool(cls, value: object) -> object:
        if value is not True:
            raise ValueError("true boolean required")
        return value
