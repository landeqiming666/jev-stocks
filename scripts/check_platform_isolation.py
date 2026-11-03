#!/usr/bin/env python3
"""平台隔离检查。仅用标准库，兼容 Python 3.9。

平台判断只允许出现在平台层、脚本包装与测试的显式平台目录里；其余源码出现
sys.platform / cfg(target_os) / process.platform 等一律报错。
"""
from __future__ import annotations

import argparse
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Optional, Sequence, Tuple


@dataclass(frozen=True)
class Finding:
    path: str
    line: int
    message: str


SOURCE_SUFFIXES = {".py", ".rs", ".ts", ".tsx", ".js", ".jsx"}
SKIP_DIRS = {
    ".git",
    ".dev-data",
    "node_modules",
    "target",
    "dist",
    ".venv",
    "__pycache__",
    ".kiro",
    "docs",
    "design",
    "contracts",
}
ALLOWED_PREFIXES = (
    "core/sentinel/platform/",
    "apps/desktop/src-tauri/src/platform/",
    "core/tests/platform/",
    "scripts/",
)

PYTHON_PATTERNS = [
    re.compile(r"\bsys\.platform\b"),
    re.compile(r"\bos\.name\b"),
    re.compile(r"\bplatform\.(?:system|win32_ver|mac_ver)\b"),
    re.compile(r"from\s+sys\s+import\s+.*\bplatform\b"),
]
RUST_PATTERNS = [
    re.compile(r"\bcfg!?\s*\(\s*(?:target_os|windows|unix|target_family)"),
    re.compile(r"#\[cfg\(.*target_os"),
]
WEB_PATTERNS = [
    re.compile(r"\bprocess\.platform\b"),
    re.compile(r"\bnavigator\.platform\b"),
    re.compile(r"\bnavigator\.userAgent(?:Data)?\b"),
]


def _patterns(suffix: str) -> Sequence[re.Pattern[str]]:
    if suffix == ".py":
        return PYTHON_PATTERNS
    if suffix == ".rs":
        return RUST_PATTERNS
    return WEB_PATTERNS


def _iter_sources(root: Path) -> Iterable[Path]:
    for directory, folders, files in os.walk(root):
        folders[:] = sorted(name for name in folders if name not in SKIP_DIRS and name != "generated")
        for name in sorted(files):
            path = Path(directory) / name
            if path.is_file() and path.suffix in SOURCE_SUFFIXES:
                yield path


def _is_allowed(relative: str) -> bool:
    return relative == "vendors/jevdb/build.py" or any(
        relative.startswith(prefix) for prefix in ALLOWED_PREFIXES
    )


def _is_fixture_guard(relative: str, line: str) -> bool:
    return relative == "apps/desktop/src-tauri/tests/bridge.rs" and bool(
        re.fullmatch(r"\s*#\[cfg\(unix\)\]\s*", line)
    )


def _script_pair_findings(root: Path) -> List[Finding]:
    scripts = root / "scripts"
    findings: List[Finding] = []
    if not scripts.is_dir():
        return findings
    for path in sorted(scripts.glob("*.sh")):
        if path.stem.startswith("_"):
            continue
        counterpart = path.with_suffix(".ps1")
        if not counterpart.exists():
            findings.append(
                Finding(path.relative_to(root).as_posix(), 0, "缺少成对脚本: %s" % counterpart.name)
            )
    for path in sorted(scripts.glob("*.ps1")):
        if path.stem.startswith("_"):
            continue
        counterpart = path.with_suffix(".sh")
        if not counterpart.exists():
            findings.append(
                Finding(path.relative_to(root).as_posix(), 0, "缺少成对脚本: %s" % counterpart.name)
            )
    return findings


def scan(root: Path) -> List[Finding]:
    root = Path(root)
    findings: List[Finding] = []
    for path in _iter_sources(root):
        relative = path.relative_to(root).as_posix()
        if _is_allowed(relative):
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            findings.append(Finding(relative, 1, "文件不是 UTF-8 编码，无法检查"))
            continue
        patterns = _patterns(path.suffix)
        for lineno, line in enumerate(text.splitlines(), 1):
            if _is_fixture_guard(relative, line):
                continue
            for pattern in patterns:
                if pattern.search(line):
                    findings.append(
                        Finding(
                            relative,
                            lineno,
                            "平台判断只允许出现在平台层: %s" % line.strip(),
                        )
                    )
                    break
    findings.extend(_script_pair_findings(root))
    return findings


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="投资逻辑哨兵：平台隔离检查")
    parser.add_argument("root", nargs="?", help="仓库根目录，默认当前脚本的上一级")
    args = parser.parse_args(argv)
    root = Path(args.root).resolve() if args.root else Path(__file__).resolve().parents[1]
    findings = scan(root)
    for finding in findings:
        print("%s:%d: %s" % (finding.path, finding.line, finding.message))
    if findings:
        print("平台隔离检查失败：%d 处发现" % len(findings))
        return 1
    print("平台隔离检查通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
