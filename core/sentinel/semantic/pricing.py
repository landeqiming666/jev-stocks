import re
import tomllib
from decimal import ROUND_HALF_UP, Context, Decimal, InvalidOperation, localcontext
from pathlib import Path

from .base import validate_count

PriceTable = dict[str, Decimal]
DEFAULT_PRICING_PATH = Path(__file__).resolve().parents[3] / "resources" / "pricing.toml"
_MODEL_ID = re.compile(r"jev-(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)")
_DECIMAL_TEXT = re.compile(r"[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?")


def load_price_table(path: Path = DEFAULT_PRICING_PATH) -> PriceTable:
    with path.open("rb") as stream:
        models = tomllib.load(stream).get("models")
    if not isinstance(models, dict) or not models:
        raise ValueError("pricing models must be a nonempty table")
    table: PriceTable = {}
    for model, row in models.items():
        if not isinstance(model, str) or _MODEL_ID.fullmatch(model) is None:
            raise ValueError("pricing model ID must be a pinned Jev version")
        if not isinstance(row, dict):
            raise ValueError("pricing model row must be a table")
        text = row.get("input_usd_per_mtok")
        if not isinstance(text, str) or _DECIMAL_TEXT.fullmatch(text) is None:
            raise ValueError("price must be Decimal text")
        try:
            price = Decimal(text)
        except InvalidOperation as exc:
            raise ValueError("invalid Decimal price text") from exc
        _validate_price(price)
        table[model] = price
    return table


def _validate_price(price: Decimal) -> None:
    if not isinstance(price, Decimal) or not price.is_finite() or price < 0:
        raise ValueError("price must be a nonnegative finite Decimal")


def cost_usd(input_tokens: int, model_id: str, table: PriceTable | None = None) -> Decimal:
    validate_count(input_tokens)
    prices = load_price_table() if table is None else table
    if model_id not in prices:
        raise ValueError("unknown price model")
    price = prices[model_id]
    _validate_price(price)
    # 新建 context，隔离调用方的 precision、rounding、traps 与 flags。
    tokens = Decimal(input_tokens)
    precision = len(tokens.as_tuple().digits) + len(price.as_tuple().digits)
    precision += max(price.adjusted(), 0) + 16
    with localcontext(Context(prec=precision, rounding=ROUND_HALF_UP)):
        return (tokens * price / Decimal(1_000_000)).quantize(Decimal("0.000001"))
