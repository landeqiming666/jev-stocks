import json
import threading
import time
from pathlib import Path

import pytest
from sentinel.errors import EngineError, ErrorCode
from sentinel.evaluation import EvalConfig, EvaluationRunner, evaluate
from sentinel.evaluation.dataset import load_dataset
from sentinel.evaluation.replay import ReplayEngine
from sentinel.semantic.engines.jev_direct import JevDirectEngine, SystemOneResponse

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures" / "eval"


def setup(gate=False, split="test", **kwargs):
    dataset = load_dataset(FIXTURES / "dataset.jsonl", mode="fixture")
    config = EvalConfig(dataset=dataset, gate=gate, split=split, **kwargs)
    return config, ReplayEngine(FIXTURES / "cassettes", dataset, config.model_id)


def test_replay_uses_no_network(monkeypatch):
    monkeypatch.setenv("SENTINEL_OFFLINE", "1")
    monkeypatch.setattr("httpx.Client.send", lambda *a, **kw: pytest.fail("network"))
    config, engine = setup()
    report = evaluate(config, engine)
    assert report.samples == 30 and report.completed == 30
    assert report.strict.positive_count == 11
    assert report.strict.f1 is not None
    assert report.gold_quality.status == "NOT_RUN"
    assert report.gold_quality.kappa is None
    assert report.real_model_status == "NOT_RUN"
    assert report.gate.passed is None
    assert report.baseline.status == "NOT_RUN"
    assert report.baseline.rows == []
    assert report.usage.cost_usd >= 0
    assert len(report.by_lang) == 2 and len(report.by_subset) == 5


def test_gate_fails_below_080_and_fixture_cannot_formally_pass():
    config, engine = setup(gate=True)
    report = evaluate(config, engine)
    assert report.gate.passed is False
    assert report.gate.status == "NOT_RUN"
    assert report.exit_code == 3
    assert report.gate.experimental_passed == (
        report.strict.f1 >= 0.8
        and report.by_lang["en"].strict.f1 - report.by_lang["zh"].strict.f1 <= 0.05
    )


def test_mixed_split_requires_explicit_opt_in():
    with pytest.raises(ValueError, match="mix"):
        setup(split="all")
    config, engine = setup(split="all", allow_tuned_test=True)
    assert evaluate(config, engine).samples == 60


def test_missing_cassette_fails_and_preserves_partial(tmp_path):
    config, _ = setup()
    for file in (FIXTURES / "cassettes").glob("*.json"):
        content = json.loads(file.read_text())
        content["frames"] = [f for f in content["frames"] if f["id"] != "p-0032"]
        (tmp_path / file.name).write_text(json.dumps(content))
    report = evaluate(config, ReplayEngine(tmp_path, config.dataset, config.model_id))
    assert report.exit_code == 4
    assert report.rows[0].status == "ok"
    assert report.rows[1].error == "MISSING_CASSETTE"
    assert report.rows[1].relation is None
    assert len(report.rows) == 30
    assert all(r.status == "not_run" for r in report.rows[2:])


def test_failed_engine_is_not_none_and_auth_stops():
    config, engine = setup()

    def fail(*args):
        raise EngineError(ErrorCode.UNAUTHENTICATED, detail="secret-in-body")

    engine.score_pairs = fail
    report = evaluate(config, engine)
    assert report.failed == 1
    assert report.rows[0].relation is None
    assert report.strict.n == 0
    assert report.completed == 0
    assert report.exit_code == 4
    assert all(r.status == "not_run" for r in report.rows[1:])
    assert "secret-in-body" not in report.model_dump_json()


def test_error_continues_without_mapping_failed_to_none():
    config, engine = setup()
    score = engine.score_pairs

    def fail_once(company, pairs, cancel):
        if pairs[0].thesis.thesis_id == "p-0031":
            raise EngineError(ErrorCode.MODEL_ERROR)
        return score(company, pairs, cancel)

    engine.score_pairs = fail_once
    report = evaluate(config, engine)
    assert report.failed == 1 and report.completed == 29
    assert report.strict.n == 29
    assert report.exit_code == 4


def test_cancel_before_request_sends_nothing():
    config, engine = setup()
    runner = EvaluationRunner(config, engine)
    runner.cancel.cancel()
    report = runner.run()
    assert len(report.rows) == 30
    assert all(r.status == "not_run" for r in report.rows)
    assert not report.usage.complete and all(not r.usage.complete for r in report.rows)
    assert report.exit_code == 4


def test_timeout_and_cancellation_are_bounded_and_keep_partial():
    config, engine = setup(timeout_sec=0.06)
    release = threading.Event()
    calls = []
    score = engine.score_pairs

    def hanging(company, pairs, cancel):
        calls.append(pairs[0].thesis.thesis_id)
        if len(calls) == 1:
            return score(company, pairs, cancel)
        release.wait(3)
        return score(company, pairs, cancel)

    engine.score_pairs = hanging
    start = time.monotonic()
    try:
        report = evaluate(config, engine)
        assert time.monotonic() - start < 0.5
        assert report.rows[0].status == "ok"
        assert report.rows[1].error == "TIMEOUT"
        assert not report.usage.complete and all(not r.usage.complete for r in report.rows[1:])
        assert len(report.rows) == 30
        assert len(calls) == 2
        assert report.exit_code == 4
    finally:
        release.set()


