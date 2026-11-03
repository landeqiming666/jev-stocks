import json
import os
import subprocess
from pathlib import Path

from sentinel.evaluation import EvalConfig, evaluate, write_report
from sentinel.evaluation.dataset import load_dataset
from sentinel.evaluation.replay import ReplayEngine

ROOT = Path(__file__).resolve().parents[4]
FIXTURES = ROOT / "core/tests/fixtures/eval"


def test_report_never_rewrites_history_and_is_machine_readable(tmp_path, monkeypatch):
    monkeypatch.setenv("SENTINEL_CLOCK", "2026-11-03T00:00:00Z")
    dataset = load_dataset(FIXTURES / "dataset.jsonl", mode="fixture")
    report = evaluate(
        EvalConfig(dataset=dataset), ReplayEngine(FIXTURES / "cassettes", dataset, "jev-1.14.0")
    )
    first = write_report(report, tmp_path / "reports")
    original = first.json.read_bytes()
    second = write_report(report, tmp_path / "reports")
    assert first.json != second.json
    assert first.json.read_bytes() == original
    value = json.loads(original)
    assert value["datasetHash"] == dataset.manifest.sha256
    assert value["source"] == "synthetic"
    assert value["goldQuality"]["status"] == "NOT_RUN"
    assert value["gate"]["passed"] is None
    assert len(first.predictions.read_text().splitlines()) == 30
    assert "NOT_RUN" in first.markdown.read_text()
    assert "synthetic" in first.markdown.read_text()


def cli(*args):
    return subprocess.run(
        [
            "uv",
            "run",
            "--frozen",
            "--project",
            str(ROOT / "core"),
            "python",
            str(ROOT / "scripts/eval.py"),
            *map(str, args),
        ],
        cwd=ROOT,
        env={**os.environ, "SENTINEL_OFFLINE": "1"},
        capture_output=True,
        text=True,
        timeout=15,
    )


def test_cli_exit_codes_and_functional_replay(tmp_path):
    base = ["--mode", "fixture", "--split", "test", "--out", tmp_path / "reports"]
    result = cli(*base, "--replay", FIXTURES / "cassettes")
    assert result.returncode == 0, result.stderr
    assert "samples=30" in result.stdout
    assert cli(*base, "--replay", FIXTURES / "cassettes", "--gate").returncode == 3
    assert cli(*base, "--replay", tmp_path / "missing").returncode == 4
    assert cli("--replay", FIXTURES / "cassettes", "--out", tmp_path / "real").returncode == 2
    assert cli(*base, "--split", "all", "--replay", FIXTURES / "cassettes").returncode == 2


def test_report_removes_env_secret_but_keeps_hash_and_code_sha(tmp_path, monkeypatch):
    dataset = load_dataset(FIXTURES / "dataset.jsonl", mode="fixture")
    report = evaluate(
        EvalConfig(dataset=dataset, code_version="a" * 40),
        ReplayEngine(FIXTURES / "cassettes", dataset, "jev-1.14.0"),
    )
    secret = "test-report-secret-42"
    monkeypatch.setenv("EVAL_BASELINE_API_KEY", secret)
    report.warnings.append("accidental " + secret)
    paths = write_report(report, tmp_path / "safe")
    for path in (paths.json, paths.markdown, paths.predictions):
        assert secret not in path.read_text()
    decoded = json.loads(paths.json.read_text())
    assert decoded["codeVersion"] == "a" * 40
    assert decoded["datasetHash"] == dataset.manifest.sha256


def test_cli_reports_unconfigured_direct_scoring_and_manifest(tmp_path, monkeypatch):
    monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)
    out = tmp_path / "direct"
    result = cli("--mode", "fixture", "--out", out)
    assert result.returncode == 4
    value = json.loads((out / "report.json").read_text())
    assert value["completed"] == 0
    assert value["rows"][0]["error"] == "SOURCE_UNAVAILABLE"
    assert value["usage"]["calls"] == 0
    new_manifest = tmp_path / "review.json"
    assert cli("--mode", "fixture", "--make-manifest", new_manifest).returncode == 0
    assert cli("--mode", "fixture", "--make-manifest", new_manifest).returncode == 2
