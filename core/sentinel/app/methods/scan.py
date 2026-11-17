"""scan 适配器：六个手动扫描方法。"""

from __future__ import annotations

from sentinel.rpc import Dispatcher
from sentinel.scan import register_handlers

from ..container import AppContainer


def register(dispatcher: Dispatcher, container: AppContainer) -> None:
    register_handlers(dispatcher, container.scan)


__all__ = ["register"]
