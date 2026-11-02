#!/usr/bin/env python3
"""工具链体检。仅用标准库，兼容 Python 3.9。"""
from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, List, Optional, Sequence, Tuple


@dataclass(frozen=True)
class ToolStatus:
    name: str
    version: str
    required: bool
    present: bool
    hint: str


ToolSpec = Tuple[str, List[str], bool, str]

TOOLS: List[ToolSpec] = [
    ("git", ["git", "--version"], True, "安装 Xcode 命令行工具或 git-scm.com"),
    ("python3", [sys.executable, "--version"], True, "运行脚本需要 Python >= 3.9"),
    ("uv", ["uv", "--version"], True, "https://docs.astral.sh/uv/"),
    ("node", ["node", "--version"], True, "版本需与 .node-version 的主版本一致"),
    ("pnpm", ["pnpm", "--version"], True, "npm install -g pnpm"),
    ("rustc", ["rustc", "--version"], True, "https://rustup.rs"),
    ("cargo", ["cargo", "--version"], True, "https://rustup.rs"),
    ("cmake", ["cmake", "--version"], False, "G0-JEVDB 构建 JEVDB 时需要"),
    ("ninja", ["ninja", "--version"], False, "G0-JEVDB 构建 JEVDB 时需要"),
]


def collect(
    run: Optional[Callable[..., object]] = None,
    which: Optional[Callable[[str], Optional[str]]] = None,
) -> List[ToolStatus]:
    runner = run or subprocess.run
    finder = which or shutil.which
    statuses: List[ToolStatus] = []
    for name, command, required, hint in TOOLS:
        if finder(command[0]) is None:
            statuses.append(ToolStatus(name, "—", required, False, hint))
            continue
        try:
            result = runner(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
            )
            output = getattr(result, "stdout", "") or ""
            first_line = output.splitlines()[0].strip() if output.splitlines() else "未知"
            code = getattr(result, "returncode", 0)
            if code != 0:
                first_line = "未知"
        except (OSError, subprocess.SubprocessError):
            first_line = "未知"
        statuses.append(ToolStatus(name, first_line, required, True, hint))
    return statuses


def format_table(statuses: Sequence[ToolStatus]) -> str:
    rows = [("工具", "版本", "必需", "状态")]
    for status in statuses:
        rows.append(
            (
                status.name,
                status.version,
                "是" if status.required else "否",
                "OK" if status.present else "缺失",
            )
        )
    widths = [max(len(row[i]) for row in rows) for i in range(4)]
    lines = []
    for index, row in enumerate(rows):
        lines.append(" | ".join(cell.ljust(widths[i]) for i, cell in enumerate(row)))
        if index == 0:
            lines.append("-+-".join("-" * width for width in widths))
    return "\n".join(lines)


def _node_major_warning(statuses: Sequence[ToolStatus], root: Path) -> Optional[str]:
    node = next((item for item in statuses if item.name == "node"), None)
    if node is None or not node.present:
        return None
    version_file = root / ".node-version"
    if not version_file.is_file():
        return None
    expected_text = version_file.read_text(encoding="utf-8").strip()
    expected_match = re.search(r"\d+", expected_text)
    actual_match = re.search(r"v?(\d+)", node.version)
    if not expected_match or not actual_match:
        return None
    expected, actual = expected_match.group(0), actual_match.group(1)
    if expected != actual:
        return "WARN node 主版本与 .node-version 不一致：期望 %s，实际 %s" % (expected, actual)
    return None


def main(
    argv: Optional[List[str]] = None,
    run: Optional[Callable[..., object]] = None,
    which: Optional[Callable[[str], Optional[str]]] = None,
    root: Optional[Path] = None,
) -> int:
    parser = argparse.ArgumentParser(description="投资逻辑哨兵：工具链体检")
    parser.parse_args(argv)
    base = Path(root) if root is not None else Path(__file__).resolve().parents[1]
    statuses = collect(run=run, which=which)
    print(format_table(statuses))
    warning = _node_major_warning(statuses, base)
    if warning:
        print(warning)
    missing = [item for item in statuses if not item.present]
    if missing:
        print("")
        for item in missing:
            print("缺少 %s：%s" % (item.name, item.hint))
    required_missing = [item for item in missing if item.required]
    return 1 if required_missing else 0


if __name__ == "__main__":
    sys.exit(main())
