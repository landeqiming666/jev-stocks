from decimal import Decimal

import pytest

from sentinel.errors import UserError
from sentinel.portfolio.validation import content_hash, validate_quantity, validate_text


def test_statement_counts_unicode_codepoints() -> None:
    assert validate_text("测" * 500, "statement", 500, required=True) == "测" * 500
    with pytest.raises(UserError) as caught:
        validate_text("测" * 500 + "试", "statement", 500, required=True)
    assert caught.value.field == "statement"
    assert caught.value.code == "INVALID_ARGUMENT"


def test_kill_condition_blank_becomes_none() -> None:
    assert validate_text("  \n ", "killCondition", 300) is None
    assert content_hash("x", None) == content_hash("x", "  \n ")


def test_quantity_rejects_fifth_decimal_place() -> None:
    with pytest.raises(UserError) as caught:
        validate_quantity(Decimal("0.00001"))
    assert caught.value.field == "quantity"


@pytest.mark.parametrize(
    "value",
    [
        Decimal("-1"),
        Decimal("100000000000000"),
        Decimal("NaN"),
        Decimal("Infinity"),
        Decimal("-Infinity"),
        True,
        1.5,
    ],
)
def test_quantity_rejects_invalid_internal_amounts(value: object) -> None:
    with pytest.raises(UserError):
        validate_quantity(value)


def test_amount_quantization_ignores_callers_decimal_context() -> None:
    from decimal import Inexact, Rounded, localcontext

    from sentinel.portfolio.validation import market_value

    with localcontext() as ctx:
        ctx.prec = 2
        ctx.traps[Inexact] = True
        ctx.traps[Rounded] = True
        assert validate_quantity(Decimal("99999999999999.9999")) == Decimal("99999999999999.9999")
        assert market_value(Decimal("120"), 52.38000001) == Decimal("6285.6000")
        assert market_value(Decimal("1"), 1.00005) == Decimal("1.0001")


def test_content_hash_normalizes_nfc_and_newlines_only() -> None:
    import hashlib

    assert content_hash(" e\u0301\r\nmargin\r ", "  floor ") == content_hash("é\nmargin", "floor")
    assert content_hash("a b", None) != content_hash("a  b", None)
    expected = hashlib.sha256("é\nmargin\n---\nfloor".encode()).hexdigest()
    assert content_hash(" e\u0301\r\nmargin\r ", "  floor ") == expected


@pytest.mark.parametrize(
    "field,maximum", [("statement", 500), ("killCondition", 300), ("note", 200)]
)
def test_text_strips_before_counting_unicode_codepoints(field: str, maximum: int) -> None:
    assert validate_text("\u3000" + "😀" * maximum + "\x1c", field, maximum) == "😀" * maximum
    with pytest.raises(UserError) as caught:
        validate_text("😀" * (maximum + 1), field, maximum)
    assert caught.value.field == field and caught.value.params["max"] == maximum
    with pytest.raises(UserError):
        validate_text("\ud800", field, maximum)
