#!/usr/bin/env python3
"""启动开发模式。仅用标准库，兼容 Python 3.9。

开发数据目录固定在仓库内的 .dev-data，绝不触碰真实用户数据目录。
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Callable, List, Optional


def main(
    argv: Optional[List[str]] = None,
    root: Optional[Path] = None,
    runner: Optional[Callable[..., object]] = None,
    which: Optional[Callable[[str], Optional[str]]] = None,
) -> int:
    run = runner or subprocess.run
    find = which or shutil.which
    base = Path(root) if root is not None else Path(__file__).resolve().parents[1]

    if not os.environ.get("SENTINEL_DATA_DIR"):
        data_dir = base / ".dev-data"
        data_dir.mkdir(parents=True, exist_ok=True)
        os.environ["SENTINEL_DATA_DIR"] = str(data_dir)
        print("开发数据目录: %s" % data_dir)

    executable = find("pnpm")
    if executable is None:
        print("找不到 pnpm，运行 scripts/doctor.py 查看缺什么")
        return 1

    result = run([executable, "tauri", "dev"], cwd=str(base / "apps" / "desktop"))
    return int(getattr(result, "returncode", 1))


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
