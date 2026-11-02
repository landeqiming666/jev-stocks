"""规则加载是唯一文件读取入口；下单与预估使用不可变显式输入。"""

from __future__ import annotations

import tomllib
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation, localcontext
from hashlib import sha256
from pathlib import Path
from types import MappingProxyType
from typing import Literal

from sentinel.errors import InternalError, UserError

from .fees import (
    BPS_DENOMINATOR,
    FeeBreakdown,
    FeeConfig,
    _decimal_context,
    _require_decimal,
    _require_int,
    calculate_fees,
)

MONEY_QUANTUM = Decimal("0.0001")
PRICE_QUANTUM = Decimal("0.000001")
DEFAULT_SLIPPAGE_BPS = Decimal("5")
Side = Literal["buy", "sell"]


@dataclass(frozen=True)
class MarketRules:
    market: str = "us"
    currency: str = "USD"
    slippage_bps: Decimal = DEFAULT_SLIPPAGE_BPS
    commission_per_share: Decimal = Decimal("0")
    commission_min: Decimal = Decimal("0")
    commission_max_pct: Decimal = Decimal("0")
    sec_fee_per_million: Decimal = Decimal("0")
    sec_effective_from: str = ""
    sec_source: str = ""
    sec_verified: bool = False  # TODO-VERIFY(P-04)
    taf_per_share: Decimal = Decimal("0")
    taf_max_per_trade: Decimal = Decimal("0")
    taf_effective_from: str = ""
    taf_source: str = ""
    taf_verified: bool = False  # TODO-VERIFY(P-04)
    max_order_quantity: int = 1000000
    max_pending_orders: int = 50
    max_wait_trading_days: int = 5

    def __post_init__(self) -> None:
        if not isinstance(self.market, str) or self.market != "us":
            raise InternalError(field="market", detail="only us is supported")
        if not isinstance(self.currency, str) or self.currency != "USD":
            raise InternalError(field="currency", detail="only USD is supported")
        try:
            _require_decimal(self.slippage_bps, "slippage_bps")
            if self.slippage_bps >= BPS_DENOMINATOR:
                raise UserError("INVALID_ARGUMENT", field="slippage_bps")
            for field in ("max_order_quantity", "max_pending_orders", "max_wait_trading_days"):
                _require_int(getattr(self, field), field, minimum=1)
        except UserError as exc:
            raise InternalError(field=exc.field, detail="invalid market configuration") from exc
        FeeConfig.from_rules(self)

    @property
    def fee_config(self) -> FeeConfig:
        return FeeConfig.from_rules(self)


