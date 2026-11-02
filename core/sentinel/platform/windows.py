"""Windows 平台占位实现：由 W-01 重写。"""

from __future__ import annotations

from contextlib import AbstractContextManager
from pathlib import Path
from typing import Literal


def name() -> Literal["macos", "windows"]:
    return "windows"


def default_data_dir() -> Path:
    raise NotImplementedError("W-01")


def is_process_alive(pid: int) -> bool:
    raise NotImplementedError("W-01")


def file_lock(path: Path) -> AbstractContextManager[None]:
    raise NotImplementedError("W-01")


def harden_permissions(path: Path) -> None:
    raise NotImplementedError("W-01")
