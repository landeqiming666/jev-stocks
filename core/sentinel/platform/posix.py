"""macOS 平台实现。"""

from __future__ import annotations

import fcntl
import os
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Literal

from . import AlreadyRunning


def name() -> Literal["macos", "windows"]:
    return "macos"


def default_data_dir() -> Path:
    return Path.home() / "Library" / "Application Support" / "Sentinel"


def is_process_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        # 进程存在，只是属于别的用户。
        return True
    return True


@contextmanager
def file_lock(path: Path) -> Iterator[None]:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = path.open("a+")
    try:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise AlreadyRunning("另一个核心进程正在使用这份数据") from exc
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
    finally:
        handle.close()


def harden_permissions(path: Path) -> None:
    mode = 0o700 if path.is_dir() else 0o600
    os.chmod(path, mode)
