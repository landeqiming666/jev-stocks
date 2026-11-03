from decimal import Decimal


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
