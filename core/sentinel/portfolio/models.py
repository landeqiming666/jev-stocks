from __future__ import annotations

from collections.abc import Mapping
from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Literal, Self

from pydantic import (
    AfterValidator,
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    ModelWrapValidatorHandler,
    PlainSerializer,
    ValidationError,
    ValidationInfo,
    field_validator,
    model_validator,
)
from pydantic.alias_generators import to_camel

from sentinel.clock import parse_iso
from sentinel.errors import UserError

from .validation import computed_decimal4, parse_amount, validate_id, validate_text

ThesisStatus = Literal["active", "archived"]
Relation = Literal["none", "support", "weaken", "overturn", "uncertain"]
Count = Annotated[int, Field(ge=0)]
Version = Annotated[int, Field(ge=1)]
Identifier = Annotated[str, Field(min_length=1)]
InputAmount = Annotated[Decimal, BeforeValidator(parse_amount)]
Amount = Annotated[
    Decimal,
    BeforeValidator(lambda value: parse_amount(value, output=True)),
    PlainSerializer(lambda value: format(value, ".4f"), return_type=str),
]

ComputedAmount = Annotated[
    Decimal,
    BeforeValidator(computed_decimal4),
    PlainSerializer(lambda value: format(value, ".4f"), return_type=str),
]


def _iso(value: str) -> str:
    parse_iso(value)
    if not value.endswith("Z"):
        raise ValueError("timestamp requires UTC Z suffix")
    return value


IsoTime = Annotated[
    str,
    Field(pattern=r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(?:\.[0-9]+)?Z$"),
    AfterValidator(_iso),
]


def _iso_date(value: str) -> str:
    if date.fromisoformat(value).isoformat() != value:
        raise ValueError("date must be canonical ISO date")
    return value


IsoDate = Annotated[str, Field(pattern=r"^[0-9]{4}-[0-9]{2}-[0-9]{2}$"), AfterValidator(_iso_date)]


class WireModel(BaseModel):
    model_config = ConfigDict(
        strict=True,
        extra="forbid",
        frozen=True,
        revalidate_instances="always",
        alias_generator=to_camel,
        validate_by_alias=True,
        validate_by_name=True,
    )


class ParamsModel(WireModel):
    @model_validator(mode="wrap")
    @classmethod
    def arguments(cls, values: object, handler: ModelWrapValidatorHandler[Self]) -> Self:
        try:
            result = handler(values)
        except ValidationError as exc:
            error = exc.errors()[0]
            parts = error["loc"]
            field = ".".join(
                cls.model_fields[part].alias or part
                if part in cls.model_fields and error["type"] != "extra_forbidden"
                else str(part)
                for part in parts
            )
            raise UserError("INVALID_ARGUMENT", field=field) from None
        return result

    @field_validator("instrument_id", "thesis_id", check_fields=False)
    @classmethod
    def identifiers(cls, value: str) -> str:
        return validate_id(
            value, "instrumentId" if "instrument_id" in cls.model_fields else "thesisId"
        )

    @field_validator("statement", "kill_condition", "note", mode="before", check_fields=False)
    @classmethod
    def texts(cls, value: str | None, info: ValidationInfo) -> str | None:
        name = info.field_name
        field, maximum = {
            "statement": ("statement", 500),
            "kill_condition": ("killCondition", 300),
            "note": ("note", 200),
        }[name or ""]
        return validate_text(value, field, maximum, required=name == "statement")


class EmptyParams(ParamsModel):
    pass


class HoldingIdParams(ParamsModel):
    instrument_id: Identifier


class ThesisIdParams(ParamsModel):
    thesis_id: Identifier


class HoldingUpsertParams(HoldingIdParams):
    quantity: InputAmount
    avg_cost: InputAmount | None = None
    note: Annotated[str, Field(max_length=200)] | None = None

    @model_validator(mode="after")
    def watchlist_cost(self) -> Self:
        if self.quantity == 0 and self.avg_cost is not None:
            raise UserError("INVALID_ARGUMENT", field="avgCost")
        return self


class ThesisListParams(ParamsModel):
    instrument_id: Identifier | None = None
    status: ThesisStatus | None = None

    @model_validator(mode="before")
    @classmethod
    def reject_explicit_null(cls, values: object) -> object:
        if isinstance(values, Mapping):
            for name, value in values.items():
                if value is None:
                    raise UserError("INVALID_ARGUMENT", field=str(name))
        return values


class ThesisCreateParams(HoldingIdParams):
    statement: str
    kill_condition: str | None = None


class ThesisUpdateParams(ThesisIdParams):
    statement: str
    kill_condition: str | None = None
    expected_version: Version


class InstrumentView(WireModel):
    instrument_id: Identifier
    market: Literal["us", "cn", "hk"]
    symbol: Identifier
    name: str
    name_zh: str | None
    exchange: str
    currency: Literal["USD", "CNY", "HKD"]
    is_active: bool


class HoldingView(WireModel):
    holding_id: Identifier
    instrument: InstrumentView
    quantity: Amount
    avg_cost: Amount | None
    note: Annotated[str, Field(max_length=200)] | None
    last_close: Annotated[float, Field(ge=0, allow_inf_nan=False)] | None
    last_close_date: IsoDate | None
    day_change_pct: Annotated[float, Field(allow_inf_nan=False)] | None
    market_value: ComputedAmount | None
    thesis_count: Count
    pending_count: Count
    uncertain_count: Count
    status: Literal["guarded", "attention", "unguarded"]


class LastDecision(WireModel):
    decision_id: Identifier
    relation: Relation
    headline: Annotated[float, Field(ge=0, le=1, allow_inf_nan=False)]
    created_at: IsoTime
    event_title: str


class ThesisVersionView(WireModel):
    version: Version
    statement: Annotated[str, Field(min_length=1, max_length=500, pattern=r"\S")]
    kill_condition: Annotated[str, Field(max_length=300)] | None
    created_at: IsoTime


class ThesisView(ThesisVersionView):
    thesis_id: Identifier
    instrument_id: Identifier
    version_count: Version
    status: ThesisStatus
    updated_at: IsoTime
    last_decision: LastDecision | None


class HoldingsListResult(WireModel):
    items: list[HoldingView]
    as_of: IsoTime


class ThesisListResult(WireModel):
    items: list[ThesisView]


class ThesisVersionsResult(WireModel):
    items: list[ThesisVersionView]


class OkResult(WireModel):
    ok: Literal[True]

    @field_validator("ok", mode="before")
    @classmethod
    def true_boolean(cls, value: object) -> object:
        if value is not True:
            raise ValueError("ok requires true boolean")
        return value


class HoldingRow(BaseModel):
    model_config = ConfigDict(strict=True, frozen=True)
    holding_id: str
    instrument_id: str
    quantity: Decimal
    avg_cost: Decimal | None
    note: str | None
    created_at: datetime
    updated_at: datetime
    archived_at: datetime | None


class ThesisRow(BaseModel):
    model_config = ConfigDict(strict=True, frozen=True)
    thesis_id: str
    instrument_id: str
    status: ThesisStatus
    current_version: Version
    created_at: datetime
    updated_at: datetime
    archived_at: datetime | None
