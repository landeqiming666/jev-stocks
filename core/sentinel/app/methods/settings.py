"""settings / secrets 适配器：注册 C-04 的七个方法。"""

from __future__ import annotations

from sentinel.rpc import Dispatcher
from sentinel.settings import register as register_settings

from ..container import AppContainer


def register(dispatcher: Dispatcher, container: AppContainer) -> None:
    register_settings(
        dispatcher,
        container.settings,
        container.secrets,
        container.db,
        container.platform_name,
        container.engine.snapshot,
        container.probe,
        change_guard=container.change_guard,
    )


__all__ = ["register"]