def test_cancel_during_request_keeps_preceding_rows():
    config, engine = setup()
    release = threading.Event()
    started = threading.Event()
    score = engine.score_pairs

    def hanging(company, pairs, cancel):
        if pairs[0].thesis.thesis_id == "p-0032":
            started.set()
            release.wait(3)
        return score(company, pairs, cancel)

    engine.score_pairs = hanging
    runner = EvaluationRunner(config, engine)

    def stop():
        started.wait(1)
        runner.cancel.cancel()

    threading.Thread(target=stop, daemon=True).start()
    start = time.monotonic()
    try:
        report = runner.run()
        assert time.monotonic() - start < 0.5
        assert report.rows[0].status == "ok"
        assert report.rows[1].error == "CANCELLED"
        assert len(report.rows) == 30
    finally:
        release.set()


def test_actual_s03_adapter_consumes_real_question_builder():
    config, _ = setup()
    sent = []

    class Client:
        def call(self, *, model, state, questions):
            sent.append((state, questions))
            return SystemOneResponse(model, {k: 0.1 for k in questions}, 10, 0)

    engine = JevDirectEngine(
        model_id=config.model_id, api_key="test-key-do-not-use", client_factory=lambda key: Client()
    )
    report = evaluate(config, engine)
    assert report.completed == 30
    assert len(sent) == 30
    assert "document" in sent[0][0]
    assert "t1__relevant" in sent[0][1]
    assert report.real_model_status == "NOT_RUN"


@pytest.mark.parametrize("key", ["inputHash", "modelId", "questionSetVersion", "datasetHash"])
def test_cassette_provenance_tampering_is_rejected(tmp_path, key):
    config, _ = setup()
    cassette = json.loads(next((FIXTURES / "cassettes").glob("*.json")).read_text())
    target = cassette["frames"][0] if key == "inputHash" else cassette
    target[key] = "changed"
    (tmp_path / "changed.json").write_text(json.dumps(cassette))
    with pytest.raises(ValueError):
        ReplayEngine(tmp_path, config.dataset, config.model_id)


def test_evidence_fallback_preserves_scoring_and_partial_usage():
    config, engine = setup()

    def fail(*args):
        raise EngineError(ErrorCode.MODEL_ERROR, detail="sensitive response")

    engine.locate_evidence = fail
    report = evaluate(config, engine)
    assert report.completed == 30
    assert report.rows[0].relation == "overturn"
    assert report.rows[0].evidence_kind == "passage"
    assert report.rows[0].evidence_error == "MODEL_ERROR"
    assert not report.rows[0].usage.complete
    assert report.rows[0].usage.calls == 2
    assert report.evidence["hits"] == 0
    assert report.evidence["titleCount"] == 1
    assert report.evidence["passageCount"] == 9
    assert "sensitive response" not in report.model_dump_json()


def test_evidence_offsets_select_original_sentence():
    config, engine = setup()
    report = evaluate(config, engine)
    sample = config.dataset.samples[30]
    predicted = report.rows[0]
    assert predicted.evidence_kind == "sentence"
    assert predicted.evidence_sentence == 2
    assert sample.passage.text[predicted.evidence_start : predicted.evidence_end].startswith(
        "The controlling shareholder completed"
    )
    assert report.evidence == {
        "denominator": 10,
        "hits": 9,
        "hitRate": 0.9,
        "passageCount": 0,
        "titleCount": 1,
    }


def test_explicit_experiment_threshold_and_synthetic_eligibility():
    from sentinel.evaluation.runner import _gate

    config, engine = setup(gate=True)
    report = evaluate(config, engine)
    report.strict.f1 = 0.79
    assert _gate(config, report).experimental_passed is False
    report.strict.f1 = 1.0
    report.by_lang["zh"].strict.f1 = 1.0
    report.by_lang["en"].strict.f1 = 1.0
    gate = _gate(config, report)
    assert gate.experimental_passed is True
    assert gate.passed is False and gate.status == "NOT_RUN"
    report.by_lang["zh"].strict.f1 = 0.94
    assert _gate(config, report).experimental_passed is False


def test_cooperative_timeout_does_not_lose_completed_rows():
    config, engine = setup(timeout_sec=0.1)
    score = engine.score_pairs

    def fail_first(company, pairs, cancel):
        if pairs[0].thesis.thesis_id == "p-0031":
            raise EngineError(ErrorCode.TIMEOUT)
        return score(company, pairs, cancel)

    engine.score_pairs = fail_first
    report = evaluate(config, engine)
    assert report.rows[0].error == "TIMEOUT"
    assert report.completed == 29


def test_experimental_language_delta_includes_exact_005_boundary():
    from sentinel.evaluation.runner import _gate

    config, engine = setup(gate=True)
    report = evaluate(config, engine)
    report.strict.f1 = 0.9
    report.by_lang["zh"].strict.f1 = 0.85
    report.by_lang["en"].strict.f1 = 0.9
    assert _gate(config, report).experimental_passed is True


def test_permanently_hung_engine_does_not_prevent_process_exit():
    import subprocess
    import sys

    code = """
import threading
from pathlib import Path
from sentinel.evaluation import EvalConfig, evaluate
from sentinel.evaluation.dataset import load_dataset
from sentinel.evaluation.replay import ReplayEngine
root = Path('core/tests/fixtures/eval')
dataset = load_dataset(root/'dataset.jsonl', mode='fixture')
engine = ReplayEngine(root/'cassettes', dataset, 'jev-1.14.0')
engine.score_pairs = lambda *args: threading.Event().wait()
report = evaluate(EvalConfig(dataset=dataset, timeout_sec=.05), engine)
print(len(report.rows), report.rows[0].error)
raise SystemExit(report.exit_code)
"""
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=FIXTURES.parents[3],
        capture_output=True,
        text=True,
        timeout=3,
    )
    assert result.returncode == 4, result.stderr
    assert result.stdout.strip() == "30 TIMEOUT"


@pytest.mark.parametrize("timeout", [True, False])
def test_eval_timeout_rejects_bool(timeout):
    with pytest.raises(ValueError, match="timeout"):
        setup(timeout_sec=timeout)
