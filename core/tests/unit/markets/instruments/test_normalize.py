import pytest

from sentinel.errors import UserError
from sentinel.markets.instruments import SearchParams, norm_query, normalize_symbol


def test_normalize_symbol_and_query() -> None:
    assert normalize_symbol(" BRK-B ") == "BRK.B"
    assert normalize_symbol("A B") is None
    assert norm_query(" 苹果 公司! ") == "苹果公司"
    assert norm_query("ＢＲＫ．Ｂ /_%- !") == "brkb"


@pytest.mark.parametrize(
    "raw", ["", " ", "A B", "A'", "A%", "A_", ".A", "A.", ".", "A..B", "Ａ", "é", None, True]
)
def test_invalid_symbols(raw: object) -> None:
    assert normalize_symbol(raw) is None


@pytest.mark.parametrize(
    "raw, expected", [("aapl", "AAPL"), ("1a", "1A"), (" brk-b ", "BRK.B"), ("X.Y", "X.Y")]
)
def test_valid_symbols(raw: str, expected: str) -> None:
    assert normalize_symbol(raw) == expected


@pytest.mark.parametrize("query", ["", " ", "!_% .", "a" * 65, None, True, 1])
def test_params_invalid_query(query: object) -> None:
    with pytest.raises(UserError) as error:
        SearchParams(query=query)
    assert error.value.code == "INVALID_ARGUMENT"
    assert error.value.field == "query"


@pytest.mark.parametrize("limit", [0, 51, -1, True, False, 1.0, "20", None])
def test_params_invalid_limit(limit: object) -> None:
    with pytest.raises(UserError) as error:
        SearchParams(query="a", limit=limit)
    assert error.value.field == "limit"
