from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import acceptance  # noqa: E402


def _runner(tmp_path: Path, mode: str = "full") -> acceptance.AcceptanceRunner:
    return acceptance.AcceptanceRunner(Path.cwd(), tmp_path, mode)  # type: ignore[arg-type]


def test_run_can_remove_inherited_environment(monkeypatch) -> None:
    monkeypatch.setenv("SENTINEL_OFFLINE", "1")
    monkeypatch.setenv("JEV_API_KEY", "test-secret-value")
    code, output = acceptance._run(
        [
            sys.executable,
            "-c",
            "import os; print(os.getenv('SENTINEL_OFFLINE')); print(os.getenv('JEV_API_KEY'))",
        ],
        cwd=Path.cwd(),
        env={"SENTINEL_OFFLINE": None, "JEV_API_KEY": None},
    )
    assert code == 0
    assert output.splitlines() == ["None", "None"]


def test_m7_clears_offline_and_live_credentials(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("SENTINEL_OFFLINE", "1")
    monkeypatch.setenv("JEV_API_KEY", "test-secret-value")
    monkeypatch.setenv("SENTINEL_JEVDB_PATH", "/private/extension.duckdb_extension")
    calls: list[tuple[list[str], dict[str, str | None]]] = []

    def fake_run(command, *, cwd, env=None):
        calls.append((list(command), env or {}))
        return 0, "gate passed"

    monkeypatch.setattr(acceptance, "_run", fake_run)
    result = _runner(tmp_path).check_m7()

    assert result.status == "pass"
    assert len(calls) == 1
    _, child_env = calls[0]
    assert child_env["SENTINEL_OFFLINE"] is None
    assert child_env["JEV_API_KEY"] is None
    assert child_env["SENTINEL_JEVDB_PATH"] is None


def test_m1_load_clear_reload_restores_fixed_counts(tmp_path: Path, monkeypatch) -> None:
    calls: list[list[str]] = []

    def fake_run(command, *, cwd, env=None):
        calls.append(list(command))
        if "--clear" in command:
            return 0, json.dumps({"cleared": True, "removed": 1620, "ok": True})
        return 0, json.dumps({"loaded": True, "counts": acceptance.EXPECTED_COUNTS})

    monkeypatch.setattr(acceptance, "_run", fake_run)
    result = _runner(tmp_path).check_m1()

    assert result.status == "pass", result.detail
    assert len(calls) == 3
    assert "--clear" in calls[1]
    payload = json.loads((tmp_path / "artifacts" / "m1-demo-load.json").read_text())
    assert payload["load"]["counts"] == acceptance.EXPECTED_COUNTS
    assert payload["reload"]["counts"] == acceptance.EXPECTED_COUNTS
    assert payload["clear"]["removed"] == 1620


def test_m1_rejects_reload_with_changed_counts(tmp_path: Path, monkeypatch) -> None:
    runs = 0

    def fake_run(command, *, cwd, env=None):
        nonlocal runs
        runs += 1
        if "--clear" in command:
            return 0, json.dumps({"cleared": True, "removed": 10})
        counts = dict(acceptance.EXPECTED_COUNTS)
        if runs == 3:
            counts["prices"] = 1559
        return 0, json.dumps({"loaded": True, "counts": counts})

    monkeypatch.setattr(acceptance, "_run", fake_run)
    result = _runner(tmp_path).check_m1()

    assert result.status == "fail"
    assert "reload counts" in result.detail


def _m3_evidence(work: Path, **overrides: object) -> None:
    payload = {
        "memorySecretStore": True,
        "secretVisibleInUi": False,
        "settingsGetClean": True,
        "bootstrapClean": True,
        "connectionTestClean": True,
        "coreLogsClean": True,
        "coreLogFiles": 2,
        "secretStatusBefore": True,
        "secretStatusAfter": False,
        "scanWhileConfiguredError": "SOURCE_UNAVAILABLE",
        "scanAfterClearError": "CONFIG_REQUIRED",
        "rpcResponses": {"statusBefore": {"jevKey": True}},
    }
    payload.update(overrides)
    path = work / "artifacts" / "browser" / "m3-credentials.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_m2_requires_structured_results_even_on_zero_exit(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(acceptance, "_run", lambda *args, **kwargs: (0, "playwright finished"))
    result = _runner(tmp_path).check_m2()

    assert result.status == "fail"
    assert result.detail == "playwright results missing"


def test_m3_requires_real_rpc_browser_evidence(tmp_path: Path, monkeypatch) -> None:
    _m3_evidence(tmp_path)
    result = _runner(tmp_path).check_m3()

    assert result.status == "pass", result.detail
    payload = json.loads((tmp_path / "artifacts" / "m3-secret-scan.json").read_text())
    assert payload["plantedDetected"] is True
    assert payload["cleanSources"] is True


def test_m3_rejects_missing_or_leaky_browser_evidence(tmp_path: Path, monkeypatch) -> None:
    runner = _runner(tmp_path)
    missing = runner.check_m3()
    assert missing.status == "fail"
    assert "evidence missing" in missing.detail

    _m3_evidence(tmp_path, rpcResponses={"echo": acceptance.SECRET_SENTINEL})
    leaky = runner.check_m3()
    assert leaky.status == "fail"
    assert "echoed" in leaky.detail


def test_m3_is_not_run_without_browser_suite(tmp_path: Path) -> None:
    runner = _runner(tmp_path)
    runner.skip_e2e = True
    assert runner.check_m3().status == "not_run"


def test_preflight_always_reports_eight_statuses(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(acceptance.shutil, "which", lambda name: None)
    checks = _runner(tmp_path).preflight()

    assert [check.id for check in checks] == list(acceptance.CHECK_IDS)
    assert checks[0].status == "fail"
    assert all(check.status == "not_run" for check in checks[1:])
    assert all("uv" in check.detail and "pnpm" in check.detail for check in checks)



def test_m8_reports_missing_live_configuration_without_starting_core(
    tmp_path: Path, monkeypatch
) -> None:
    for name in ("JEV_API_KEY", "SENTINEL_JEVDB_PATH", "SENTINEL_SEC_CONTACT"):
        monkeypatch.delenv(name, raising=False)
    runner = _runner(tmp_path)
    runner.confirm_live_model_cost = True

    result = runner.check_m8()

    assert result.status == "fail"
    assert "JEV_API_KEY" in result.detail
    assert "SENTINEL_JEVDB_PATH" in result.detail
    assert "SENTINEL_SEC_CONTACT" in result.detail
    payload = json.loads((tmp_path / "artifacts" / "m8-blocked.json").read_text())
    assert payload["reason"] == "CONFIG_REQUIRED"


def test_m8_requires_explicit_cost_confirmation_before_network(tmp_path: Path, monkeypatch) -> None:
    extension = tmp_path / "test.duckdb_extension"
    extension.write_bytes(b"not loaded by this test")
    monkeypatch.setenv("JEV_API_KEY", "test-secret-value")
    monkeypatch.setenv("SENTINEL_JEVDB_PATH", str(extension))
    monkeypatch.setenv("SENTINEL_SEC_CONTACT", "analyst@example.com")
    monkeypatch.delenv("SENTINEL_OFFLINE", raising=False)
    runner = _runner(tmp_path)
    runner.confirm_live_model_cost = False

    result = runner.check_m8()

    assert result.status == "not_run"
    assert "confirm-live-model-cost" in result.detail
    assert not (tmp_path / "artifacts" / "m8-scan.json").exists()


def test_m8_offline_environment_blocks_real_requests(tmp_path: Path, monkeypatch) -> None:
    extension = tmp_path / "test.duckdb_extension"
    extension.write_bytes(b"not loaded by this test")
    monkeypatch.setenv("JEV_API_KEY", "test-secret-value")
    monkeypatch.setenv("SENTINEL_JEVDB_PATH", str(extension))
    monkeypatch.setenv("SENTINEL_SEC_CONTACT", "analyst@example.com")
    monkeypatch.setenv("SENTINEL_OFFLINE", "1")
    runner = _runner(tmp_path)
    runner.confirm_live_model_cost = True

    result = runner.check_m8()

    assert result.status == "fail"
    assert result.detail == "SENTINEL_OFFLINE blocks live acceptance"
    assert not (tmp_path / "artifacts" / "m8-scan.json").exists()


def test_report_evidence_resolves_from_report_directory(tmp_path: Path) -> None:
    work = tmp_path / "work"
    work.mkdir()
    runner = _runner(work)
    relative = runner._write_evidence("check.json", '{"ok":true}')
    report = acceptance.AcceptanceReport(
        "offline",
        "macos",
        "2026-11-05T00:00:00Z",
        "2026-11-05T00:01:00Z",
        [acceptance.CheckResult("M-1", "pass", [relative])],
        str(work),
    )
    destination = tmp_path / "report"
    path = acceptance.write_report(report, destination)
    payload = json.loads(path.read_text())
    evidence = (destination / payload["checks"][0]["evidence"][0]).resolve()
    assert evidence == (work / "artifacts" / "check.json").resolve()
    assert (destination / "manual-checklist.md").read_text().count("- [ ]") == 6
    assert acceptance.verify_evidence(path) == []


def test_verify_evidence_reports_missing_file(tmp_path: Path) -> None:
    work = tmp_path / "work"
    work.mkdir()
    runner = _runner(work)
    relative = runner._write_evidence("check.json", '{"ok":true}')
    report = acceptance.AcceptanceReport(
        "offline",
        "macos",
        "2026-11-05T00:00:00Z",
        "2026-11-05T00:01:00Z",
        [acceptance.CheckResult("M-1", "pass", [relative])],
        str(work),
    )
    path = acceptance.write_report(report, tmp_path / "report")
    (work / "artifacts" / "check.json").unlink()

    assert acceptance.verify_evidence(path) == ["M-1: ../work/artifacts/check.json"]


def test_report_uses_repo_relative_work_dir(tmp_path: Path) -> None:
    work = acceptance.ROOT / ".tmp-pytest" / "unit-display"
    report = acceptance.AcceptanceReport(
        "offline",
        "macos",
        "2026-11-05T00:00:00Z",
        "2026-11-05T00:01:00Z",
        [acceptance.CheckResult("M-1", "not_run", [])],
        str(work),
    )
    assert report.to_wire()["workDir"] == ".tmp-pytest/unit-display"
    destination = tmp_path / "summary-report"
    acceptance.write_report(report, destination)
    summary = (destination / "summary.md").read_text()
    assert ".tmp-pytest/unit-display" in summary
    assert str(acceptance.ROOT) not in summary



def test_system_python_can_reexec_the_locked_runtime() -> None:
    import shutil
    import subprocess

    python = shutil.which("python3")
    assert python is not None
    result = subprocess.run(
        [python, str(acceptance.ROOT / "scripts/acceptance.py"), "--self-test"],
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert result.returncode == 0, result.stderr
    assert "SELF-TEST PASS" in result.stdout


def test_command_timeout_returns_failure_with_output(tmp_path: Path) -> None:
    code, output = acceptance._run(
        [sys.executable, "-c", "import time; print('started', flush=True); time.sleep(10)"],
        cwd=tmp_path,
        timeout=0.2,
    )
    assert code == 124
    assert "started" in output


def test_check_exception_still_records_all_eight_statuses(tmp_path: Path, monkeypatch) -> None:
    runner = _runner(tmp_path)
    monkeypatch.setattr(runner, "preflight", lambda: [])
    for index in range(1, 9):
        method = f"check_m{index}"
        monkeypatch.setattr(
            runner, method, lambda index=index: acceptance.CheckResult(f"M-{index}", "pass")
        )

    def broken():
        raise TimeoutError("private upstream response must never be saved")

    monkeypatch.setattr(runner, "check_m2", broken)
    report = runner.run()
    assert len(report.checks) == 8
    assert report.checks[1].status == "fail"
    assert report.checks[2].status == "pass"
    assert report.overall == "fail"
    assert "private upstream" not in (tmp_path / "artifacts" / "m-2-error.json").read_text()
