"""组合根对外入口。"""

from __future__ import annotations

from .container import AppContainer, build_container
from .main import run

__all__ = ["AppContainer", "build_container", "run"]
