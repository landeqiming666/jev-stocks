"""进程参数解析：唯一允许读取命令行的位置。"""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import NoReturn

LOG_LEVELS = ("DEBUG", "INFO", "WARN", "ERROR")
EXIT_USAGE = 2


class UsageError(Exception):
    """参数错误：由入口打印中文提示并以退出码 2 结束。"""


@dataclass(frozen=True)
class AppArgs:
    data_dir: Path
    resource_dir: Path
    parent_pid: int | None = None
    log_level: str = "INFO"


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> NoReturn:
        raise UsageError(message)


def _parser() -> argparse.ArgumentParser:
    parser = _Parser(
        prog="python -m sentinel", add_help=True, description="Thesis Sentinel 核心进程"
    )
    parser.add_argument("--data-dir", required=True)
    parser.add_argument("--resource-dir", required=True)
    parser.add_argument("--parent-pid", type=int, default=None)
    parser.add_argument("--log-level", default="INFO")
    return parser


def _writable(path: Path) -> bool:
    try:
        path.mkdir(parents=True, exist_ok=True)
        probe = path / ".write-probe"
        probe.write_text("", encoding="utf-8")
        probe.unlink()
        return True
    except OSError:
        return False


def parse_args(argv: Sequence[str] | None = None) -> AppArgs:
    try:
        namespace = _parser().parse_args(argv)
    except SystemExit as exc:
        if exc.code == 0:  # --help 已打印，按正常退出处理
            raise
        raise UsageError("无法识别的启动参数。") from exc

    data_dir = Path(str(namespace.data_dir)).expanduser()
    resource_dir = Path(str(namespace.resource_dir)).expanduser()
    level = str(namespace.log_level).upper()
    if level == "WARNING":
        level = "WARN"
    if level not in LOG_LEVELS:
        raise UsageError("日志级别必须是 DEBUG、INFO、WARN 或 ERROR。")
    parent_pid = namespace.parent_pid
    if parent_pid is not None and (type(parent_pid) is not int or parent_pid <= 0):
        raise UsageError("--parent-pid 必须是正整数。")
    if not _writable(data_dir):
        raise UsageError("无法写入应用数据目录。")
    if not resource_dir.is_dir():
        raise UsageError("找不到资源目录。")
    return AppArgs(data_dir.resolve(), resource_dir.resolve(), parent_pid, level)


__all__ = ["EXIT_USAGE", "LOG_LEVELS", "AppArgs", "UsageError", "parse_args"]
