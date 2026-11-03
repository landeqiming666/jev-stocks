#!/usr/bin/env python3
"""一键检查。仅用标准库，兼容 Python 3.9。

用法：
    scripts/check.sh                 运行全部已就绪的检查
    scripts/check.sh --only py-test  只运行指定步骤（可重复）
    scripts/check.sh --e2e           额外运行 Playwright
    scripts/check.sh --list          只列出步骤和依赖文件是否存在
"""
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, List, Optional, Sequence, Set


@dataclass(frozen=True)
class Step:
    name: str
    command: List[str]
    cwd: str
    requires: List[str]
    needs_flag: Optional[str] = None


STEPS: List[Step] = [
    Step("docs", ["{python}", "scripts/check_docs.py"], ".", ["docs"]),
    Step(
        "isolation",
        ["{python}", "scripts/check_platform_isolation.py"],
        ".",
        ["scripts/check_platform_isolation.py"],
    ),
    Step(
        "scripts-test",
        ["uv", "run", "--project", "core", "python", "-m", "pytest", "-q", "scripts/tests"],
        ".",
        ["scripts/tests", "core/pyproject.toml"],
    ),
    Step("contrast", ["{python}", "scripts/check_contrast.py"], ".", ["scripts/check_contrast.py"]),
    Step("proto", ["{python}", "scripts/check_proto.py"], ".", ["scripts/check_proto.py"]),
    Step(
        "generated-ts",
        ["{python}", "scripts/gen_ts_types.py", "--check"],
        ".",
        ["scripts/gen_ts_types.py"],
    ),
    Step(
        "generated-proto",
        ["{python}", "scripts/gen_proto_mock.py", "--check"],
        ".",
        ["scripts/gen_proto_mock.py"],
    ),
    Step("py-lint", ["uv", "run", "ruff", "check", "."], "core", ["core/pyproject.toml"]),
    Step("py-format", ["uv", "run", "ruff", "format", "--check", "."], "core", ["core/pyproject.toml"]),
    Step("py-types", ["uv", "run", "mypy", "sentinel"], "core", ["core/pyproject.toml"]),
    Step("py-test", ["uv", "run", "python", "-m", "pytest", "-q"], "core", ["core/pyproject.toml"]),
    Step("web-lint", ["pnpm", "lint"], "apps/desktop", ["apps/desktop/package.json"]),
    Step("web-types", ["pnpm", "typecheck"], "apps/desktop", ["apps/desktop/package.json"]),
    Step("web-test", ["pnpm", "test"], "apps/desktop", ["apps/desktop/package.json"]),
    Step(
        "rust-fmt",
        ["cargo", "fmt", "--check"],
        "apps/desktop/src-tauri",
        ["apps/desktop/src-tauri/Cargo.toml"],
    ),
    Step(
        "rust-clippy",
        ["cargo", "clippy", "--all-targets", "--", "-D", "warnings"],
        "apps/desktop/src-tauri",
        ["apps/desktop/src-tauri/Cargo.toml"],
    ),
    Step(
        "e2e",
        ["pnpm", "e2e"],
        "apps/desktop",
        ["apps/desktop/playwright.config.ts"],
        needs_flag="e2e",
    ),
]


def _resolve_python(command: Sequence[str]) -> List[str]:
    return [sys.executable if part == "{python}" else part for part in command]


def run_steps(
    steps: List[Step],
    root: Path,
    only: Optional[List[str]] = None,
    flags: Optional[Set[str]] = None,
    runner: Optional[Callable[..., object]] = None,
    which: Optional[Callable[[str], Optional[str]]] = None,
    out: Callable[[str], None] = print,
) -> int:
    """按顺序运行步骤；全部 PASS/SKIP 返回 0，有 FAIL 返回 1。"""
    run = runner or subprocess.run
    find = which or shutil.which
    enabled = set(flags or ())
    selected = set(only) if only else None
    passed = failed = skipped = 0

    for step in steps:
        if selected is not None and step.name not in selected:
            out("SKIP %s (未选中)" % step.name)
            skipped += 1
            continue
        if step.needs_flag and step.needs_flag not in enabled:
            out("SKIP %s (需要 --%s)" % (step.name, step.needs_flag))
            skipped += 1
            continue
        missing = [item for item in step.requires if not (root / item).exists()]
        if missing:
            out("SKIP %s (缺少 %s)" % (step.name, missing[0]))
            skipped += 1
            continue

        argv = _resolve_python(step.command)
        executable = find(argv[0])
        if executable is None:
            out(
                "FAIL %s (找不到命令 %s，运行 scripts/doctor.py 查看缺什么)"
                % (step.name, argv[0])
            )
            failed += 1
            continue
        argv[0] = executable

        try:
            result = run(argv, cwd=str(root / step.cwd))
        except OSError as exc:
            out("FAIL %s (无法执行: %s)" % (step.name, exc))
            failed += 1
            continue

        if getattr(result, "returncode", 1) != 0:
            out("FAIL %s (退出码 %s)" % (step.name, getattr(result, "returncode", "?")))
            failed += 1
        else:
            out("PASS %s" % step.name)
            passed += 1

    out("通过 %d · 失败 %d · 跳过 %d" % (passed, failed, skipped))
    return 1 if failed else 0


def list_steps(steps: List[Step], root: Path, out: Callable[[str], None] = print) -> int:
    for step in steps:
        details = []
        for item in step.requires:
            state = "存在" if (root / item).exists() else "缺少"
            details.append("%s(%s)" % (item, state))
        if step.needs_flag:
            details.append("需要 --%s" % step.needs_flag)
        out("%s  %s" % (step.name, ", ".join(details) if details else "-"))
    return 0


def main(
    argv: Optional[List[str]] = None,
    steps: Optional[List[Step]] = None,
    root: Optional[Path] = None,
    runner: Optional[Callable[..., object]] = None,
    which: Optional[Callable[[str], Optional[str]]] = None,
    out: Callable[[str], None] = print,
) -> int:
    parser = argparse.ArgumentParser(description="投资逻辑哨兵：一键检查")
    parser.add_argument("--only", action="append", metavar="NAME", help="只运行指定步骤，可重复")
    parser.add_argument("--e2e", action="store_true", help="额外运行 Playwright 端到端测试")
    parser.add_argument("--list", action="store_true", help="只列出步骤")
    args = parser.parse_args(argv)

    active = steps if steps is not None else STEPS
    base = root if root is not None else Path(__file__).resolve().parents[1]
    if args.list:
        return list_steps(active, base, out=out)
    flags = {"e2e"} if args.e2e else set()
    return run_steps(active, base, only=args.only, flags=flags, runner=runner, which=which, out=out)


if __name__ == "__main__":
    sys.exit(main())