def load_market_rules(path: Path) -> MarketRules:
    if not isinstance(path, Path):
        raise InternalError(field="path", detail="market rules require a Path")
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, tomllib.TOMLDecodeError) as exc:
        raise InternalError(detail="market rules are unreadable or malformed") from exc

    def table(parent: Mapping[str, object], key: str) -> Mapping[str, object]:
        value = parent.get(key)
        if not isinstance(value, dict):
            raise InternalError(field=key, detail="missing configuration table")
        return value

    def value(parent: Mapping[str, object], key: str, kind: type) -> object:
        result = parent.get(key)
        if type(result) is not kind:
            raise InternalError(field=key, detail="missing or invalid configuration value")
        return result

    def text(parent: Mapping[str, object], key: str) -> str:
        return str(value(parent, key, str))

    def number(parent: Mapping[str, object], key: str) -> Decimal:
        raw = parent.get(key)
        # TOML 的小数必须加引号；整数可无损转换，bool 不属于整数。
        if type(raw) not in (str, int):
            raise InternalError(
                field=key, detail="decimal configuration requires string or integer"
            )
        try:
            result = Decimal(str(raw))
            _require_decimal(result, key)
        except (InvalidOperation, UserError) as exc:
            raise InternalError(field=key, detail="invalid decimal configuration") from exc
        return result

    def integer(parent: Mapping[str, object], key: str) -> int:
        result = value(parent, key, int)
        assert isinstance(result, int)
        return result

    def boolean(parent: Mapping[str, object], key: str) -> bool:
        result = value(parent, key, bool)
        assert isinstance(result, bool)
        return result

    meta, costs, limits = table(data, "meta"), table(data, "costs"), table(data, "limits")
    sec, taf = table(costs, "sec_fee"), table(costs, "finra_taf")
    return MarketRules(
        market=text(meta, "market"),
        currency=text(meta, "currency"),
        slippage_bps=number(costs, "slippage_bps"),
        commission_per_share=number(costs, "commission_per_share"),
        commission_min=number(costs, "commission_min"),
        commission_max_pct=number(costs, "commission_max_pct"),
        sec_fee_per_million=number(sec, "usd_per_million"),
        sec_effective_from=text(sec, "effective_from"),
        sec_source=text(sec, "source"),
        sec_verified=boolean(sec, "verified"),
        taf_per_share=number(taf, "usd_per_share"),
        taf_max_per_trade=number(taf, "max_per_trade"),
        taf_effective_from=text(taf, "effective_from"),
        taf_source=text(taf, "source"),
        taf_verified=boolean(taf, "verified"),
        max_order_quantity=integer(limits, "max_order_quantity"),
        max_pending_orders=integer(limits, "max_pending_orders"),
        max_wait_trading_days=integer(limits, "max_wait_trading_days"),
    )


@dataclass(frozen=True)
class OrderIntent:
    account_id: str
    instrument_id: str
    side: Side
    quantity: int
    order_type: str
    idempotency_key: str


@dataclass(frozen=True)
class MarketSnapshot:
    clock_date: date
    close: Decimal | None
    max_order_quantity: int


@dataclass(frozen=True)
class Reject:
    code: str
    message_key: str
    data: Mapping[str, object]

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "data", MappingProxyType({**self.data, "reason": self.code, "retryable": False})
        )


@dataclass(frozen=True)
class BuyEstimate:
    price: Decimal
    amount: Decimal
    fee: Decimal
    required: Decimal
    fees: FeeBreakdown


@dataclass(frozen=True)
class PrecheckResult:
    estimate: BuyEstimate | None = None
    reject: Reject | None = None


def _require_text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip() or "|" in value:
        raise UserError("INVALID_ARGUMENT", field=field)
    return value


def _validate_intent(intent: OrderIntent) -> None:
    if not isinstance(intent, OrderIntent):
        raise UserError("INVALID_ARGUMENT", field="intent")
    _require_text(intent.account_id, "accountId")
    instrument = _require_text(intent.instrument_id, "instrumentId")
    if not instrument.startswith("us:") or len(instrument) <= 3:
        raise UserError("INVALID_ARGUMENT", field="instrumentId")
    if not isinstance(intent.side, str) or intent.side not in ("buy", "sell"):
        raise UserError("INVALID_ARGUMENT", field="side")
    if not isinstance(intent.order_type, str) or intent.order_type != "market_open":
        raise UserError(
            "INVALID_ARGUMENT", field="orderType", detail="only market_open is supported"
        )
    _require_int(intent.quantity, "quantity", minimum=1)
    if not isinstance(intent.idempotency_key, str) or not intent.idempotency_key.strip():
        raise UserError("INVALID_ARGUMENT", field="idempotencyKey")
    if len(intent.idempotency_key) > 64:
        raise UserError("INVALID_ARGUMENT", field="idempotencyKey")


def validate_parameters(intent: OrderIntent, pending_count: int, rules: MarketRules) -> None:
    _validate_intent(intent)
    if not isinstance(rules, MarketRules):
        raise UserError("INVALID_ARGUMENT", field="rules")
    _require_int(intent.quantity, "quantity", minimum=1, maximum=rules.max_order_quantity)
    _require_int(pending_count, "pending_count")
    if pending_count >= rules.max_pending_orders:
        raise UserError("INVALID_ARGUMENT", field="pending_count")


