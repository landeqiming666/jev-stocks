"""paper 适配器：模拟账户与订单八个方法。"""

from __future__ import annotations

from sentinel.rpc import Dispatcher
from sentinel.trading import register_handlers

from ..container import AppContainer


def register(dispatcher: Dispatcher, container: AppContainer) -> None:
    register_handlers(dispatcher, container.paper)


__all__ = ["register"]
