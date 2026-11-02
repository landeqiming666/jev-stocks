"""费用与撮合只消费显式快照，账本事务由 P-05 负责。"""

from __future__ import annotations

from dataclasses import dataclass
from dataclasses import field as dataclass_field
from datetime import date
from decimal import ROUND_HALF_UP, ROUND_UP, Context, Decimal, localcontext
from typing import TYPE_CHECKING, Literal

from sentinel.errors import InternalError, UserError

if TYPE_CHECKING:
    from .rules import MarketRules, OrderIntent, Reject, Side

CENT_QUANTUM = Decimal("0.01")
BPS_DENOMINATOR = Decimal("10000")
SEC_MILLION = Decimal("1000000")


def _require_decimal(
    value: object, field: str, *, positive: bool = False, quantum: Decimal | None = None
) -> Decimal:
    if not isinstance(value, Decimal) or not value.is_finite():
        raise UserError("INVALID_ARGUMENT", field=field)
    if value < 0 or (positive and value == 0):
        raise UserError("INVALID_ARGUMENT", field=field)
    if quantum is not None:
        with localcontext(_decimal_context(value)):
            if value != value.quantize(quantum):
                raise UserError("INVALID_ARGUMENT", field=field)
    return value


def _require_int(value: object, field: str, *, minimum: int = 0, maximum: int | None = None) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise UserError("INVALID_ARGUMENT", field=field)
    if maximum is not None and value > maximum:
        raise UserError("INVALID_ARGUMENT", field=field)
    return value


def _decimal_context(*values: Decimal) -> Context:
    # 独立 context 避免调用方改变精度、舍入或 trap 后影响账本结果。
    precision = 32
    for value in values:
        parts = value.as_tuple()
        assert isinstance(parts.exponent, int)
        precision += len(parts.digits) + abs(parts.exponent)
    return Context(prec=precision, rounding=ROUND_HALF_UP)


@dataclass(frozen=True)
class FeeConfig:
    commission_per_share: Decimal = Decimal("0")
    commission_min: Decimal = Decimal("0")
    commission_max_pct: Decimal = Decimal("0")
    sec_fee_per_million: Decimal = Decimal("0")
    taf_per_share: Decimal = Decimal("0")
    taf_max_per_trade: Decimal = Decimal("0")
    sec_effective_from: str = ""
    sec_source: str = ""
    sec_verified: bool = False
    taf_effective_from: str = ""
    taf_source: str = ""
    taf_verified: bool = False
    max_order_quantity: int = 1000000

    def __post_init__(self) -> None:
        for field in (
            "commission_per_share",
            "commission_min",
            "commission_max_pct",
            "sec_fee_per_million",
            "taf_per_share",
            "taf_max_per_trade",
        ):
            try:
                _require_decimal(getattr(self, field), field)
            except UserError as exc:
                raise InternalError(field=field, detail="invalid fee configuration") from exc
        if self.commission_max_pct > 100:
            raise InternalError(field="commission_max_pct", detail="percentage exceeds 100")
        if self.taf_per_share > 0 and self.taf_max_per_trade <= 0:
            raise InternalError(field="taf_max_per_trade", detail="positive TAF requires a cap")
        for field in ("commission_min", "taf_max_per_trade"):
            value: Decimal = getattr(self, field)
            with localcontext(_decimal_context(value)):
                if value != value.quantize(CENT_QUANTUM):
                    raise InternalError(field=field, detail="fee minimum and cap require cents")
        try:
            _require_int(self.max_order_quantity, "max_order_quantity", minimum=1)
        except UserError as exc:
            raise InternalError(
                field="max_order_quantity", detail="invalid quantity limit"
            ) from exc
        for prefix in ("sec", "taf"):
            effective: object = getattr(self, f"{prefix}_effective_from")
            source: object = getattr(self, f"{prefix}_source")
            verified: object = getattr(self, f"{prefix}_verified")
            if not isinstance(effective, str) or not isinstance(source, str):
                raise InternalError(field=prefix, detail="fee metadata must be strings")
            if type(verified) is not bool:
                raise InternalError(field=f"{prefix}_verified", detail="verified must be boolean")
            if effective:
                try:
                    parsed = date.fromisoformat(effective)
                except ValueError as exc:
                    raise InternalError(field=f"{prefix}_effective_from") from exc
                if parsed.isoformat() != effective:
                    raise InternalError(field=f"{prefix}_effective_from")
            if verified and (not effective or not source.strip()):
                raise InternalError(field=prefix, detail="verified fees require date and source")

    @classmethod
    def from_rules(cls, rules: MarketRules) -> FeeConfig:
        return cls(**{field: getattr(rules, field) for field in cls.__dataclass_fields__})


