"""8 个方法适配器模块；顺序即注册顺序，不在此处写业务逻辑。"""

from __future__ import annotations

from . import demo, inbox, markets, paper, portfolio, risk, scan, settings

__all__ = ["demo", "inbox", "markets", "paper", "portfolio", "risk", "scan", "settings"]
