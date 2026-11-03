import json
from decimal import ROUND_DOWN, Decimal, Inexact, Rounded, localcontext
from pathlib import Path

import httpx
import pytest
from sentinel.evaluation.baselines import BaselineConfig, _price, run_baseline
from sentinel.evaluation.dataset import load_dataset

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures" / "eval"


def test_baseline_reports_calls_tokens_latency_cost(monkeypatch):
    monkeypatch.delenv("SENTINEL_OFFLINE", raising=False)
    examples = [
        json.loads(line) for line in (FIXTURES / "baseline_example.jsonl").read_text().splitlines()
    ]
    calls = []

    def respond(request):
        calls.append(request)
        return httpx.Response(200, json=examples[len(calls) - 1]["response"])

    config = BaselineConfig(
        endpoint="https://example.test/v1",
        model="example-model",
        input_price=Decimal("1"),
        output_price=Decimal("2"),
    )
    monkeypatch.setenv("EVAL_BASELINE_API_KEY", "test-baseline-secret")
    samples = load_dataset(FIXTURES / "dataset.jsonl", mode="fixture").samples[30:33]
    ticks = iter([0.0, 0.005, 1.0, 1.010, 2.0, 2.015])
    report = run_baseline(
        config, samples, transport=httpx.MockTransport(respond), timer=lambda: next(ticks)
    )
    assert report.status == "COMPLETED"
    assert report.usage.calls == 3
    assert report.usage.input_tokens == 60
    assert report.usage.output_tokens == 6
    assert report.usage.cost_usd == Decimal(".000072")
    assert report.usage.latency_ms == 30
    assert report.p95_latency_ms == 14.5
    assert "test-baseline-secret" not in report.model_dump_json()
    assert all(json.loads(r.content)["model"] == "example-model" for r in calls)


def test_missing_baseline_env_is_explicit_not_run(monkeypatch):
    for name in list(__import__("os").environ):
        if name.startswith("EVAL_BASELINE_"):
            monkeypatch.delenv(name)
    report = run_baseline(None, [])
    assert report.status == "NOT_RUN" and report.rows == []
    assert report.usage.calls == 0
    assert not report.usage.complete


@pytest.mark.parametrize("bad", ["uncertain", "none extra", "", '"none"'])
def test_baseline_bad_model_output_is_failed_without_retry(monkeypatch, bad):
    monkeypatch.delenv("SENTINEL_OFFLINE", raising=False)
    monkeypatch.setenv("EVAL_BASELINE_API_KEY", "test-baseline-secret")
    samples = load_dataset(FIXTURES / "dataset.jsonl", mode="fixture").samples[30:31]

    def respond(request):
        return httpx.Response(
            200,
            json={
                "model": "example-model",
                "choices": [{"message": {"content": bad}}],
                "usage": {"prompt_tokens": 10, "completion_tokens": 2},
            },
        )

    config = BaselineConfig(
        endpoint="https://example.test/v1",
        model="example-model",
        input_price=Decimal("1"),
        output_price=Decimal("2"),
    )
    report = run_baseline(config, samples, transport=httpx.MockTransport(respond))
    assert report.status == "PARTIAL"
    assert report.rows[0].status == "failed"
    assert report.rows[0].relation is None
    assert report.usage.calls == 1
    assert report.usage.input_tokens == 10
    assert not report.usage.complete and not report.rows[0].usage.complete


def test_offline_baseline_sends_nothing(monkeypatch):
    monkeypatch.setenv("SENTINEL_OFFLINE", "1")
    monkeypatch.setenv("EVAL_BASELINE_API_KEY", "test-baseline-secret")
    config = BaselineConfig(
        endpoint="https://example.test/v1",
        model="example-model",
        input_price=Decimal("1"),
        output_price=Decimal("2"),
    )
    report = run_baseline(
        config, [], transport=httpx.MockTransport(lambda req: pytest.fail("network"))
    )
    assert report.status == "NOT_RUN"


