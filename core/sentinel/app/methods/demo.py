"""demo 适配器：demo.load 与 demo.clear。"""

from __future__ import annotations

from sentinel.demo.rpc import register_handlers
from sentinel.rpc import Dispatcher

from ..container import AppContainer


def register(dispatcher: Dispatcher, container: AppContainer) -> None:
    register_handlers(dispatcher, container.demo)


__all__ = ["register"]
