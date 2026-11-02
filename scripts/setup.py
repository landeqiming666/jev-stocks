#!/usr/bin/env python3
"""安装全部依赖。仅用标准库，兼容 Python 3.9。

每个新的 git worktree 都要先运行一次。目录不存在时打印 SKIP，不算失败。
"""
from __future__ import annotations

import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, List, Optional


@dataclass(frozen=True)
class SetupStep:
    name: str
    command: List[str]
    cwd: str
    requires: str


STEPS: List[SetupStep] = [
    SetupStep("python", ["uv", "sync"], "core", "core/pyproject.toml"),
    SetupStep("web", ["pnpm", "install", "--frozen-lockfile"], "apps/desktop", "apps/desktop/package.json"),
    SetupStep("rust", ["cargo", "fetch"], "apps/desktop/src-tauri", "apps/desktop/src-tauri/Cargo.toml"),
]


def main(
    argv: Optional[List[str]] = None,
    root: Optional[Path] = None,
    runner: Optional[Callable[..., object]] = None,
    which: Optional[Callable[[str], Optional[str]]] = None,
) -> int:
    run = runner or subprocess.run
    find = which or shutil.which
    base = Path(root) if root is not None else Path(__file__).resolve().parents[1]
    failed = False

    for step in STEPS:
        if not (base / step.requires).exists():
            print("SKIP %s (缺少 %s)" % (step.name, step.requires))
            continue
        executable = find(step.command[0])
        if executable is None:
            print("FAIL %s (找不到命令 %s)" % (step.name, step.command[0]))
            failed = True
            continue
        argv_step = [executable] + step.command[1:]
        print("RUN  %s: %s" % (step.name, " ".join(step.command)))
        result = run(argv_step, cwd=str(base / step.cwd))
        code = getattr(result, "returncode", 1)
        if code != 0:
            print("FAIL %s (退出码 %s)" % (step.name, code))
            failed = True

    if failed:
        print("安装失败。先运行 scripts/doctor.py 查看缺什么。")
        return 1
    print("安装完成。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
