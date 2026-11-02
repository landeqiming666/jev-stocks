"""平台层接口与按平台选择实现。

这是核心代码里唯一允许出现 sys.platform 的地方之一（ADR-016）。
"""

from __future__ import annotations

import sys

__all__ = [
    "AlreadyRunning",
    "default_data_dir",
    "file_lock",
    "harden_permissions",
    "is_process_alive",
    "name",
]


class AlreadyRunning(Exception):
    """文件锁已被另一个核心进程持有。"""


if sys.platform == "darwin":
    from .posix import default_data_dir as default_data_dir
    from .posix import file_lock as file_lock
    from .posix import harden_permissions as harden_permissions
    from .posix import is_process_alive as is_process_alive
    from .posix import name as name
elif sys.platform == "win32":
    from .windows import default_data_dir as default_data_dir
    from .windows import file_lock as file_lock
    from .windows import harden_permissions as harden_permissions
    from .windows import is_process_alive as is_process_alive
    from .windows import name as name
else:
    raise RuntimeError(f"不支持的平台: {sys.platform}")