@dataclass(frozen=True)
class FeeBreakdown:
    commission: Decimal
    sec: Decimal
    taf: Decimal
    total: Decimal = dataclass_field(init=False)

    def __post_init__(self) -> None:
        for name in ("commission", "sec", "taf"):
            value = _require_decimal(getattr(self, name), name, quantum=CENT_QUANTUM)
            with localcontext(_decimal_context(value)):
                object.__setattr__(self, name, value.quantize(CENT_QUANTUM))
        with localcontext(_decimal_context(self.commission, self.sec, self.taf)):
            object.__setattr__(
                self, "total", (self.commission + self.sec + self.taf).quantize(CENT_QUANTUM)
            )


def calculate_fees(side: Side, quantity: int, amount: Decimal, cfg: FeeConfig) -> FeeBreakdown:
    if not isinstance(side, str) or side not in ("buy", "sell"):
        raise UserError("INVALID_ARGUMENT", field="side")
    if not isinstance(cfg, FeeConfig):
        raise UserError("INVALID_ARGUMENT", field="cfg")
    _require_int(quantity, "quantity", minimum=1, maximum=cfg.max_order_quantity)
    _require_decimal(amount, "amount", quantum=Decimal("0.0001"))
    with localcontext(
        _decimal_context(
            amount,
            Decimal(quantity),
            cfg.commission_per_share,
            cfg.commission_min,
            cfg.commission_max_pct,
            cfg.sec_fee_per_million,
            cfg.taf_per_share,
            cfg.taf_max_per_trade,
        )
    ):
        commission = max(
            cfg.commission_min, (quantity * cfg.commission_per_share).quantize(CENT_QUANTUM)
        )
        if cfg.commission_max_pct > 0:
            cap = (amount * cfg.commission_max_pct / 100).quantize(CENT_QUANTUM)
            commission = min(commission, cap)
        commission = commission.quantize(CENT_QUANTUM)
        if side == "buy":
            return FeeBreakdown(commission, Decimal("0.00"), Decimal("0.00"))
        sec = (amount / SEC_MILLION * cfg.sec_fee_per_million).quantize(
            CENT_QUANTUM, rounding=ROUND_UP
        )
        taf = min(
            cfg.taf_max_per_trade,
            (quantity * cfg.taf_per_share).quantize(CENT_QUANTUM, rounding=ROUND_UP),
        )
        return FeeBreakdown(commission, sec, taf.quantize(CENT_QUANTUM))


@dataclass(frozen=True)
class MatchResult:
    kind: Literal["filled", "rejected", "pending"]
    price: Decimal | None = None
    amount: Decimal | None = None
    fee: Decimal | None = None
    fees: FeeBreakdown | None = None
    reject: Reject | None = None
    waited_days: int = 0

    @property
    def reject_code(self) -> str | None:
        return self.reject.code if self.reject is not None else None


def match_at_open(
    intent: OrderIntent,
    open_price: Decimal | None,
    waited_days: int,
    reserved_cash: Decimal,
    available_cash_after_release: Decimal,
    held: int,
    rules: MarketRules,
) -> MatchResult:
    # 普通局部导入解除规则预估与费用撮合的相互引用。
    from .rules import MONEY_QUANTUM, Reject, _slipped_price, validate_parameters

    validate_parameters(intent, 0, rules)
    _require_int(waited_days, "waited_days")
    _require_int(held, "held")
    _require_decimal(reserved_cash, "reserved_cash", quantum=MONEY_QUANTUM)
    _require_decimal(
        available_cash_after_release, "available_cash_after_release", quantum=MONEY_QUANTUM
    )
    if open_price is not None:
        _require_decimal(open_price, "open_price")
    if open_price is None or open_price == 0:
        days = waited_days + 1
        if days >= rules.max_wait_trading_days:
            reject = Reject("NO_PRICE_AT_FILL", "trading.no_price_at_fill", {"n": days})
            return MatchResult("rejected", reject=reject, waited_days=days)
        return MatchResult("pending", waited_days=days)
    price = _slipped_price(open_price, intent.side, rules, field="open_price")
    with localcontext(_decimal_context(price, Decimal(intent.quantity))):
        amount = (price * intent.quantity).quantize(MONEY_QUANTUM)
    fees = calculate_fees(intent.side, intent.quantity, amount, FeeConfig.from_rules(rules))
    with localcontext(_decimal_context(amount, fees.total, available_cash_after_release)):
        fee = fees.total.quantize(MONEY_QUANTUM)
        required = amount + fee
        if intent.side == "buy" and available_cash_after_release < required:
            reject = Reject(
                "INSUFFICIENT_CASH_AT_FILL",
                "trading.insufficient_cash_at_fill",
                {
                    "required": str(required),
                    "available": format(available_cash_after_release, ".4f"),
                },
            )
            return MatchResult("rejected", reject=reject, waited_days=waited_days)
        if intent.side == "sell" and held < intent.quantity:
            reject = Reject(
                "INSUFFICIENT_POSITION_AT_FILL",
                "trading.insufficient_position_at_fill",
                {"held": held, "requested": intent.quantity},
            )
            return MatchResult("rejected", reject=reject, waited_days=waited_days)
        return MatchResult("filled", price, amount, fee, fees, waited_days=waited_days)
