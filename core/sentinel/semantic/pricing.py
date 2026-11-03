import tomllib
from decimal import ROUND_HALF_UP, Context, Decimal, localcontext
from pathlib import Path

from .base import validate_count

PriceTable = dict[str, Decimal]
DEFAULT_PRICING_PATH = Path(__file__).resolve().parents[3] / "resources" / "pricing.toml"


def load_price_table(path: Path = DEFAULT_PRICING_PATH) -> PriceTable:
    with path.open("rb") as stream:
        models = tomllib.load(stream)["models"]
    table = {model: Decimal(row["input_usd_per_mtok"]) for model, row in models.items()}
    for price in table.values():
        _validate_price(price)
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
