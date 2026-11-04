"""处理器注册：显式装配 38 个业务方法，并校验数量与方法名集合。"""

from __future__ import annotations

from sentinel.errors import InternalError
from sentinel.rpc import Dispatcher

from . import methods
from .container import AppContainer

EXPECTED_BUSINESS_METHOD_COUNT = 38
METHOD_MODULES = ("settings", "markets", "portfolio", "inbox", "scan", "paper", "risk", "demo")

BUSINESS_METHODS = frozenset(
    {
        "app.bootstrap",
        "settings.get",
        "settings.update",
        "settings.testConnection",
        "secrets.set",
        "secrets.clear",
        "secrets.status",
        "instruments.search",
        "holdings.list",
        "holdings.upsert",
        "holdings.archive",
        "prices.refresh",
        "thesis.list",
        "thesis.create",
        "thesis.update",
        "thesis.archive",
        "thesis.versions",
        "inbox.list",
        "decision.get",
        "decision.act",
        "decision.reopen",
        "scan.start",
        "scan.cancel",
        "scan.status",
        "scan.history",
        "scan.detail",
        "scan.retryBatch",
        "paper.accounts",
        "paper.createAccount",
        "paper.portfolio",
        "paper.order.place",
        "paper.order.cancel",
        "paper.orders",
        "paper.advance",
        "paper.reset",
        "risk.compute",
        "demo.load",
        "demo.clear",
    }
)


def register_all(dispatcher: Dispatcher, container: AppContainer) -> int:
    before = set(dispatcher.methods())
    methods.settings.register(dispatcher, container)
    methods.markets.register(dispatcher, container)
    methods.portfolio.register(dispatcher, container)
    methods.inbox.register(dispatcher, container)
    methods.scan.register(dispatcher, container)
    methods.paper.register(dispatcher, container)
    methods.risk.register(dispatcher, container)
    methods.demo.register(dispatcher, container)
    added = set(dispatcher.methods()) - before
    missing = sorted(BUSINESS_METHODS - added)
    extra = sorted(added - BUSINESS_METHODS)
    if missing or extra:
        raise InternalError(
            detail=f"handlers incomplete: missing={missing} extra={extra}",
        )
    if len(added) != EXPECTED_BUSINESS_METHOD_COUNT:
        raise InternalError(detail=f"handler count {len(added)}")
    return len(added)


__all__ = [
    "BUSINESS_METHODS",
    "EXPECTED_BUSINESS_METHOD_COUNT",
    "METHOD_MODULES",
    "register_all",
]
