"""inbox 适配器：inbox.list 与三个 decision 方法。"""

from __future__ import annotations

from sentinel.rpc import Dispatcher
from sentinel.scan.pending import register_handlers

from ..container import AppContainer


def register(dispatcher: Dispatcher, container: AppContainer) -> None:
    register_handlers(dispatcher, container.inbox)


__all__ = ["register"]
