from __future__ import annotations

import re
from collections.abc import Callable
from datetime import date, datetime
from decimal import ROUND_HALF_UP, Context, Decimal, localcontext
from functools import wraps
from typing import Annotated, Literal

from pydantic import (
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    PlainSerializer,
    field_validator,
    model_validator,
)
from pydantic.alias_generators import to_camel

from sentinel import clock
from sentinel.errors import InternalError

from .rules import MONEY_QUANTUM, PRICE_QUANTUM, Side

MAX_MONEY = Decimal("99999999999999.9999")
MAX_PRICE = Decimal("999999999999.999999")
MAX_POSITION_QUANTITY = 2_147_483_647
Status = Literal["pending", "filled", "rejected", "cancelled"]
RejectCode = Literal[
    "NO_PRICE",
    "INSUFFICIENT_CASH",
    "INSUFFICIENT_POSITION",
    "NO_PRICE_AT_FILL",
    "INSUFFICIENT_CASH_AT_FILL",
    "INSUFFICIENT_POSITION_AT_FILL",
]


def isolated_decimal[**P, T](fn: Callable[P, T]) -> Callable[P, T]:
    @wraps(fn)
    def call(*args: P.args, **kwargs: P.kwargs) -> T:
        # 不继承调用方的精度、舍入、trap 或 flags；覆盖 18 位存储和 38 位 SUM。
        with localcontext(Context(prec=80, rounding=ROUND_HALF_UP)):
            return fn(*args, **kwargs)

    return call


@isolated_decimal
def money(value: Decimal) -> Decimal:
    if not isinstance(value, Decimal) or not value.is_finite():
        raise InternalError(reason="INVALID_MONEY")
    result = value.quantize(MONEY_QUANTUM)
    if abs(result) > MAX_MONEY:
        raise InternalError(reason="MONEY_OVERFLOW")
    return result


@isolated_decimal
def price(value: Decimal) -> Decimal:
    if not isinstance(value, Decimal) or not value.is_finite() or value < 0:
        raise InternalError(reason="INVALID_PRICE")
    result = value.quantize(PRICE_QUANTUM)
    if result > MAX_PRICE:
        raise InternalError(reason="PRICE_OVERFLOW")
    return result


def _decimal4(value: object) -> Decimal:
    if isinstance(value, str) and re.fullmatch(r"-?(?:0|[1-9][0-9]*)\.[0-9]{4}", value):
        value = Decimal(value)
    if not isinstance(value, Decimal) or not value.is_finite():
        raise ValueError("requires decimal money")
    with localcontext(Context(prec=80, rounding=ROUND_HALF_UP)):
        if abs(value) > MAX_MONEY or value != value.quantize(MONEY_QUANTUM):
            raise ValueError("money exceeds precision or storage")
    return value


def _decimal6(value: object) -> Decimal:
    if isinstance(value, str) and re.fullmatch(r"(?:0|[1-9][0-9]*)\.[0-9]{6}", value):
        value = Decimal(value)
    if not isinstance(value, Decimal) or not value.is_finite() or value < 0:
        raise ValueError("requires decimal price")
    with localcontext(Context(prec=80, rounding=ROUND_HALF_UP)):
        if value > MAX_PRICE or value != value.quantize(PRICE_QUANTUM):
            raise ValueError("price exceeds precision or storage")
    return value


def parse_initial_cash(value: object) -> Decimal:
    if not isinstance(value, str) or not re.fullmatch(
        r"(?:0|[1-9][0-9]{0,13})(?:\.[0-9]{1,4})?", value
    ):
        raise ValueError("initialCash requires a decimal string")
    result = Decimal(value)
    if result <= 0 or result > MAX_MONEY:
        raise ValueError("initialCash must be positive and fit DECIMAL(18,4)")
    return result


def parse_date(value: object) -> date:
    if type(value) is date:
        return value
    if not isinstance(value, str) or not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", value):
        raise ValueError("requires canonical date")
    return date.fromisoformat(value)


def parse_time(value: object) -> datetime:
    if isinstance(value, datetime):
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("requires timezone")
        return value
    if not isinstance(value, str) or not value.endswith("Z"):
        raise ValueError("requires UTC Z time")
    return clock.parse_iso(value)


Amount = Annotated[
    Decimal,
    BeforeValidator(_decimal4),
    PlainSerializer(lambda v: format(v, ".4f"), return_type=str),
]
NonnegativeAmount = Annotated[Amount, Field(ge=0)]
Price = Annotated[
    Decimal,
    BeforeValidator(_decimal6),
    PlainSerializer(lambda v: format(v, ".6f"), return_type=str),
]
Day = Annotated[date, BeforeValidator(parse_date)]
Moment = Annotated[
    datetime, BeforeValidator(parse_time), PlainSerializer(clock.to_iso, return_type=str)
]
Identifier = Annotated[str, Field(min_length=1)]
Count = Annotated[int, Field(ge=0)]


class WireModel(BaseModel):
    model_config = ConfigDict(
        strict=True,
        extra="forbid",
        frozen=True,
        revalidate_instances="always",
        alias_generator=to_camel,
        validate_by_alias=True,
        validate_by_name=True,
        allow_inf_nan=False,
    )