def test_invalid_environment_pricing_is_configuration_error(monkeypatch):
    for suffix, value in {
        "ENDPOINT": "https://example.test/v1",
        "MODEL": "example-model",
        "API_KEY": "secret",
        "INPUT_USD_PER_MTOK": "invalid",
        "OUTPUT_USD_PER_MTOK": "2",
    }.items():
        monkeypatch.setenv("EVAL_BASELINE_" + suffix, value)
    with pytest.raises(ValueError, match="pricing"):
        BaselineConfig.from_env()


def test_baseline_auth_failure_keeps_all_partial_rows_and_other_thread_logs(monkeypatch, caplog):
    import logging

    monkeypatch.delenv("SENTINEL_OFFLINE", raising=False)
    monkeypatch.setenv("EVAL_BASELINE_API_KEY", "test-baseline-secret")
    samples = load_dataset(FIXTURES / "dataset.jsonl", mode="fixture").samples[30:33]
    calls = []

    def respond(request):
        calls.append(request)
        if len(calls) == 2:
            return httpx.Response(401, text="test-baseline-secret")
        return httpx.Response(
            200,
            json={
                "model": "example-model",
                "choices": [{"message": {"content": "none"}}],
                "usage": {"prompt_tokens": 10, "completion_tokens": 2},
            },
        )

    config = BaselineConfig(
        endpoint="https://example.test/v1",
        model="example-model",
        input_price=Decimal("1"),
        output_price=Decimal("2"),
    )
    with caplog.at_level(logging.INFO, logger="httpx"):
        report = run_baseline(config, samples, transport=httpx.MockTransport(respond))
        logging.getLogger("httpx").info("unrelated-thread-log")
    assert [r.status for r in report.rows] == ["ok", "failed", "not_run"]
    assert report.usage.calls == 2 and report.usage.input_tokens == 10
    assert not report.usage.complete
    assert report.rows[1].error == "UNAUTHENTICATED"
    assert all(not r.usage.complete for r in report.rows[1:])
    assert "unrelated-thread-log" in caplog.text
    assert "example.test" not in caplog.text
    assert "test-baseline-secret" not in caplog.text
    assert "test-baseline-secret" not in report.model_dump_json()


@pytest.mark.parametrize(
    "tokens,price,expected",
    [
        (1, "1.5", ".000002"),
        (int("1" * 80), "1", "1" * 74 + ".111111"),
        (1, "1E40", "1" + "0" * 34 + ".000000"),
    ],
)
def test_price_isolated_from_caller_decimal_context(tokens, price, expected):
    config = BaselineConfig(
        "https://example.test/v1", "example-model", Decimal(price), Decimal("0.000000000001")
    )
    with localcontext() as ctx:
        ctx.prec, ctx.rounding, ctx.Emax, ctx.Emin, ctx.clamp = 1, ROUND_DOWN, 6, -6, 1
        ctx.traps[Inexact] = ctx.traps[Rounded] = True
        ctx.flags[Inexact] = True
        before = (repr(ctx), dict(ctx.flags), dict(ctx.traps))
        assert _price(config, tokens, 0) == Decimal(expected)
        assert (repr(ctx), dict(ctx.flags), dict(ctx.traps)) == before


@pytest.mark.parametrize("timeout", [True, False])
def test_baseline_timeout_rejects_bool(timeout):
    with pytest.raises(ValueError, match="timeout"):
        BaselineConfig(
            "https://example.test/v1",
            "example-model",
            Decimal("1"),
            Decimal("2"),
            timeout_sec=timeout,
        )


@pytest.mark.parametrize("field", ["input_price", "output_price"])
@pytest.mark.parametrize("value", [True, None, "1", 1, 1.0])
def test_baseline_price_type_error_is_value_error(field, value):
    prices = {"input_price": Decimal("1"), "output_price": Decimal("2"), field: value}
    with pytest.raises(ValueError, match="Decimal"):
        BaselineConfig("https://example.test/v1", "example-model", **prices)
