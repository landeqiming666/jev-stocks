from __future__ import annotations

import hashlib
import re
import unicodedata
from decimal import ROUND_HALF_UP, Context, Decimal, InvalidOperation, localcontext

from sentinel.errors import UserError

MAX_STATEMENT_CODEPOINTS = 500
MAX_KILL_CONDITION_CODEPOINTS = 300
MAX_NOTE_CODEPOINTS = 200
QUANTITY_QUANTUM = Decimal("0.0001")
MAX_AMOUNT = Decimal("99999999999999.9999")
INPUT_AMOUNT_PATTERN = r"(?:0|[1-9][0-9]{0,13})(?:\.[0-9]{1,4})?"
OUTPUT_AMOUNT_PATTERN = r"(?:0|[1-9][0-9]{0,13})\.[0-9]{4}"
MONEY_CONTEXT = Context(prec=360, rounding=ROUND_HALF_UP)


def decimal4(value: Decimal) -> Decimal:
    if not isinstance(value, Decimal) or not value.is_finite() or not 0 <= value <= MAX_AMOUNT:
        raise ValueError("amount must be finite and within DECIMAL(18,4)")
    try:
        with localcontext(MONEY_CONTEXT):
            quantized = value.quantize(QUANTITY_QUANTUM)
            if value != quantized:
                raise ValueError("amount must have at most four decimal places")
            return quantized.copy_abs() if quantized == 0 else quantized
    except InvalidOperation as exc:
        raise ValueError("invalid amount") from exc


def parse_amount(value: object, *, output: bool = False) -> Decimal:
    if isinstance(value, str):
        pattern = OUTPUT_AMOUNT_PATTERN if output else INPUT_AMOUNT_PATTERN
        if re.fullmatch(pattern, value) is None:
            raise ValueError("invalid decimal string")
        value = Decimal(value)
    if not isinstance(value, Decimal):
        raise ValueError("amount requires a decimal string or internal Decimal")
    return decimal4(value)


def validate_quantity(value: Decimal, field: str = "quantity") -> Decimal:
    try:
        return decimal4(value)
    except ValueError:
        raise UserError("INVALID_ARGUMENT", field=field) from None


def market_value(quantity: Decimal, close: float) -> Decimal:
    with localcontext(MONEY_CONTEXT):
        result = (quantity * Decimal(str(close))).quantize(QUANTITY_QUANTUM)
    return computed_decimal4(result)


def computed_decimal4(value: object) -> Decimal:
    if isinstance(value, str):
        if re.fullmatch(r"(?:0|[1-9][0-9]*)\.[0-9]{4}", value) is None:
            raise ValueError("invalid computed decimal string")
        value = Decimal(value)
    if not isinstance(value, Decimal) or not value.is_finite() or value < 0:
        raise ValueError("computed amount must be finite and nonnegative")
    with localcontext(MONEY_CONTEXT):
        result = value.quantize(QUANTITY_QUANTUM)
    if value != result:
        raise ValueError("computed amount requires four decimal places")
    return result.copy_abs() if result == 0 else result


def validate_id(value: str, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise UserError("INVALID_ARGUMENT", field=field)
    return value.strip()


def validate_text(
    value: str | None, field: str, maximum: int, *, required: bool = False
) -> str | None:
    if value is None and not required:
        return None
    if not isinstance(value, str):
        raise UserError("INVALID_ARGUMENT", field=field)
    value = value.strip()
    if (required and not value) or len(value) > maximum:
        raise UserError(
            "INVALID_ARGUMENT", field=field, params={"length": len(value), "max": maximum}
        )
    try:
        value.encode("utf-8")
    except UnicodeEncodeError:
        raise UserError("INVALID_ARGUMENT", field=field) from None
    return value or None


def validate_version(value: int) -> int:
    if type(value) is not int or value < 1:
        raise UserError("INVALID_ARGUMENT", field="expectedVersion")
    return value


def norm(value: str) -> str:
    return unicodedata.normalize("NFC", value).replace("\r\n", "\n").replace("\r", "\n").strip()


def content_hash(statement: str, kill_condition: str | None) -> str:
    return hashlib.sha256(
        (norm(statement) + "\n---\n" + norm(kill_condition or "")).encode()
    ).hexdigest()
