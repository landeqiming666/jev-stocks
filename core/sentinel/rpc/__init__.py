from __future__ import annotations

from collections.abc import Sequence

from .cancel import CancelToken
from .dispatcher import Dispatcher
from .server import RpcServer, ServerConfig


def main(argv: Sequence[str] | None = None) -> int:
    from .__main__ import main as entry

    return entry(argv)


__all__ = ["CancelToken", "Dispatcher", "RpcServer", "ServerConfig", "main"]
