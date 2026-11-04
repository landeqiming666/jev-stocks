from decimal import Decimal

import pytest


def test_estimate_tokens_rounds_up_with_3_5_chars():
    from sentinel.semantic.budget import estimate_tokens

    assert [estimate_tokens(c) for c in (0, 1, 4, 35)] == [0, 1, 2, 10]


def test_budget_reserves_twenty_percent_without_float_drift():
    from sentinel.semantic.budget import check_budget, reserve_tokens

    decision = check_budget(0, 101, 122)
    assert reserve_tokens(101) == decision.reserved == 122
    assert decision.allowed and decision.remaining == 122
    assert reserve_tokens(25) == 30
    assert reserve_tokens(10**50 + 1) == (6 * (10**50 + 1) + 4) // 5


def test_budget_exhausted_returns_zero_remaining():
    from sentinel.semantic.budget import check_budget

    decision = check_budget(100, 10, 100)
    assert not decision.allowed and decision.remaining == 0
    assert check_budget(101, 0, 100).remaining == 0


def test_cost_uses_decimal_and_six_places():
    from sentinel.semantic.pricing import cost_usd

    result = cost_usd(1_000_000, "jev-1.14.0")
    assert result == Decimal("0.042000") and result.as_tuple().exponent == -6


def test_numeric_inputs_reject_bool_nonintegers_and_nonfinite():
    import pytest

    from sentinel.semantic.budget import check_budget, estimate_tokens, reserve_tokens
    from sentinel.semantic.pricing import cost_usd

    for bad in (-1, True, False, 1.5, float("nan"), float("inf"), "1", None):
        for call in (
            lambda bad=bad: estimate_tokens(bad),
            lambda bad=bad: reserve_tokens(bad),
            lambda bad=bad: check_budget(bad, 0, 1),
            lambda bad=bad: check_budget(0, bad, 1),
            lambda bad=bad: check_budget(0, 0, bad),
            lambda bad=bad: cost_usd(bad, "jev-1.14.0"),
        ):
            with pytest.raises(ValueError):
                call()
    assert estimate_tokens(10**50) == (2 * 10**50 + 6) // 7
    assert check_budget(5, 0, 5).allowed


def test_cost_is_independent_of_global_decimal_context():
    from decimal import ROUND_DOWN, Inexact, localcontext

    from sentinel.semantic.pricing import cost_usd

    with localcontext() as ctx:
        ctx.prec, ctx.rounding = 2, ROUND_DOWN
        ctx.traps[Inexact] = True
        ctx.Emax, ctx.Emin = 1, -1
        before = ctx.copy()
        assert cost_usd(12, "jev-1.14.0") == Decimal("0.000001")
        assert cost_usd(11, "jev-1.14.0") == Decimal("0.000000")
        assert cost_usd(10**40, "jev-1.14.0") == Decimal("420000000000000000000000000000000.000000")
        assert cost_usd(1, "custom", {"custom": Decimal("0.5")}) == Decimal("0.000001")
        assert (ctx.prec, ctx.rounding, ctx.traps, ctx.flags) == (
            before.prec,
            before.rounding,
            before.traps,
            before.flags,
        )


def test_price_table_unknown_models_and_unverified_dates():
    import tomllib

    import pytest

    from sentinel.semantic.pricing import DEFAULT_PRICING_PATH, cost_usd, load_price_table

    assert load_price_table() == {"jev-1.14.0": Decimal("0.042"), "jev-1.13.0": Decimal("0.042")}
    with DEFAULT_PRICING_PATH.open("rb") as stream:
        models = tomllib.load(stream)["models"]
    assert {row["verification"] for row in models.values()} == {"TODO-VERIFY(G0-JEV)"}
    assert [row["effective_from"] for row in models.values()] == ["2026-10-14", "2026-10-02"]
    for model in ("jev-latest", "jev-1.14", "unknown"):
        with pytest.raises(ValueError):
            cost_usd(1, model)
    with pytest.raises(ValueError):
        cost_usd(0, "jev-1.14.0", {})
    for price in (Decimal("NaN"), Decimal("sNaN"), Decimal("Infinity"), Decimal("-1"), 0.042):
        with pytest.raises(ValueError):
            cost_usd(1, "custom", {"custom": price})


