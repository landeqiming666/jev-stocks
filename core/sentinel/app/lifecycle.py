"""启动恢复与关闭顺序；失败只记录，不掩盖进程退出码。"""

from __future__ import annotations

import logging

from sentinel.logging_setup import get_logger, log_event
from sentinel.rpc.server import RpcServer

from .container import AppContainer

_LOG = get_logger(__name__)


def startup(container: AppContainer) -> int:
    """把遗留的 queued/running 标为 interrupted；不自动开始扫描。"""
    try:
        recovered = container.scan.recover_on_startup()
    except Exception:
        log_event(
            _LOG,
            logging.WARNING,
            event="app.recovery_failed",
            error_code="INTERNAL",
        )
        return 0
    if recovered:
        log_event(
            _LOG,
            logging.INFO,
            event="app.recovered_runs",
            error_code=None,
            runs=recovered,
        )
    return recovered


def shutdown(container: AppContainer, server: RpcServer | None = None) -> None:
    if server is not None:
        try:
            server.stop()
        except Exception:
            log_event(_LOG, logging.WARNING, event="app.server_stop_failed", error_code="INTERNAL")
    try:
        container.close()
    except Exception:
        log_event(_LOG, logging.WARNING, event="app.close_failed", error_code="INTERNAL")


__all__ = ["shutdown", "startup"]
