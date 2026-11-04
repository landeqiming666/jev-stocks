#!/usr/bin/env python3
"""MVP-0 验收编排：M-1 至 M-8 的可重复检查与证据落盘。"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "core"))

try:  # 允许直接 python3 scripts/acceptance.py，自动切到 core 的虚拟环境
    import duckdb  # noqa: F401
except ImportError:  # pragma: no cover - 取决于调用方式
    os.execvp(
        "uv",
        ["uv", "run", "--project", str(ROOT / "core"), "python", str(Path(__file__)), *sys.argv[1:]],
    )

from sentinel.storage import Database  # noqa: E402

SCHEMA_VERSION = "1"
SECRET_SENTINEL = "test-key-do-not-use"
MAX_ACCEPTANCE_SECONDS = 900
CHECK_IDS = ("M-1", "M-2", "M-3", "M-4", "M-5", "M-6", "M-7", "M-8")
EXPECTED_COUNTS = {
    "instruments": 6,
    "holdings": 5,
    "theses": 6,
    "events": 6,
    "decisions": 12,
    "prices": 1560,
}
WHITELIST_ENGINE = {"jevdb", "jev_direct"}
WHITELIST_EVIDENCE = {"sentence", "passage", "title"}
SECRET_PATTERNS = (
    re.compile(r"sk-[A-Za-z0-9_-]{12,}"),
    re.compile(r"Bearer\s+[A-Za-z0-9._-]{20,}"),
    re.compile(re.escape(SECRET_SENTINEL)),
)


@dataclass
class CheckResult:
    id: str
    status: Literal["pass", "fail", "not_run"]
    evidence: list[str] = field(default_factory=list)
    detail: str = ""


@dataclass
class AcceptanceReport:
    mode: Literal["offline", "full"]
    platform: str
    started_at: str
    finished_at: str
    checks: list[CheckResult]
    work_dir: str

    @property
    def overall(self) -> str:
        return "pass" if all(check.status == "pass" for check in self.checks) else "fail"

    def to_wire(self) -> dict[str, object]:
        return {
            "schemaVersion": SCHEMA_VERSION,
            "platform": self.platform,
            "mode": self.mode,
            "startedAt": self.started_at,
            "finishedAt": self.finished_at,
            "checks": [
                {
                    "id": check.id,
                    "status": check.status,
                    "evidence": check.evidence,
                    "detail": check.detail,
                }
                for check in self.checks
            ],
            "overall": self.overall,
            "workDir": self.work_dir,
        }


def _iso(moment: datetime) -> str:
    return moment.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _run(command: Sequence[str], *, cwd: Path, env: dict[str, str] | None = None) -> tuple[int, str]:
    merged = {**os.environ, **(env or {})}
    result = subprocess.run(
        list(command), cwd=str(cwd), env=merged, capture_output=True, text=True, timeout=600
    )
    return result.returncode, (result.stdout or "") + (result.stderr or "")


def find_secret(text: str) -> bool:
    return any(pattern.search(text) for pattern in SECRET_PATTERNS)


class AcceptanceRunner:
    def __init__(self, root: Path, work_dir: Path, mode: Literal["offline", "full"]) -> None:
        self.root = root
        self.work_dir = work_dir
        self.mode = mode
        self.skip_e2e = False
        self.skip_gate = False

    # -- 单项检查 ---------------------------------------------------------
    def check_m1(self) -> CheckResult:
        data_dir = self.work_dir / "demo-data"
        code, output = _run(
            [
                sys.executable,
                "scripts/load_demo.py",
                "--json",
                "--data-dir",
                str(data_dir),
            ],
            cwd=self.root,
            env={"SENTINEL_OFFLINE": "1", "SENTINEL_CLOCK": "2026-11-02T08:35:00Z"},
        )
        evidence = self._write_evidence("m1-demo-load.json", output)
        if code != 0:
            return CheckResult("M-1", "fail", [evidence], "demo load failed")
        try:
            payload = json.loads(output.strip().splitlines()[-1])
            counts = payload["counts"]
        except (ValueError, KeyError, IndexError):
            return CheckResult("M-1", "fail", [evidence], "unreadable demo summary")
        if counts != EXPECTED_COUNTS:
            return CheckResult("M-1", "fail", [evidence], f"counts {counts}")
        return CheckResult("M-1", "pass", [evidence], "6/5/6/6/12/1560")

    def check_m2(self) -> CheckResult:
        if self.skip_e2e:
            return CheckResult("M-2", "not_run", [], "--skip-e2e")
        code, output = _run(
            [
                "pnpm",
                "exec",
                "playwright",
                "test",
                "-c",
                "e2e/acceptance/playwright.config.ts",
                "--reporter=line",
            ],
            cwd=self.root / "apps" / "desktop",
            env={"SENTINEL_OFFLINE": "1"},
        )
        log = self._write_evidence("m2-playwright.log", output)
        results = self.root / "test-results" / "acceptance" / "results.json"
        evidence = [log] + ([self._rel(results)] if results.is_file() else [])
        if code != 0:
            return CheckResult("M-2", "fail", evidence, "playwright acceptance failed")
        return CheckResult("M-2", "pass", evidence, "six pages offline at 1440/1024")

    def check_m3(self) -> CheckResult:
        """密钥泄漏扫描：日志、数据库文本列与 bootstrap/settings 输出。"""
        data_dir = self.work_dir / "demo-data"
        planted = self.work_dir / "planted-secret.log"
        planted.write_text(f"debug: {SECRET_SENTINEL}\n", encoding="utf-8")
        detector = self._scan_secret_sources(data_dir, planted)
        planted.unlink()
        clean = self._scan_secret_sources(data_dir, None)
        evidence = self._write_evidence(
            "m3-secret-scan.json",
            json.dumps({"plantedDetected": detector, "cleanSources": not clean}, ensure_ascii=False),
        )
        if not detector:
            return CheckResult("M-3", "fail", [evidence], "planted secret not detected")
        if clean:
            return CheckResult("M-3", "fail", [evidence], "secret found in real sources")
        return CheckResult("M-3", "pass", [evidence], "no secret in logs/db/bootstrap")

    def _scan_secret_sources(self, data_dir: Path, extra: Path | None) -> bool:
        texts: list[str] = []
        for path in sorted(data_dir.rglob("*")):
            if path.is_file() and path.suffix in {".jsonl", ".log", ".json", ".txt"}:
                texts.append(path.read_text(encoding="utf-8", errors="replace"))
        database = data_dir / "sentinel.duckdb"
        if database.is_file():
            con = Database(database, read_only=True)
            con.open()
            try:
                with con.read() as reader:
                    for table in ("decision", "thesis", "event_doc", "event_file", "setting"):
                        try:
                            reader.execute(f"SELECT * FROM {table}")
                        except Exception:
                            continue
                        for row in reader.fetchall():
                            texts.append(" ".join(str(value) for value in row))
            finally:
                con.close()
        if extra is not None and extra.is_file():
            texts.append(extra.read_text(encoding="utf-8", errors="replace"))
        return any(find_secret(text) for text in texts)

    def check_m4(self) -> CheckResult:
        database = self.work_dir / "demo-data" / "sentinel.duckdb"
        if not database.is_file():
            return CheckResult("M-4", "fail", [], "demo database missing")
        con = Database(database, read_only=True)
        con.open()
        try:
            with con.read() as reader:
                reader.execute(
                    "SELECT decision_id, engine, model_id, question_set_version, evidence_kind"
                    " FROM decision"
                )
                rows = reader.fetchall()
        finally:
            con.close()
        evidence = self._write_evidence(
            "m4-decisions.json", json.dumps([list(map(str, row)) for row in rows], ensure_ascii=False)
        )
        if len(rows) != 12:
            return CheckResult("M-4", "fail", [evidence], f"decision rows {len(rows)}")
        for row in rows:
            if any(value in (None, "") for value in row[1:]) or row[1] not in WHITELIST_ENGINE:
                return CheckResult("M-4", "fail", [evidence], f"invalid provenance {row[0]}")
            if row[4] not in WHITELIST_EVIDENCE:
                return CheckResult("M-4", "fail", [evidence], f"invalid evidence {row[0]}")
        return CheckResult("M-4", "pass", [evidence], "12 decisions with provenance")

    def check_m5(self) -> CheckResult:
        out = self.work_dir / "eval"
        code, output = _run(
            [
                sys.executable,
                "scripts/eval.py",
                "--mode",
                "fixture",
                "--replay",
                "core/tests/fixtures/eval/cassettes",
                "--split",
                "test",
                "--out",
                str(out),
            ],
            cwd=self.root,
            env={"SENTINEL_OFFLINE": "1"},
        )
        log = self._write_evidence("m5-eval.log", output)
        report = out / "report.json"
        if code != 0 or not report.is_file():
            return CheckResult("M-5", "fail", [log], "replay failed or report missing")
        payload = json.loads(report.read_text(encoding="utf-8"))
        evidence = [log, self._rel(report)]
        if payload.get("samples") != 30 or not isinstance(payload.get("strict", {}).get("f1"), float):
            return CheckResult("M-5", "fail", evidence, "report incomplete")
        return CheckResult("M-5", "pass", evidence, "synthetic replay report")

    def check_m6(self) -> CheckResult:
        """缺证据的阳性判定不得进入清单。"""
        from sentinel.app.status import RuntimeStatus
        from sentinel.scan.pending import InboxService

        database = self.work_dir / "demo-data" / "sentinel.duckdb"
        if not database.is_file():
            return CheckResult("M-6", "fail", [], "demo database missing")
        con = Database(database)
        con.open()
        try:
            with con.write() as tx:
                tx.execute(
                    "INSERT INTO decision SELECT * REPLACE ('M6-MISSING-EVIDENCE' AS decision_id,"
                    " 'M6-MISSING-EVIDENCE-CACHE' AS cache_key) FROM decision"
                    " WHERE decision_id=(SELECT min(decision_id) FROM decision)"
                )
                tx.execute(
                    "UPDATE decision SET evidence_kind=NULL, evidence_start=NULL,"
                    " evidence_end=NULL WHERE decision_id='M6-MISSING-EVIDENCE'"
                )
            status = RuntimeStatus(engine=_UnconfiguredEngine(), offline=True)  # type: ignore[arg-type]
            page = InboxService(con, status_provider=status).list_inbox()
            ids = {item.decision_id for item in page.items + page.uncertain}
        finally:
            con.close()
        evidence = self._write_evidence(
            "m6-missing-evidence.json",
            json.dumps({"inInbox": "M6-MISSING-EVIDENCE" in ids, "count": len(ids)}),
        )
        if "M6-MISSING-EVIDENCE" in ids:
            return CheckResult("M-6", "fail", [evidence], "missing evidence leaked into inbox")
        return CheckResult("M-6", "pass", [evidence], "evidence-less decision hidden")

    def check_m7(self) -> CheckResult:
        if self.skip_gate:
            return CheckResult("M-7", "not_run", [], "--skip-gate")
        tmp = self.work_dir / "tmp"
        tmp.mkdir(parents=True, exist_ok=True)
        code, output = _run(
            [sys.executable, "scripts/check.py"],
            cwd=self.root,
            env={"SENTINEL_OFFLINE": "1", "TMPDIR": str(tmp)},
        )
        log = self._write_evidence("m7-check.log", output)
        if code != 0:
            return CheckResult("M-7", "fail", [log], "scripts/check.py failed")
        return CheckResult("M-7", "pass", [log], "gate passed")

    def check_m8(self) -> CheckResult:
        if self.mode != "full":
            return CheckResult("M-8", "not_run", [], "offline mode cannot verify real JEVDB")
        extension = os.environ.get("SENTINEL_JEVDB_PATH")
        key = os.environ.get("JEV_API_KEY")
        missing = [name for name, value in (("SENTINEL_JEVDB_PATH", extension), ("JEV_API_KEY", key)) if not value]
        if missing:
            evidence = self._write_evidence(
                "m8-blocked.json", json.dumps({"missing": missing, "reason": "CONFIG_REQUIRED"})
            )
            return CheckResult("M-8", "fail", [evidence], f"missing {', '.join(missing)}")
        path = Path(extension or "")
        if not path.is_file():
            evidence = self._write_evidence(
                "m8-blocked.json", json.dumps({"missing": ["extension"], "path": str(path)})
            )
            return CheckResult("M-8", "fail", [evidence], "extension file missing")
        return CheckResult(
            "M-8",
            "fail",
            [],
            "real JEVDB scan not executed by this runner; run scripts/probe_jevdb.py",
        )

    # -- 编排 -------------------------------------------------------------
    def preflight(self) -> list[CheckResult]:
        missing = [name for name in ("uv", "pnpm") if shutil.which(name) is None]
        if missing:
            return [CheckResult("M-1", "fail", [], f"missing tools: {missing}")]
        return []

    def run(self) -> AcceptanceReport:
        started = datetime.now(UTC)
        checks = self.preflight()
        if not checks:
            checks = [
                self.check_m1(),
                self.check_m2(),
                self.check_m3(),
                self.check_m4(),
                self.check_m5(),
                self.check_m6(),
                self.check_m7(),
                self.check_m8(),
            ]
        return AcceptanceReport(
            mode=self.mode,
            platform=_platform_name(),
            started_at=_iso(started),
            finished_at=_iso(datetime.now(UTC)),
            checks=checks,
            work_dir=str(self.work_dir),
        )

    def _rel(self, path: Path) -> str:
        try:
            return str(path.relative_to(self.root))
        except ValueError:
            return str(path)

    def _write_evidence(self, name: str, content: str) -> str:
        directory = self.work_dir / "artifacts"
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / name
        path.write_text(content, encoding="utf-8")
        try:
            return str(path.relative_to(self.work_dir))
        except ValueError:
            return str(path)


class _UnconfiguredEngine:
    def health(self) -> tuple[None, str]:
        return None, "unconfigured"


def _platform_name() -> str:
    import platform

    return "macos" if platform.system() == "Darwin" else "windows"


def write_report(report: AcceptanceReport, out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    payload = report.to_wire()
    path = out_dir / "acceptance.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    lines = [
        "# MVP-0 验收报告",
        "",
        f"- 模式：{report.mode}",
        f"- 平台：{report.platform}",
        f"- 总体：{report.overall.upper()}",
        f"- 数据目录：`{report.work_dir}`",
        "",
        "| 项 | 状态 | 证据 | 说明 |",
        "|---|---|---|---|",
    ]
    for check in report.checks:
        lines.append(
            f"| {check.id} | {check.status} | {', '.join(check.evidence) or '—'} | {check.detail} |"
        )
    (out_dir / "summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def self_test() -> int:
    """扫描器与缺证据规则的自检；不启动核心、不联网。"""
    failures: list[str] = []
    if not find_secret(f"line {SECRET_SENTINEL} line"):
        failures.append("planted sentinel not detected")
    if not find_secret("Authorization: Bearer abcdefghijklmnopqrstuvwxyz012345"):
        failures.append("bearer token not detected")
    if find_secret("nothing sensitive here"):
        failures.append("false positive")
    schema = json.loads((ROOT / "apps/desktop/e2e/acceptance/report.schema.json").read_text())
    sample = {
        "schemaVersion": "1",
        "platform": "macos",
        "mode": "offline",
        "startedAt": "2026-11-02T08:35:00Z",
        "finishedAt": "2026-11-02T08:36:00Z",
        "checks": [
            {"id": check, "status": "not_run", "evidence": [], "detail": ""} for check in CHECK_IDS
        ],
        "overall": "fail",
        "workDir": "/tmp/x",
    }
    try:
        import jsonschema

        jsonschema.validate(sample, schema)
    except ImportError:
        pass
    except Exception as exc:  # pragma: no cover - schema drift
        failures.append(f"schema: {exc}")
    if failures:
        print("SELF-TEST FAIL " + "; ".join(failures))
        return 1
    print("SELF-TEST PASS")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="MVP-0 acceptance runner")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--offline", action="store_true", help="只做开发回归（默认）")
    group.add_argument("--full", action="store_true", help="包含真实 JEVDB 验证")
    parser.add_argument("--report-dir", type=Path, default=ROOT / "test-results" / "acceptance")
    parser.add_argument("--skip-e2e", action="store_true")
    parser.add_argument("--skip-gate", action="store_true", help="跳过 scripts/check.py（仅本地快速验证）")
    parser.add_argument("--work-dir", type=Path, help="覆盖临时工作目录")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args(argv)
    if args.self_test:
        return self_test()
    mode: Literal["offline", "full"] = "full" if args.full else "offline"
    started = time.monotonic()
    stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    work_dir = args.work_dir or (ROOT / ".tmp-pytest" / f"acceptance-{stamp}")
    work_dir.mkdir(parents=True, exist_ok=True)
    runner = AcceptanceRunner(ROOT, work_dir, mode)
    runner.skip_e2e = bool(args.skip_e2e)
    runner.skip_gate = bool(args.skip_gate)
    report = runner.run()
    out = args.report_dir
    write_report(report, out)
    passed = sum(1 for check in report.checks if check.status == "pass")
    elapsed = time.monotonic() - started
    if args.json:
        print(json.dumps(report.to_wire(), ensure_ascii=False))
    print(f"ACCEPTANCE {report.overall.upper()} {passed}/8 ({elapsed:.0f}s) -> {out}")
    if elapsed > MAX_ACCEPTANCE_SECONDS:
        print("acceptance exceeded 15 minutes", file=sys.stderr)
        return 1
    return 0 if report.overall == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