def test_usage_migration_is_verbatim_document_ddl():
    from pathlib import Path

    root = Path(__file__).resolve().parents[4]
    document = (root / "docs/04-数据模型.md").read_text()
    expected = document.split("### 3.9 `009_usage.sql` · S-02\n\n```sql\n", 1)[1].split("```", 1)[0]
    assert (root / "core/sentinel/storage/migrations/009_usage.sql").read_text() == expected


@pytest.mark.parametrize(
    "text",
    [
        "",
        "[models]\n",
        'models = "bad"',
        "models = false",
        "models = []",
        'models = [{model = "jev-1.14.0"}]',
        '[models]\n"jev-1.14.0" = false',
        '[models]\n"jev-1.14.0" = 0.042',
        '[models]\n"jev-1.14.0" = "0.042"',
        '[models]\n"jev-1.14.0" = []',
        '[models."jev-1.14.0"]',
        '[models."jev-1.14.0"]\neffective_from = "2026-10-14"',
    ],
)
def test_price_loader_rejects_empty_and_invalid_structure(tmp_path, text):
    from sentinel.semantic.pricing import load_price_table

    path = tmp_path / "pricing.toml"
    path.write_text(text)
    with pytest.raises(ValueError):
        load_price_table(path)


@pytest.mark.parametrize(
    "price",
    [
        "false",
        "true",
        "0.042",
        "0",
        "[]",
        "{}",
        '""',
        '"NaN"',
        '"sNaN"',
        '"Infinity"',
        '"-Infinity"',
        '"-0.042"',
        '"free"',
        '"0.0_42"',
        '" 0.042 "',
        '"０.０４２"',
        '"1e999999999999999999999999999999"',
    ],
)
def test_price_loader_rejects_nondecimal_and_invalid_price_text(tmp_path, price):
    from sentinel.semantic.pricing import load_price_table

    path = tmp_path / "pricing.toml"
    path.write_text(f'[models."jev-1.14.0"]\ninput_usd_per_mtok = {price}\n')
    with pytest.raises(ValueError):
        load_price_table(path)


@pytest.mark.parametrize(
    "model", ["", "jev-latest", "jev-1.14", "jev-01.14.0", "other", "jev-1.14.0 "]
)
def test_price_loader_rejects_unpinned_or_invalid_model_ids(tmp_path, model):
    from sentinel.semantic.pricing import load_price_table

    path = tmp_path / "pricing.toml"
    path.write_text(f'[models."{model}"]\ninput_usd_per_mtok = "0.042"\n')
    with pytest.raises(ValueError):
        load_price_table(path)


def test_price_loader_keeps_decimal_text_exact_and_rejects_whole_invalid_table(tmp_path):
    from decimal import FloatOperation, localcontext

    from sentinel.semantic.pricing import load_price_table

    path = tmp_path / "pricing.toml"
    text = (
        '[models."jev-1.14.0"]\ninput_usd_per_mtok = "0.042"\n'
        '[models."jev-1.13.0"]\ninput_usd_per_mtok = "0"\n'
    )
    path.write_text(text)
    with localcontext() as ctx:
        ctx.prec = 2
        ctx.traps[FloatOperation] = True
        assert load_price_table(path) == {
            "jev-1.14.0": Decimal("0.042"),
            "jev-1.13.0": Decimal("0"),
        }
    path.write_text(text.replace('input_usd_per_mtok = "0"', "input_usd_per_mtok = false"))
    with pytest.raises(ValueError):
        load_price_table(path)