def _slipped_price(price: Decimal, side: Side, rules: MarketRules, *, field: str) -> Decimal:
    with localcontext(_decimal_context(price, rules.slippage_bps)):
        slip = rules.slippage_bps / BPS_DENOMINATOR
        factor = 1 + slip if side == "buy" else 1 - slip
        result = (price * factor).quantize(PRICE_QUANTUM)
        if result <= 0:
            raise UserError("INVALID_ARGUMENT", field=field, detail="price rounds to zero")
        return result


def estimate_buy(close: Decimal, quantity: int, rules: MarketRules) -> BuyEstimate:
    if not isinstance(rules, MarketRules):
        raise UserError("INVALID_ARGUMENT", field="rules")
    _require_decimal(close, "close", positive=True)
    _require_int(quantity, "quantity", minimum=1, maximum=rules.max_order_quantity)
    price = _slipped_price(close, "buy", rules, field="close")
    with localcontext(_decimal_context(price, Decimal(quantity))):
        amount = (price * quantity).quantize(MONEY_QUANTUM)
    fees = calculate_fees("buy", quantity, amount, rules.fee_config)
    with localcontext(_decimal_context(amount, fees.total)):
        fee = fees.total.quantize(MONEY_QUANTUM)
        return BuyEstimate(price, amount, fee, (amount + fee).quantize(MONEY_QUANTUM), fees)


def precheck(
    intent: OrderIntent,
    snapshot: MarketSnapshot,
    available_cash: Decimal,
    held: int,
    pending_sell: int,
    rules: MarketRules,
) -> PrecheckResult:
    validate_parameters(intent, 0, rules)
    if not isinstance(snapshot, MarketSnapshot):
        raise UserError("INVALID_ARGUMENT", field="snapshot")
    if type(snapshot.clock_date) is not date:
        raise UserError("INVALID_ARGUMENT", field="clockDate")
    _require_int(snapshot.max_order_quantity, "maxOrderQuantity", minimum=1)
    _require_int(intent.quantity, "quantity", minimum=1, maximum=snapshot.max_order_quantity)
    _require_decimal(available_cash, "available_cash", quantum=MONEY_QUANTUM)
    _require_int(held, "held")
    _require_int(pending_sell, "pending_sell")
    if snapshot.close is not None:
        _require_decimal(snapshot.close, "close")
    if snapshot.close is None or snapshot.close == 0:
        return PrecheckResult(
            reject=Reject("NO_PRICE", "trading.no_price", {"date": snapshot.clock_date.isoformat()})
        )
    if intent.side == "buy":
        estimate = estimate_buy(snapshot.close, intent.quantity, rules)
        if available_cash < estimate.required:
            return PrecheckResult(
                reject=Reject(
                    "INSUFFICIENT_CASH",
                    "trading.insufficient_cash",
                    {
                        "required": str(estimate.required),
                        "available": format(available_cash, ".4f"),
                    },
                )
            )
        return PrecheckResult(estimate=estimate)
    sellable = held - pending_sell
    if sellable < intent.quantity:
        return PrecheckResult(
            reject=Reject(
                "INSUFFICIENT_POSITION",
                "trading.insufficient_position",
                {
                    "held": held,
                    "requested": intent.quantity,
                    "pendingSell": pending_sell,
                    "sellable": sellable,
                },
            )
        )
    return PrecheckResult()


def request_hash(account_id: str, intent: OrderIntent) -> str:
    _require_text(account_id, "accountId")
    _validate_intent(intent)
    if account_id != intent.account_id:
        raise UserError("INVALID_ARGUMENT", field="accountId")
    payload = (
        f"{account_id}|{intent.instrument_id}|{intent.side}|{intent.quantity}|{intent.order_type}"
    )
    return sha256(payload.encode("utf-8")).hexdigest()
