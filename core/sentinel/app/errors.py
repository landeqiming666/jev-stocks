"""组合根自有的启动错误；不进入 RPC 线上错误对象。"""

from __future__ import annotations


class StartupError(Exception):
    """启动阶段失败；code 决定进程退出码。"""

    MIGRATION_FAILED = "MIGRATION_FAILED"
    INCOMPLETE = "INCOMPLETE"

    def __init__(self, code: str, detail: str = "") -> None:
        super().__init__(code)
        self.code, self.detail = code, detail


__all__ = ["StartupError"]