class ParamsModel(WireModel):
    model_config = ConfigDict(validate_by_name=False)

    @model_validator(mode="before")
    @classmethod
    def no_null(cls, values: object) -> object:
        if isinstance(values, dict) and any(v is None for v in values.values()):
            raise ValueError("optional parameters must be omitted")
        return values


class EmptyParams(ParamsModel):
    pass


class AccountIdParams(ParamsModel):
    account_id: Identifier


class CreateAccountParams(ParamsModel):
    name: Annotated[str, Field(min_length=1, max_length=30, pattern=r"\S")]
    initial_cash: Annotated[Decimal, BeforeValidator(parse_initial_cash)]
    start_date: date

    @field_validator("start_date", mode="before")
    @classmethod
    def json_date(cls, value: object) -> date:
        if not isinstance(value, str):
            raise ValueError("startDate requires a JSON string")
        return parse_date(value)


class PlaceOrderParams(AccountIdParams):
    instrument_id: Identifier
    side: Side
    quantity: Annotated[int, Field(ge=1, le=1_000_000)]
    order_type: Literal["market_open"]
    idempotency_key: Annotated[str, Field(min_length=1, max_length=64)]


class CancelOrderParams(ParamsModel):
    order_id: Identifier


class OrdersParams(AccountIdParams):
    status: Status | None = None
    idempotency_key: Annotated[str, Field(min_length=1, max_length=64)] | None = None
    limit: Annotated[int, Field(ge=1, le=200)] = 50
    cursor: Identifier | None = None


class ResetParams(AccountIdParams):
    confirm_text: str


class InstrumentView(WireModel):
    instrument_id: Identifier
    market: Literal["us", "cn", "hk"]
    symbol: Identifier
    name: str
    name_zh: str | None
    exchange: str
    currency: Literal["USD", "CNY", "HKD"]
    is_active: bool


class PaperAccountView(WireModel):
    account_id: Identifier
    name: Annotated[str, Field(min_length=1, max_length=30, pattern=r"\S")]
    base_currency: Literal["USD"]
    initial_cash: NonnegativeAmount
    start_date: Day
    clock_date: Day
    created_at: Moment


class FillView(WireModel):
    fill_id: Identifier
    filled_on: Day
    price: Price
    quantity: Annotated[int, Field(ge=1)]
    amount: NonnegativeAmount
    fee: NonnegativeAmount


class RejectReason(WireModel):
    code: RejectCode
    message: str


class EstimateView(WireModel):
    price: Price
    amount: NonnegativeAmount
    fee: NonnegativeAmount


class PaperOrderView(WireModel):
    order_id: Identifier
    account_id: Identifier
    instrument: InstrumentView
    side: Side
    quantity: Annotated[int, Field(ge=1)]
    order_type: Literal["market_open"]
    status: Status
    reject_reason: RejectReason | None
    created_clock_date: Day
    reserved_cash: NonnegativeAmount | None
    idempotency_key: Annotated[str, Field(min_length=1, max_length=64)]
    fills: list[FillView]
    estimate: EstimateView | None


class PositionView(WireModel):
    instrument: InstrumentView
    quantity: Count
    sellable_quantity: Count
    avg_cost: Price
    last_close: Annotated[float, Field(ge=0)]
    market_value: NonnegativeAmount
    unrealized_pnl: Amount
    unrealized_pnl_pct: float


class PortfolioView(WireModel):
    account: PaperAccountView
    cash: Amount
    reserved_cash: NonnegativeAmount
    available_cash: Amount
    positions: list[PositionView]
    equity: Amount
    as_of: Day
    pending_orders: Count


class PaperAccountsResult(WireModel):
    items: list[PaperAccountView]


class PaperOrderPage(WireModel):
    items: list[PaperOrderView]
    next_cursor: str | None


class AdvanceResult(WireModel):
    clock_date: Day
    trading_day: Literal[True]
    filled: list[PaperOrderView]
    rejected: list[PaperOrderView]
    pending_remaining: Count
    portfolio: PortfolioView

    @field_validator("trading_day", mode="before")
    @classmethod
    def true_boolean(cls, value: object) -> object:
        if value is not True:
            raise ValueError("tradingDay requires boolean true")
        return value


class OkResult(WireModel):
    ok: Literal[True]

    @field_validator("ok", mode="before")
    @classmethod
    def true_boolean(cls, value: object) -> object:
        if value is not True:
            raise ValueError("ok requires boolean true")
        return value


class OrderRow(BaseModel):
    model_config = ConfigDict(strict=True, frozen=True, extra="forbid")
    order_id: str
    account_id: str
    instrument_id: str
    side: Side
    quantity: int
    order_type: str
    status: Status
    reject_code: RejectCode | None
    reject_message: str | None
    created_clock_date: date
    estimate_price: Decimal | None
    reserved_cash: Decimal | None
    idempotency_key: str
    request_hash: str
    created_at: datetime
    updated_at: datetime


class PositionRow(BaseModel):
    model_config = ConfigDict(strict=True, frozen=True)
    account_id: str
    instrument_id: str
    quantity: int
    avg_cost: Decimal
    updated_at: datetime


class LedgerTotals(WireModel):
    cash: Amount
    reserved: Amount
    available: Amount
