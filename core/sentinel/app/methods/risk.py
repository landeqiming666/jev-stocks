"""risk 适配器：risk.compute。"""

from __future__ import annotations

from sentinel.quant import register_handlers
from sentinel.rpc import Dispatcher

from ..container import AppContainer


def register(dispatcher: Dispatcher, container: AppContainer) -> None:
    register_handlers(dispatcher, container.risk)


__all__ = ["register"]
