"""portfolio 适配器：holdings 与 thesis 九个方法。"""

from __future__ import annotations

from sentinel.portfolio import register_handlers
from sentinel.rpc import Dispatcher

from ..container import AppContainer


def register(dispatcher: Dispatcher, container: AppContainer) -> None:
    register_handlers(dispatcher, container.portfolio)


__all__ = ["register"]
